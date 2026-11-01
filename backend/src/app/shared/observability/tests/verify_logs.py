"""Match captured local runtime events to real HTTP response request IDs."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
import json
import logging
import os
from pathlib import Path
from typing import NotRequired, TypedDict
from pydantic import TypeAdapter

from app.shared.cli import ExitCode
from app.shared.observability.domain import LogLevel, read_logging_settings
from app.shared.observability.schemas import ExceptionSnapshots, SafeIdentifier
from app.shared.observability.tests.verify_http import ProbeReport, RequestId
from app.shared.observability.services import configure_logging


logger = logging.getLogger(__name__)


class CapturedEvent(TypedDict):
    event: SafeIdentifier
    severity: str
    request_id: NotRequired[RequestId]
    status: NotRequired[int]
    route: NotRequired[str]
    outcome: NotRequired[str]
    exceptions: NotRequired[ExceptionSnapshots]


class ProbeMode(StrEnum):
    INFO = auto()
    DEBUG = auto()

    @property
    def level(self) -> LogLevel:
        return LogLevel[self.name]


type VerificationResult = dict[str, str | int | bool]


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


def read_events(path: Path, record_bytes: int) -> list[CapturedEvent]:
    raw = path.read_text(encoding="utf-8")
    assert "secret" not in raw and "postgresql://" not in raw
    events: list[CapturedEvent] = []
    adapter = TypeAdapter(CapturedEvent)
    for line in raw.splitlines():
        if not line.startswith(("{", "event {")):
            assert line.startswith("INFO:") and (
                "Started server process" in line
                or "Waiting for application startup" in line
            )
            continue
        assert len(line.encode()) + 1 <= record_bytes
        event = adapter.validate_json(line.removeprefix("event "), strict=True)
        LogLevel[event["severity"]]
        events.append(event)
    return events


def verify_mode(
    mode: ProbeMode, report: ProbeReport, options: ProbeOptions
) -> VerificationResult:
    events = read_events(
        options.directory.joinpath(f"tradevalue-logging02-{mode}.log"),
        options.record_bytes,
    )
    assert sum(item["event"] == "service.ready" for item in events) == 1
    assert sum(item["event"] == "service.stopped" for item in events) == 1
    assert all(
        item["severity"] == "INFO"
        for item in events
        if item["event"] in ("service.ready", "service.stopped")
    )
    assert all(
        "request_id" not in item
        for item in events
        if item["event"].startswith("service.")
    )
    assert all(LogLevel[item["severity"]] >= mode.level for item in events)
    assert report["requests"]["stream"].get("interrupted") is True
    assert report["requests"]["stream"].get("bytes") == len(b"first_chunk")
    expected_errors = {
        report["requests"][name]["request_id"] for name in ("unexpected", "stream")
    }
    error_records = [
        item for item in events if LogLevel[item["severity"]] >= LogLevel.ERROR
    ]
    assert len(error_records) == len(expected_errors)
    assert {item.get("request_id") for item in error_records} == expected_errors
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
        assert len(summaries) == (
            0 if name == "health" and mode is ProbeMode.INFO else 1
        )
        assert len(errors) == (1 if name in ("unexpected", "stream") else 0)
        assert sum(item["event"] == "request.started" for item in selected) == (
            1 if mode is ProbeMode.DEBUG else 0
        )
        if len(summaries) > 0:
            assert summaries[0]["status"] == response["status"]
            assert summaries[0].get("route") == routes[name]
            assert summaries[0]["severity"] == ("DEBUG" if name == "health" else "INFO")
        assert all(
            item["severity"] == "DEBUG"
            for item in selected
            if item["event"] == "request.started"
        )
        if name in ("unexpected", "stream"):
            assert summaries[0]["outcome"] == "failed"
            assert len(errors[0]["exceptions"]) > 0
            assert errors[0]["severity"] == "ERROR"
    assert (
        not any(item["severity"] == "DEBUG" for item in events)
        if mode is ProbeMode.INFO
        else any(item["severity"] == "DEBUG" for item in events)
    )
    return {
        "mode": mode.value,
        "events": len(events),
        "correlated_requests": sum(
            any(item.get("request_id") == response["request_id"] for item in events)
            for response in report["requests"].values()
        ),
        "stream_interrupted": report["requests"]["stream"].get("interrupted") is True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    options = ProbeOptions(**vars(build_parser().parse_args(argv)))
    configure_logging(read_logging_settings(os.environ))
    try:
        reports = TypeAdapter(list[ProbeReport]).validate_json(
            options.results.read_text(encoding="utf-8"), strict=True
        )
        verified = [
            verify_mode(mode, report, options)
            for mode, report in zip(
                (ProbeMode.INFO, ProbeMode.DEBUG), reports, strict=True
            )
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
        assert failures[0]["exceptions"][0].type == "ConfigurationError"
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
