"""Structured backend diagnostics with allowlisted fields and no free-text payloads.

Configuration belongs to process entrypoints. Importing this module has no logging,
network, database, or environment-loading side effects.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path, PurePath
import re
import sys
from threading import RLock
import traceback
from uuid import UUID

_CONTEXT: ContextVar[dict] = ContextVar("backend_log_context", default={})
_LOCK = RLock()
BACKEND_DIR = Path(__file__).resolve().parent.parent
_EVENTS = frozenset({
    "api.request_completed", "api.request_cancelled", "api.database_error",
    "api.validation_failed", "api.problem", "job.started", "job.finished",
    "job.error", "job.resumed", "job.batch_validated", "job.batch_accepted",
    "job.checkpoint_committed", "job.persistence_error", "setup.started",
    "setup.finished", "setup.error", "source.request", "source.retry",
    "source.failed", "source.invalid_json", "upload.retry", "upload.failed",
    "database.connected", "database.connection_failed", "database.schema_checked",
    "database.committed", "database.rolled_back", "database.rollback_failed", "cli.failed",
})
_IDS = {"request_id", "job_run_id", "setup_run_id", "batch_id"}
_NAMES = {"job", "source", "mode", "status", "component", "error_code"}
_NUMBERS = {
    "status_code", "duration_ms", "attempt", "delay_seconds", "batch_index",
    "records", "issues", "read", "accepted", "rejected", "unresolved", "skipped",
    "written", "unchanged", "completed_batches", "first_season", "last_season",
    "correction_lookback_days", "requested_jobs", "completed_jobs",
    "checkpoint_count", "coverage_count", "github_run_id", "github_run_attempt",
}
_BOOLS = {"resume", "validation_only", "complete", "checkpoint_complete"}
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}


def _fields(values):
    """Never stringify arbitrary objects or pass through unknown extra fields."""
    result = {}
    for key, value in values.items():
        if key in _IDS:
            try:
                result[key] = str(UUID(str(value)))
            except (ValueError, TypeError, AttributeError):
                pass
        elif key == "environment":
            if value in ("dev", "nonprod", "prod", "unknown"):
                result[key] = value
        elif key in _NAMES:
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value):
                result[key] = value
        elif key in _NUMBERS:
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                result[key] = value
        elif key in _BOOLS and type(value) is bool:
            result[key] = value
        elif key == "method":
            result[key] = value if isinstance(value, str) and value in _METHODS else "OTHER"
        elif key == "route" and isinstance(value, str) and len(value) <= 256 and re.fullmatch(r"[/A-Za-z0-9_{}:.-]+", value):
            # Only call with a matched route template, never a raw request path.
            result[key] = value
        elif key == "github_sha" and isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
            result[key] = value
        elif key == "game_types" and isinstance(value, (list, tuple)) and all(type(v) is int and v in (2, 3) for v in value):
            result[key] = list(value)
    return result


def exception_summary(error):
    """Retain exception types and stack locations, never messages, source, or locals."""
    result, seen = [], set()
    while error is not None and id(error) not in seen and len(result) < 5:
        seen.add(id(error))
        result.append({
            "type": type(error).__name__,
            "frames": [{"file": PurePath(frame.filename).name, "line": frame.lineno,
                        "function": frame.name}
                       for frame in traceback.extract_tb(error.__traceback__)[-12:]],
        })
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return result


@contextmanager
def log_context(**values):
    token = _CONTEXT.set({**_CONTEXT.get(), **_fields(values)})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def log_event(logger, event, *, level=logging.INFO, error=None, **values):
    if event not in _EVENTS:
        raise ValueError("Unknown backend log event")
    payload = {**_CONTEXT.get(), **_fields(values)}
    if error is not None:
        payload["exceptions"] = exception_summary(error)
    # Never attach the actual exception/args to the LogRecord: other handlers may
    # use a different formatter. Diagnostic values are sanitized before emission.
    logger.log(level, event, extra={"backend_event": event, "backend_fields": payload})


class JsonFormatter(logging.Formatter):
    def __init__(self, *, environment=None):
        super().__init__()
        self.environment = environment

    def format(self, record):
        import json
        environment = self.environment if self.environment is not None else os.getenv("ENV", "unknown")
        namespace = record.name.split(".", 1)[0]
        component = namespace if namespace in ("app", "uvicorn", "sqlalchemy", "httpx", "httpcore", "alembic") else "dependency"
        result = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "severity": record.levelname,
            "component": component,
            "environment": environment if environment in ("dev", "nonprod", "prod") else "unknown",
            **_CONTEXT.get(),
        }
        event = getattr(record, "backend_event", None)
        if event in _EVENTS:
            values = getattr(record, "backend_fields", {})
            result.update(_fields(values))
            if "exceptions" in values:
                result["exceptions"] = values["exceptions"]
            result["event"] = event
        else:
            # Dependency messages can contain SQL, URLs, headers, or raw payloads.
            # Do not call record.getMessage() or formatException()/formatStack().
            result["event"] = "library_log"
            if record.exc_info and isinstance(record.exc_info[1], BaseException):
                result["exceptions"] = exception_summary(record.exc_info[1])
        return json.dumps(result, ensure_ascii=True, allow_nan=False)


def configure_logging(*, level=None, stream=None, environment=None):
    """Own process logging, including existing server/library handlers, idempotently.

    LOG_LEVEL controls all backend diagnostics. stdout remains reserved for CLI
    reports. LOG_FILE adds a rotating file only in dev; relative paths are anchored
    to backend/. Only our own handlers are closed during reconfiguration.
    """
    selected = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    if selected not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    with _LOCK:
        effective_environment = environment if environment is not None else os.getenv("ENV", "unknown")
        formatter = JsonFormatter(environment=effective_environment)
        handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
        handler.setFormatter(formatter)
        handler._backend_owned = True
        handlers = [handler]
        filename = os.getenv("LOG_FILE", "").strip()
        if effective_environment == "dev" and filename:
            try:
                path = Path(filename).expanduser()
                if not path.is_absolute():
                    path = BACKEND_DIR / path
                path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024,
                                                  backupCount=3, encoding="utf-8")
            except (OSError, RuntimeError, ValueError):
                # Do not leak a configured path or filesystem exception text.
                raise ValueError("Unable to open LOG_FILE; check file and directory access.") from None
            file_handler.setFormatter(formatter)
            file_handler._backend_owned = True
            handlers.append(file_handler)
        root = logging.getLogger()
        previous = set(root.handlers)
        root.handlers.clear()
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(selected)
        for logger in list(logging.Logger.manager.loggerDict.values()):
            if isinstance(logger, logging.Logger):
                previous.update(logger.handlers)
                logger.handlers.clear()
                logger.propagate = True
                logger.setLevel(logging.NOTSET)
        for handler in previous:
            if getattr(handler, "_backend_owned", False):
                handler.close()
        # The ASGI middleware owns request records and safely uses route templates.
        logging.getLogger("uvicorn.access").disabled = True
        logging.raiseExceptions = False
        logging.captureWarnings(True)


def workflow_context():
    values = {}
    for variable, field in (("GITHUB_RUN_ID", "github_run_id"), ("GITHUB_RUN_ATTEMPT", "github_run_attempt")):
        value = os.getenv(variable, "")
        if value.isascii() and value.isdigit() and len(value) <= 20:
            values[field] = int(value)
    values["github_sha"] = os.getenv("GITHUB_SHA", "")
    return _fields(values)
