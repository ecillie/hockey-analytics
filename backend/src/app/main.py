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

from app.api.routes import create_router
from app.api.service import ApiProblem
from app.config import (
    ApiSettings,
    DatabaseSettings,
    get_api_settings,
    get_database_settings,
    load_environment,
)
from app.database import DatabaseResources, create_database_resources


logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


class ContractFastAPI(FastAPI):
    def openapi(self) -> dict[str, object]:
        if self.openapi_schema is None:
            schema = get_openapi(
                title=self.title,
                version=self.version,
                routes=self.routes,
            )
            for path in schema["paths"].values():
                for operation in path.values():
                    if isinstance(operation, dict):
                        operation.get("responses", {}).pop("422", None)
            self.openapi_schema = schema
        return self.openapi_schema


def create_app(
    settings: ApiSettings | None = None,
    *,
    database_settings: DatabaseSettings | None = None,
    resource_factory: Callable[
        [DatabaseSettings], DatabaseResources
    ] = create_database_resources,
) -> FastAPI:
    settings = ApiSettings() if settings is None else settings

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        if database_settings is None:
            yield
            return
        resources = resource_factory(database_settings)
        application.state.database = resources
        try:
            yield
        finally:
            application.state.database = None
            async with asyncio.timeout(database_settings.cleanup_timeout_seconds):
                await asyncio.to_thread(resources.engine.dispose)

    application = ContractFastAPI(
        title="TradeValue API", version="1.0.0", lifespan=lifespan
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    @application.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem):
        return _error(exc.status, exc.code, exc.message, exc.details)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        details: dict[str, list[str]] = {}
        for issue in exc.errors():
            field = str(issue["loc"][-1])
            details.setdefault(field, []).append(issue["msg"])
        return _error(
            400, "INVALID_REQUEST", "The request parameters are invalid.", details
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_handler(_request: Request, exc: SQLAlchemyError):
        logger.exception("Database request failed", exc_info=exc)
        return _error(
            503, "DATABASE_UNAVAILABLE", "The data service is temporarily unavailable."
        )

    @application.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled API error", exc_info=exc)
        return _error(500, "INTERNAL_ERROR", "The API could not complete this request.")

    application.include_router(create_router())

    return application


def create_runtime_app() -> FastAPI:
    values = load_environment()
    return create_app(
        get_api_settings(values), database_settings=get_database_settings(values)
    )
