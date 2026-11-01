"""Verify real HTTP correlation and interrupted streaming on local containers."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
import logging
import os

import httpx

from app.shared.cli import ExitCode
from app.shared.observability.domain import read_logging_settings
from app.shared.observability.services import configure_logging


logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProbeOptions:
    base_urls: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_urls", nargs="+")
    return parser


def read_interrupted_stream(client: httpx.Client) -> dict[str, object]:
    chunks: list[bytes] = []
    interrupted = False
    with client.stream(
        "GET",
        "/probe/stream?token=query_secret",
        headers={"Origin": "http://localhost:5173", "X-Request-ID": "caller_secret"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["access-control-expose-headers"] == "X-Request-ID"
        request_id = response.headers["x-request-id"]
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


def probe_container(base_url: str) -> dict[str, object]:
    results: dict[str, object] = {}
    cases = (
        ("health", "/api/health?token=query_secret", 200),
        ("seasons", "/api/seasons?token=query_secret", 200),
        ("invalid", "/api/players?season=invalid_secret", 400),
        ("missing", "/missing_secret?token=query_secret", 404),
        ("unexpected", "/probe/number/value_secret?token=query_secret", 500),
    )
    with httpx.Client(base_url=base_url, timeout=5) as client:
        for name, path, status in cases:
            response = client.get(
                path,
                headers={
                    "Origin": "http://localhost:5173",
                    "X-Request-ID": "caller_secret",
                },
            )
            assert response.status_code == status
            request_id = response.headers["x-request-id"]
            assert len(request_id) == 32 and request_id != "caller_secret"
            assert (
                response.headers["access-control-allow-origin"]
                == "http://localhost:5173"
            )
            assert response.headers["access-control-expose-headers"] == "X-Request-ID"
            if name == "unexpected":
                assert response.json() == {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "The API could not complete this request.",
                    }
                }
            results[name] = {"request_id": request_id, "status": status}
        results["stream"] = read_interrupted_stream(client)
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
