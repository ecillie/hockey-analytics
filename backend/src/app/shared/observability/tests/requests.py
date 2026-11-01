"""ASGI probes for streaming delivery and request-local state ownership."""

import asyncio
from dataclasses import dataclass, field

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from app.shared.observability.domain import RequestContext
from app.shared.observability.requests import (
    RequestLoggingMiddleware,
    get_request_context,
)


async def respond_to_probe(request: Request) -> Response:
    return Response(request.url.path)


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingTransport:
    messages: list[Message] = field(default_factory=list)
    reads: list[bool] = field(default_factory=list)

    async def receive(self) -> Message:
        self.reads.append(True)
        return {"type": "http.request", "body": b"request_secret", "more_body": False}

    async def send(self, message: Message) -> None:
        self.messages.append(message)


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestApplication:
    transport: RecordingTransport
    status: int = 200
    route_path: str = "/api/probe/{key}"
    failure: BaseException | None = None
    contexts: list[RequestContext | None] = field(default_factory=list)
    delivery_counts: list[int] = field(default_factory=list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["route"] = Route(self.route_path, endpoint=respond_to_probe)
        self.contexts.append(get_request_context(scope))
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"X-Request-ID", b"upstream_secret")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"response_secret",
                "more_body": True,
            }
        )
        self.delivery_counts.append(len(self.transport.messages))
        await asyncio.sleep(0)
        if self.failure is not None:
            raise self.failure
        await send(
            {"type": "http.response.body", "body": b"final_chunk", "more_body": False}
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class RequestScenario:
    application: RequestApplication
    scope: Scope

    async def execute(self) -> None:
        async with asyncio.timeout(5):
            await RequestLoggingMiddleware(app=self.application)(
                self.scope,
                self.application.transport.receive,
                self.application.transport.send,
            )

    def run(self) -> None:
        asyncio.run(self.execute())


def build_request_scope(*, path: str = "/api/probe/raw_secret") -> Scope:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"x-request-id", b"caller_secret")],
        "query_string": b"token=query_secret",
        "state": {},
    }


async def exercise_concurrent_requests(
    application: RequestApplication,
    scopes: tuple[Scope, ...],
    transports: tuple[RecordingTransport, ...],
) -> None:
    middleware = RequestLoggingMiddleware(app=application)
    async with asyncio.timeout(5):
        async with asyncio.TaskGroup() as tasks:
            for scope, transport in zip(scopes, transports, strict=True):
                tasks.create_task(middleware(scope, transport.receive, transport.send))
