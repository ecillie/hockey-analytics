"""Owned SQLAlchemy resource and ASGI protocol probes for lifespan failures."""

import asyncio
from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from starlette.types import ASGIApp, Message

from app.config import DatabaseSettings
from app.database import DatabaseResources
from app.shared.tests.resources import ResourceProbe


@dataclass(slots=True, kw_only=True, frozen=True)
class LifecycleResources:
    engine: Engine
    probe: ResourceProbe

    def create_resources(self, settings: DatabaseSettings) -> DatabaseResources:
        assert settings.database_url == str(self.engine.url)
        self.probe.record_operation("construct")
        return DatabaseResources(
            engine=self.engine, sessions=sessionmaker(bind=self.engine)
        )

    def record_disposal(self, engine: Engine) -> None:
        assert engine is self.engine
        self.probe.record_operation("dispose")


@dataclass(slots=True, kw_only=True, frozen=True)
class LifecycleTransport:
    incoming: list[Message] = field(default_factory=list)
    outgoing: list[Message] = field(default_factory=list)
    receive_failure: BaseException | None = None
    reads: list[bool] = field(default_factory=list)

    async def receive(self) -> Message:
        self.reads.append(True)
        if len(self.reads) > 1 and self.receive_failure is not None:
            raise self.receive_failure
        return self.incoming.pop(0)

    async def send(self, message: Message) -> None:
        self.outgoing.append(message)


async def exercise_lifespan(
    application: ASGIApp, transport: LifecycleTransport
) -> None:
    async with asyncio.timeout(5):
        await application(
            {"type": "lifespan", "state": {}}, transport.receive, transport.send
        )
