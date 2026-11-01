"""Hostile values used to verify diagnostics never inspect payloads."""

import logging
from email.message import Message
from urllib.error import HTTPError

from sqlalchemy.exc import OperationalError


class HostileValue:
    def __str__(self) -> str:
        raise AssertionError("diagnostics evaluated a payload")

    def __repr__(self) -> str:
        raise AssertionError("diagnostics evaluated a payload")


class MetadataAccessError(RuntimeError):
    def __init__(self, *, failure: BaseException) -> None:
        super().__init__("primary_secret")
        self.failure = failure

    @property
    def __dict__(self) -> dict[str, object]:
        raise self.failure


def build_exception_record(secret: str) -> logging.LogRecord:
    error = RuntimeError(secret)
    error.add_note(secret)
    error.__cause__ = ValueError(secret)
    record = logging.LogRecord(
        "app.jobs", logging.ERROR, "", 1, secret, (), (RuntimeError, error, None)
    )
    record.event = "job.failed"
    return record


class BrokenStream:
    def write(self, value: str) -> int:
        raise OSError("secret sink failure")

    def flush(self) -> None:
        raise OSError("secret flush failure")


def parse_source_number() -> int:
    return int("sensitive source value")


def capture_source_failure() -> ValueError:
    try:
        parse_source_number()
    except ValueError as error:
        return error
    raise AssertionError("source scenario must fail")


def build_bounded_record() -> logging.LogRecord:
    error = capture_source_failure()
    record = build_exception_record("secret")
    current: BaseException = error
    for _ in range(10):
        previous = RuntimeError("secret")
        previous.__traceback__ = error.__traceback__
        previous.__cause__ = current
        current = previous
    record.exc_info = (type(current), current, current.__traceback__)
    record.request_id = "retained-request-id"
    return record


def build_connection_error_record() -> logging.LogRecord:
    error = OperationalError(
        "SELECT :secret",
        {"password": "secret"},
        ConnectionError("postgresql://user:secret@host/db"),
    )
    error.__cause__ = error.orig
    record = build_exception_record("secret")
    record.exc_info = (type(error), error, None)
    record.payload = {"nested": {"authorization": HostileValue()}}
    return record


def build_http_error_record() -> logging.LogRecord:
    headers = Message()
    headers["Authorization"] = "secret"
    error = HTTPError(
        "https://feed.invalid?token=secret",
        503,
        "secret",
        headers,
        None,
    )
    error.__cause__ = ConnectionError("secret upstream failure")
    record = build_exception_record("secret")
    record.exc_info = (type(error), error, None)
    record.payload = {"nested": {"authorization": HostileValue()}}
    return record
