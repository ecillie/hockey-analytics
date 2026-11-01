"""Read-only verification routes added to the production application factory."""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from app.main import create_runtime_app


async def parse_number(key: str) -> Response:
    return PlainTextResponse(str(int(key)))


async def stream_chunks() -> AsyncGenerator[bytes]:
    yield b"first_chunk"
    int("stream_failure_secret")


async def stream_response() -> Response:
    return StreamingResponse(stream_chunks(), media_type="text/plain")


def create_probe_app() -> FastAPI:
    application = create_runtime_app()
    application.add_api_route(
        "/probe/number/{key}", parse_number, include_in_schema=False
    )
    application.add_api_route("/probe/stream", stream_response, include_in_schema=False)
    return application
