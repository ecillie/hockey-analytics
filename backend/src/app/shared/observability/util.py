"""Pure extraction of request and failure metadata without formatting payloads."""

import logging
import asyncio

from starlette.routing import Route
from starlette.types import Scope

from app.shared.observability.domain import RequestContext, RequestFailure


def get_request_context(scope: Scope) -> RequestContext | None:
    context = scope.get("state", {}).get("logging_context")
    return context if isinstance(context, RequestContext) else None


def build_request_fields(scope: Scope, context: RequestContext) -> dict[str, object]:
    fields: dict[str, object] = {
        "request_id": context.request_id,
        "method": scope.get("method", "UNKNOWN"),
    }
    if isinstance(route := scope.get("route"), Route):
        fields["route"] = route.path
    return fields


def read_cleanup_failure(error: BaseException) -> BaseException | None:
    try:
        cleanup = error.__dict__.get("tradevalue_cleanup")
    except BaseException:
        return None
    return cleanup if isinstance(cleanup, BaseException) else None


def has_truncated_cleanup(error: BaseException) -> bool:
    try:
        return error.__dict__.get("tradevalue_cleanup_truncated") is True
    except BaseException:
        return True


def is_expected_cancellation(error: BaseException) -> bool:
    if not isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)):
        return False
    cleanup = read_cleanup_failure(error)
    try:
        failed = error.__dict__.get("tradevalue_cleanup_failed") is True
    except BaseException:
        return False
    return (
        cleanup is None
        or isinstance(cleanup, (asyncio.CancelledError, KeyboardInterrupt))
    ) and not failed


def read_request_failure(
    record: logging.LogRecord, logger_name: str = "uvicorn.error"
) -> RequestFailure | None:
    if (
        record.name != logger_name
        or type(record.msg) is not str
        or record.msg
        not in ("Exception in ASGI application\n", "Exception in ASGI application")
    ):
        return None
    if not isinstance(record.exc_info, tuple) or record.exc_info[1] is None:
        return None
    try:
        failure = record.exc_info[1].__dict__.get("tradevalue_request")
    except BaseException:
        return None
    return failure if isinstance(failure, RequestFailure) else None
