"""Download the historical season CSVs from blob storage for hosted ingestion."""

import argparse
import json
import logging
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import urlsplit

from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient

from app.config import ConfigurationError, load_environment
from app.shared.cli import ExitCode
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_command_exceptions,
    configure_logging,
    finish_command,
    start_command,
)


logger = logging.getLogger(__name__)

BLOB_URL_SETTING = "TRADEVALUE_DATA_BLOB_URL"


class BlobSource(Protocol):
    def list_names(self) -> Iterable[str]: ...

    def download(self, name: str, target: BinaryIO) -> None: ...


class BlobNameError(ValueError):
    def __init__(self) -> None:
        super().__init__("Blob names must be relative paths without . or .. parts")


class EmptyBlobContainerError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("The ingestion data container has no blobs")


@dataclass(slots=True, kw_only=True, frozen=True)
class FetchSummary:
    files: int
    bytes: int


@dataclass(slots=True, kw_only=True, frozen=True)
class AzureBlobSource:
    client: ContainerClient

    def list_names(self) -> Iterable[str]:
        return tuple(blob.name for blob in self.client.list_blobs())

    def download(self, name: str, target: BinaryIO) -> None:
        self.client.download_blob(name).readinto(target)


@contextmanager
def open_azure_source(container_url: str) -> Generator[BlobSource]:
    credential = DefaultAzureCredential()
    with (
        closing(credential),
        ContainerClient.from_container_url(
            container_url, credential=credential
        ) as client,
    ):
        yield AzureBlobSource(client=client)


def read_blob_url(values: Mapping[str, str]) -> str:
    url = values.get(BLOB_URL_SETTING, "").strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc == "" or parts.path.strip("/") == "":
        raise ConfigurationError(
            field=BLOB_URL_SETTING, reason="must be an https blob container URL"
        )
    return url


def resolve_blob_path(destination: Path, name: str) -> Path:
    parts = name.split("/")
    if any(part in ("", ".", "..") or "\\" in part for part in parts):
        raise BlobNameError()
    return destination.joinpath(*parts)


def fetch_data(source: BlobSource, destination: Path) -> FetchSummary:
    names = tuple(source.list_names())
    if len(names) == 0:
        raise EmptyBlobContainerError()
    targets = tuple((name, resolve_blob_path(destination, name)) for name in names)
    total = 0
    for name, path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as target:
            source.download(name, target)
        total += path.stat().st_size
    return FetchSummary(files=len(targets), bytes=total)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    open_source: Callable[
        [str], AbstractContextManager[BlobSource]
    ] = open_azure_source,
) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    values = load_environment()
    try:
        settings = read_logging_settings(values)
        container_url = read_blob_url(values)
    except (LoggingSettingsError, ConfigurationError) as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("fetch_data")
    configure_command_exceptions(context)
    try:
        with open_source(container_url) as source:
            summary = fetch_data(source, options.destination)
    except Exception:
        logger.exception(
            "Ingestion data download failed",
            extra=context.fields | {"event": "command.failed"},
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    print(json.dumps({"bytes": summary.bytes, "files": summary.files}, sort_keys=True))
    finish_command(context, CommandOutcome.COMPLETED)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
