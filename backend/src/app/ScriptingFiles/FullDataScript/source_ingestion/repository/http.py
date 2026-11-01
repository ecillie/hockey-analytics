"""Source transport protocols and explicitly owned retry sessions."""

from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from _thread import LockType
from threading import Lock

import requests
from app.shared.cleanup import complete_cleanup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.response import HTTPResponse
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.shared.observability.domain import LogLevel


from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    SourceHttpOptions as SourceHttpOptions,
)


@runtime_checkable
class SourceResponse(Protocol):
    @property
    def text(self) -> str: ...

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


@runtime_checkable
class SourceSession(Protocol):
    def get(
        self, url: str, *, timeout: float, params: Mapping[str, str | int] | None = None
    ) -> SourceResponse: ...


@runtime_checkable
class SourceClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        timeout: float | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> object: ...
    def get_csv(self, url: str, *, timeout: float | None = None) -> str: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionSourceClient:
    session: SourceSession
    options: SourceHttpOptions = field(default_factory=SourceHttpOptions)
    context: IngestionContext | None = None

    def get_json(
        self,
        url: str,
        *,
        timeout: float | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        timeout = self.options.json_timeout if timeout is None else timeout
        report_ingestion_progress(
            self.context, event="ingestion.request_started", level=LogLevel.DEBUG
        )
        response = (
            self.session.get(url, timeout=timeout)
            if params is None
            else self.session.get(url, params=params, timeout=timeout)
        )
        response.raise_for_status()
        report_request_recovery(response, self.context)
        return response.json()

    def get_csv(self, url: str, *, timeout: float | None = None) -> str:
        timeout = self.options.csv_timeout if timeout is None else timeout
        report_ingestion_progress(
            self.context, event="ingestion.request_started", level=LogLevel.DEBUG
        )
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        report_request_recovery(response, self.context)
        return response.text


def report_request_recovery(response: object, context: IngestionContext | None) -> None:
    if context is None or type(response) is not requests.Response:
        return
    raw = response.raw
    if type(raw) is not HTTPResponse or type(raw.retries) is not Retry:
        return
    history = raw.retries.history
    if type(history) is not tuple:
        return
    attempts = len(history) + 1
    if attempts > 1:
        report_ingestion_progress(
            context,
            event="ingestion.request_recovered",
            values={"attempt": attempts},
            level=LogLevel.WARNING,
        )


def open_http_session(options: SourceHttpOptions | None = None) -> requests.Session:
    options = SourceHttpOptions() if options is None else options
    session = requests.Session()
    try:
        configure_http_session(session, options)
    except BaseException as primary:
        complete_cleanup((session.close,), primary)
        raise
    return session


def configure_http_session(
    session: requests.Session, options: SourceHttpOptions
) -> None:
    retry = Retry(
        total=options.retry_total,
        backoff_factor=options.retry_backoff,
        status_forcelist=options.retry_statuses,
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": options.user_agent,
            "Accept": "application/json,text/csv,text/html",
        }
    )


@contextmanager
def open_source_client(
    options: SourceHttpOptions | None = None,
    *,
    context: IngestionContext | None = None,
) -> Generator[SourceClient]:
    options = SourceHttpOptions() if options is None else options
    with open_http_session(options) as session:
        yield SessionSourceClient(session=session, options=options, context=context)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContextualSourceClientFactory:
    context: IngestionContext | None
    options: SourceHttpOptions = field(default_factory=SourceHttpOptions)

    def __call__(self) -> AbstractContextManager[SourceClient]:
        return open_source_client(self.options, context=self.context)


@dataclass(slots=True, kw_only=True, frozen=True)
class SynchronizedSourceClient:
    client: SourceClient
    lock: LockType = field(default_factory=Lock)

    def get_json(
        self,
        url: str,
        *,
        timeout: float | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        with self.lock:
            return self.client.get_json(url, timeout=timeout, params=params)

    def get_csv(self, url: str, *, timeout: float | None = None) -> str:
        with self.lock:
            return self.client.get_csv(url, timeout=timeout)
