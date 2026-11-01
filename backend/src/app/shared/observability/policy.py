"""Bounds that keep diagnostic rendering finite and fallback records deliverable."""

from dataclasses import dataclass
import logging

from app.shared.observability.domain import RecordLimits
from app.shared.observability.errors import RecordLimitsError
from app.shared.observability.schemas import read_lifecycle_report
from app.shared.observability.util import read_request_failure


def find_record_limits_violation(limits: RecordLimits) -> RecordLimitsError | None:
    boundaries = (
        ("record_bytes", limits.record_bytes, 1024, 8192),
        ("string_characters", limits.string_characters, 16, 256),
        ("stack_frames", limits.stack_frames, 1, 64),
        ("exception_depth", limits.exception_depth, 1, 8),
    )
    return next(
        (
            RecordLimitsError(field=name, minimum=minimum, maximum=maximum)
            for name, value, minimum, maximum in boundaries
            if type(value) is not int or value < minimum or value > maximum
        ),
        None,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ReportedRequestFilter:
    logger_name: str = "uvicorn.error"

    def filter(self, record: logging.LogRecord) -> bool:
        failure = read_request_failure(record, self.logger_name)
        if failure is None or not failure.reported:
            return True
        if not isinstance(record.exc_info, tuple) or record.exc_info[1] is None:
            return True
        try:
            record.exc_info[1].__dict__.pop("tradevalue_request", None)
        except BaseException:
            return True
        return False


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestFailureFilter:
    logger_name: str = "uvicorn.error"

    def filter(self, record: logging.LogRecord) -> bool:
        if failure := read_request_failure(record, self.logger_name):
            record.levelno = failure.level.value
            record.levelname = failure.level.name
        return True


@dataclass(slots=True, kw_only=True, frozen=True)
class LifecycleReportFilter:
    logger_name: str = "uvicorn.error"

    def filter(self, record: logging.LogRecord) -> bool:
        if report := read_lifecycle_report(record, self.logger_name):
            record.levelno = report.level.value
            record.levelname = report.level.name
            record.__dict__["lifecycle_report"] = report
        return True
