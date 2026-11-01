"""Complete owned cleanup operations while retaining the primary failure."""

from collections.abc import Callable
import asyncio


def retain_cleanup_failure(
    primary: BaseException | None, cleanup: BaseException
) -> BaseException:
    if primary is None:
        return cleanup
    primary.add_note(f"Resource cleanup also failed: {cleanup!r}")
    try:
        if not isinstance(cleanup, (asyncio.CancelledError, KeyboardInterrupt)):
            primary.__dict__["tradevalue_cleanup_failed"] = True
        previous = primary.__dict__.setdefault("tradevalue_cleanup", cleanup)
        if previous is not cleanup:
            primary.__dict__["tradevalue_cleanup_truncated"] = True
    except Exception:
        pass
    return primary


def complete_cleanup(
    operations: tuple[Callable[[], object], ...], primary: BaseException | None
) -> None:
    failure = primary
    for operation in operations:
        try:
            operation()
        except BaseException as cleanup:
            failure = retain_cleanup_failure(failure, cleanup)
    if primary is None and failure is not None:
        raise failure
