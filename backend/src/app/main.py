"""ASGI entry point for the TradeValue backend."""

import logging
import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp

from app.api.routes import create_router
from app.api.errors import ApiProblem
from app.config import (
    ApiSettings,
    DatabaseSettings,
    DatabaseEnvironment,
    get_api_settings,
    get_database_settings,
    load_environment,
)
from app.database import DatabaseResources, create_database_resources
from app.shared.observability.domain import LoggingSettings, read_logging_settings
from app.shared.observability.services import (
    configure_api_host_logging,
    configure_logging,
    report_request_error,
    retain_lifespan_cleanup,
)
from app.shared.observability.requests import RequestLoggingMiddleware
from app.shared.observability.lifecycle import LifecycleLoggingMiddleware


logger = logging.getLogger(__name__)


def build_api_error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def remove_validation_responses(schema: dict) -> None:
    operations = (
        operation for path in schema["paths"].values() for operation in path.values()
    )
    for operation in operations:
        if isinstance(operation, dict):
            operation.get("responses", {}).pop("422", None)


class ContractFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        settings: ApiSettings = self.state.api_settings
        return LifecycleLoggingMiddleware(
            settings=self.state.logging_settings,
            app=RequestLoggingMiddleware(
                app=CORSMiddleware(
                    app=super().build_middleware_stack(),
                    allow_origins=list(settings.cors_origins),
                    allow_origin_regex=settings.cors_origin_regex,
                    allow_credentials=False,
                    allow_methods=["GET"],
                    allow_headers=["Accept", "Content-Type"],
                    expose_headers=["X-Request-ID"],
                )
            ),
        )

    def openapi(self) -> dict[str, object]:
        if self.openapi_schema is None:
            schema = get_openapi(
                title=self.title,
                version=self.version,
                routes=self.routes,
            )
            remove_validation_responses(schema)
            self.openapi_schema = schema
        return self.openapi_schema


def create_app(
    settings: ApiSettings | None = None,
    *,
    database_settings: DatabaseSettings | DatabaseEnvironment | None = None,
    logging_settings: LoggingSettings | None = None,
    resource_factory: Callable[
        [DatabaseSettings], DatabaseResources
    ] = create_database_resources,
) -> FastAPI:
    settings = ApiSettings() if settings is None else settings

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        if logging_settings is not None:
            handler = configure_logging(logging_settings)
            configure_api_host_logging(logging_settings, handler)
        selected_database = (
            get_database_settings(dict(database_settings.values))
            if isinstance(database_settings, DatabaseEnvironment)
            else database_settings
        )
        if selected_database is None:
            yield
            return
        resources = resource_factory(selected_database)
        application.state.database = resources
        primary: BaseException | None = None
        try:
            yield
        except BaseException as error:
            primary = error
            raise
        finally:
            application.state.database = None
            try:
                async with asyncio.timeout(selected_database.cleanup_timeout_seconds):
                    await asyncio.to_thread(resources.engine.dispose)
            except BaseException as cleanup:
                if primary is None:
                    raise
                retain_lifespan_cleanup(primary, cleanup)

    application = ContractFastAPI(
        title="TradeValue API", version="1.0.0", lifespan=lifespan
    )

    application.state.api_settings = settings
    application.state.logging_settings = (
        LoggingSettings() if logging_settings is None else logging_settings
    )

    @application.exception_handler(ApiProblem)
    async def api_problem_handler(request: Request, exc: ApiProblem):
        if exc.status >= 500:
            report_request_error(request.scope, exc)
        return build_api_error(exc.status, exc.code, exc.message, exc.details)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        details: dict[str, list[str]] = {}
        for issue in exc.errors():
            field = str(issue["loc"][-1])
            details.setdefault(field, []).append(issue["msg"])
        return build_api_error(
            400, "INVALID_REQUEST", "The request parameters are invalid.", details
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_handler(request: Request, exc: SQLAlchemyError):
        report_request_error(request.scope, exc)
        return build_api_error(
            503, "DATABASE_UNAVAILABLE", "The data service is temporarily unavailable."
        )

    @application.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        report_request_error(request.scope, exc)
        return build_api_error(
            500, "INTERNAL_ERROR", "The API could not complete this request."
        )

    application.include_router(create_router())

    return application


def create_runtime_app() -> FastAPI:
    values = load_environment()
    logging_settings = read_logging_settings(values)
    return create_app(
        get_api_settings(values),
        database_settings=DatabaseEnvironment(values=tuple(values.items())),
        logging_settings=logging_settings,
    )
