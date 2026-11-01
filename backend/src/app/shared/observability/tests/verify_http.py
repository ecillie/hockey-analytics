"""Verify real HTTP correlation and interrupted streaming on local containers."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
import json
import logging
import os
from typing import Annotated, NotRequired, TypedDict
from uuid import uuid4

import httpx
from pydantic import StringConstraints, TypeAdapter
from app.api.schemas import ErrorResponse, HealthResponse, SeasonInfo

from app.shared.cli import ExitCode
from app.shared.observability.domain import read_logging_settings
from app.shared.observability.services import configure_logging


logger = logging.getLogger(__name__)


type RequestId = Annotated[
    str, StringConstraints(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
]


class ProbeResponse(TypedDict):
    request_id: RequestId
    status: int
    bytes: NotRequired[int]
    interrupted: NotRequired[bool]


class ProbeReport(TypedDict):
    base_url: str
    requests: dict[str, ProbeResponse]


class ProbeKind(StrEnum):
    HEALTH = auto()
    SEASONS = auto()
    INVALID = auto()
    MISSING = auto()
    UNEXPECTED = auto()


def build_probe_headers() -> dict[str, str]:
    return {
        "Origin": "http://localhost:5173",
        "X-Request-ID": uuid4().hex,
        "Authorization": "Bearer header_secret",
        "Cookie": "session=cookie_secret",
    }


def read_request_id(response: httpx.Response) -> str:
    request_id = TypeAdapter(RequestId).validate_python(
        response.headers["x-request-id"]
    )
    assert request_id != response.request.headers["x-request-id"]
    return request_id


def verify_response_body(kind: ProbeKind, response: httpx.Response) -> None:
    if kind is ProbeKind.HEALTH:
        HealthResponse.model_validate_json(response.content, strict=True)
        return
    if kind is ProbeKind.SEASONS:
        seasons = SeasonInfo.model_validate_json(response.content, strict=True)
        assert len(seasons.availableSeasons) > 0
        assert seasons.currentSeason in {
            season.startYear for season in seasons.availableSeasons
        }
        return
    if kind is ProbeKind.MISSING:
        assert response.json() == {"detail": "Not Found"}
        return
    error = ErrorResponse.model_validate_json(response.content, strict=True)
    assert error.error.code == (
        "INVALID_REQUEST" if kind is ProbeKind.INVALID else "INTERNAL_ERROR"
    )
    if kind is ProbeKind.INVALID:
        assert error.error.message == "The request parameters are invalid."
        assert error.error.details is not None
        assert set(error.error.details) == {"season"}
        assert len(error.error.details["season"]) > 0
        return
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "The API could not complete this request.",
        }
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class ProbeOptions:
    base_urls: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_urls", nargs="+")
    return parser


def read_interrupted_stream(client: httpx.Client) -> ProbeResponse:
    chunks: list[bytes] = []
    interrupted = False
    with client.stream(
        "GET",
        "/probe/stream?token=query_secret",
        headers=build_probe_headers(),
    ) as response:
        assert response.status_code == 200
        assert response.headers["access-control-expose-headers"] == "X-Request-ID"
        request_id = read_request_id(response)
        try:
            for chunk in response.iter_bytes():
                chunks.append(chunk)
        except httpx.RemoteProtocolError:
            interrupted = True
    assert interrupted
    assert b"".join(chunks) == b"first_chunk"
    return {
        "request_id": request_id,
        "status": 200,
        "bytes": sum(map(len, chunks)),
        "interrupted": interrupted,
    }


def probe_container(base_url: str) -> ProbeReport:
    results: dict[str, ProbeResponse] = {}
    cases = (
        (ProbeKind.HEALTH, "/api/health?token=query_secret", 200),
        (ProbeKind.SEASONS, "/api/seasons?token=query_secret", 200),
        (ProbeKind.INVALID, "/api/players?season=invalid_secret", 400),
        (ProbeKind.MISSING, "/missing_secret?token=query_secret", 404),
        (ProbeKind.UNEXPECTED, "/probe/number/value_secret?token=query_secret", 500),
    )
    with httpx.Client(base_url=base_url, timeout=5) as client:
        for name, path, status in cases:
            response = client.get(
                path,
                headers=build_probe_headers(),
            )
            assert response.status_code == status
            request_id = read_request_id(response)
            assert (
                response.headers["access-control-allow-origin"]
                == "http://localhost:5173"
            )
            assert response.headers["access-control-expose-headers"] == "X-Request-ID"
            verify_response_body(name, response)
            results[name.value] = {"request_id": request_id, "status": status}
        results["stream"] = read_interrupted_stream(client)
    assert len({value["request_id"] for value in results.values()}) == len(results)
    return {"base_url": base_url, "requests": results}


def main(argv: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    options = ProbeOptions(base_urls=tuple(parsed.base_urls))
    configure_logging(read_logging_settings(os.environ))
    try:
        results = list(map(probe_container, options.base_urls))
    except Exception:
        logger.exception(
            "HTTP verification failed", extra={"event": "verification.failed"}
        )
        return ExitCode.FAILURE
    print(json.dumps(results))
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
