"""Match captured local runtime events to real HTTP response request IDs."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path

from app.shared.cli import ExitCode
from app.shared.observability.domain import read_logging_settings
from app.shared.observability.services import configure_logging


logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProbeOptions:
    directory: Path = Path("/private/tmp")
    results: Path = Path("/private/tmp/tradevalue-logging02-probe-results.json")
    record_bytes: int = 8192


def build_parser() -> argparse.ArgumentParser:
    defaults = ProbeOptions()
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=defaults.directory)
    parser.add_argument("--results", type=Path, default=defaults.results)
    return parser


def read_events(path: Path, record_bytes: int) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    assert "secret" not in raw and "postgresql://" not in raw
    events = []
    for line in raw.splitlines():
        if not line.startswith(("{", "event {")):
            assert line.startswith("INFO:") and (
                "Started server process" in line
                or "Waiting for application startup" in line
            )
            continue
        assert len(line.encode()) + 1 <= record_bytes
        events.append(json.loads(line.removeprefix("event ")))
    return events


def verify_mode(mode: str, report: dict, options: ProbeOptions) -> dict:
    events = read_events(
        options.directory.joinpath(f"tradevalue-logging02-{mode}.log"),
        options.record_bytes,
    )
    assert sum(item["event"] == "service.ready" for item in events) == 1
    assert sum(item["event"] == "service.stopped" for item in events) == 1
    assert all(
        "request_id" not in item
        for item in events
        if item["event"].startswith("service.")
    )
    routes = {
        "health": "/api/health",
        "seasons": "/api/seasons",
        "invalid": "/api/players",
        "missing": None,
        "unexpected": "/probe/number/{key}",
        "stream": "/probe/stream",
    }
    for name, response in report["requests"].items():
        selected = [
            item for item in events if item.get("request_id") == response["request_id"]
        ]
        summaries = [item for item in selected if item["event"] == "request.finished"]
        errors = [item for item in selected if item["event"] == "request.failed"]
        assert len(summaries) == (0 if name == "health" and mode == "info" else 1)
        assert len(errors) == (1 if name in ("unexpected", "stream") else 0)
        assert sum(item["event"] == "request.started" for item in selected) == (
            1 if mode == "debug" else 0
        )
        if summaries:
            assert summaries[0]["status"] == response["status"]
            assert summaries[0].get("route") == routes[name]
        if name in ("unexpected", "stream"):
            assert summaries[0]["outcome"] == "failed"
            assert errors[0]["exceptions"]
    assert (
        not any(item["severity"] == "DEBUG" for item in events)
        if mode == "info"
        else any(item["severity"] == "DEBUG" for item in events)
    )
    return {
        "mode": mode,
        "events": len(events),
        "correlated_requests": len(report["requests"]),
        "stream_interrupted": report["requests"]["stream"]["interrupted"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    options = ProbeOptions(**vars(build_parser().parse_args(argv)))
    configure_logging(read_logging_settings(os.environ))
    try:
        reports = json.loads(options.results.read_text(encoding="utf-8"))
        verified = [
            verify_mode(mode, report, options)
            for mode, report in zip(("info", "debug"), reports, strict=True)
        ]
        startup = read_events(
            options.directory.joinpath("tradevalue-logging02-startup-failure.log"),
            options.record_bytes,
        )
        failures = [
            item for item in startup if item["event"] == "service.startup_failed"
        ]
        assert len(failures) == 1
        assert failures[0]["severity"] == "CRITICAL"
        assert failures[0]["exceptions"][0]["type"] == "ConfigurationError"
        assert not any(item["event"] == "service.ready" for item in startup)
        assert (
            options.directory.joinpath("tradevalue-logging02-startup-failure.exitcode")
            .read_text()
            .strip()
            == "3"
        )
        verified.append(
            {"mode": "startup_failure", "severity": "CRITICAL", "exit_code": 3}
        )
    except Exception:
        logger.exception(
            "Captured log verification failed", extra={"event": "verification.failed"}
        )
        return ExitCode.FAILURE
    print(json.dumps(verified))
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
