"""Complete owned cleanup operations while retaining the primary failure."""

from collections.abc import Callable


def retain_cleanup_failure(
    primary: BaseException | None, cleanup: BaseException
) -> BaseException:
    if primary is None:
        return cleanup
    primary.add_note(f"Resource cleanup also failed: {cleanup!r}")
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
