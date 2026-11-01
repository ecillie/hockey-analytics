"""Hostile values used to verify diagnostics never inspect payloads."""

import logging


class HostileValue:
    def __str__(self) -> str:
        raise AssertionError("diagnostics evaluated a payload")

    def __repr__(self) -> str:
        raise AssertionError("diagnostics evaluated a payload")


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
