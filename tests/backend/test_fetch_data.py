"""Hosted ingestion downloads its season CSVs from blob storage before run_all."""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from typing import BinaryIO

import pytest

from app.ScriptingFiles.FullDataScript.fetch_data import (
    BlobNameError,
    EmptyBlobContainerError,
    fetch_data,
    main,
    read_blob_url,
    resolve_blob_path,
)
from app.shared.cli import ExitCode
from app.config import ConfigurationError


CONTAINER_URL = "https://hockeyanalyticsnpst.blob.core.windows.net/ingestion-data"


@dataclass(slots=True, kw_only=True)
class FakeBlobSource:
    blobs: dict[str, bytes]
    downloaded: list[str] = field(default_factory=list)

    def list_names(self) -> Iterable[str]:
        return tuple(self.blobs)

    def download(self, name: str, target: BinaryIO) -> None:
        self.downloaded.append(name)
        target.write(self.blobs[name])


@dataclass(slots=True, kw_only=True)
class FakeSourceOpener:
    source: FakeBlobSource
    opened: list[str] = field(default_factory=list)

    @contextmanager
    def __call__(self, container_url: str) -> Generator[FakeBlobSource]:
        self.opened.append(container_url)
        yield self.source


@pytest.fixture
def season_blobs():
    return {
        "skater advanced/skaters_2008_to_2024.csv": b"season,name\n2024,a\n",
        "goalie_advanced/goalies_2008_to_2024.csv": b"season,name\n2024,b\n",
    }


class TestFetchData:
    def test_blobs_are_written_under_destination_with_their_folders(
        self, tmp_path, season_blobs
    ):
        summary = fetch_data(FakeBlobSource(blobs=season_blobs), tmp_path)
        assert summary.files == 2
        assert summary.bytes == sum(len(value) for value in season_blobs.values())
        for name, content in season_blobs.items():
            assert tmp_path.joinpath(*name.split("/")).read_bytes() == content

    @pytest.mark.parametrize(
        "name", ["../escape.csv", "/absolute.csv", "a/./b.csv", "a//b.csv", ""]
    )
    def test_unsafe_blob_names_are_rejected(self, tmp_path, name):
        with pytest.raises(BlobNameError):
            resolve_blob_path(tmp_path, name)

    def test_unsafe_name_stops_before_any_download(self, tmp_path, season_blobs):
        source = FakeBlobSource(blobs=season_blobs | {"../escape.csv": b"x"})
        with pytest.raises(BlobNameError):
            fetch_data(source, tmp_path)
        assert source.downloaded == []

    def test_empty_container_fails(self, tmp_path):
        with pytest.raises(EmptyBlobContainerError):
            fetch_data(FakeBlobSource(blobs={}), tmp_path)


class TestBlobUrl:
    def test_https_container_url_is_accepted(self):
        values = {"TRADEVALUE_DATA_BLOB_URL": f" {CONTAINER_URL} "}
        assert read_blob_url(values) == CONTAINER_URL

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "http://account.blob.core.windows.net/data",
            "https://account.blob.core.windows.net/",
        ],
    )
    def test_missing_or_unsafe_url_is_rejected(self, value):
        with pytest.raises(ConfigurationError):
            read_blob_url({"TRADEVALUE_DATA_BLOB_URL": value})


@pytest.mark.usefixtures("isolate_command_logging")
class TestCommand:
    @pytest.fixture
    def environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADEVALUE_ENV_FILE", str(tmp_path / "missing.env"))
        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("TRADEVALUE_DATA_BLOB_URL", CONTAINER_URL)

    @pytest.mark.usefixtures("environment")
    def test_success_prints_summary_and_exits_zero(
        self, tmp_path, season_blobs, capsys
    ):
        opener = FakeSourceOpener(source=FakeBlobSource(blobs=season_blobs))
        destination = tmp_path / "data"
        code = main(["--destination", str(destination)], open_source=opener)
        assert code == ExitCode.SUCCESS
        assert opener.opened == [CONTAINER_URL]
        assert json.loads(capsys.readouterr().out)["files"] == 2

    @pytest.mark.usefixtures("environment")
    def test_download_failure_exits_one(self, tmp_path):
        opener = FakeSourceOpener(source=FakeBlobSource(blobs={}))
        code = main(["--destination", str(tmp_path)], open_source=opener)
        assert code == ExitCode.FAILURE

    def test_missing_url_exits_two_before_opening_storage(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRADEVALUE_ENV_FILE", str(tmp_path / "missing.env"))
        monkeypatch.delenv("TRADEVALUE_DATA_BLOB_URL", raising=False)
        opener = FakeSourceOpener(source=FakeBlobSource(blobs={}))
        with pytest.raises(SystemExit) as raised:
            main(["--destination", str(tmp_path)], open_source=opener)
        assert raised.value.code == 2
        assert opener.opened == []
