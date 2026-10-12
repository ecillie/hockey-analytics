"""Common bounded retry timing for source requests and atomic uploads."""


def backoff_delay(attempt: int, maximum: float) -> float:
    """Attempt zero precedes the first retry; retries never exceed their wait cap."""
    return min(2 ** attempt, maximum)
