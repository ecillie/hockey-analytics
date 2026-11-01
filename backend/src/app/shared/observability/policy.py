"""Bounds that keep diagnostic rendering finite and fallback records deliverable."""

from app.shared.observability.domain import RecordLimits


class RecordLimitsError(ValueError):
    def __init__(self, *, field: str, minimum: int, maximum: int) -> None:
        super().__init__(f"{field} must be between {minimum} and {maximum}")
        self.field = field
        self.minimum = minimum
        self.maximum = maximum


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
