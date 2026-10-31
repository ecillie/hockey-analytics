"""Source transport protocols and explicitly owned retry sessions."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from _thread import LockType
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceHttpOptions:
    json_timeout: float = 30.0
    csv_timeout: float = 60.0
    retry_total: int = 4
    retry_backoff: float = 0.6
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    user_agent: str = "TradeValue/1.0 (NHL analytics data ingestion)"


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

    def get_json(
        self,
        url: str,
        *,
        timeout: float | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        timeout = self.options.json_timeout if timeout is None else timeout
        response = (
            self.session.get(url, timeout=timeout)
            if params is None
            else self.session.get(url, params=params, timeout=timeout)
        )
        response.raise_for_status()
        return response.json()

    def get_csv(self, url: str, *, timeout: float | None = None) -> str:
        timeout = self.options.csv_timeout if timeout is None else timeout
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text


def http_session(options: SourceHttpOptions | None = None) -> requests.Session:
    options = SourceHttpOptions() if options is None else options
    session = requests.Session()
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
    return session


@contextmanager
def open_source_client(
    options: SourceHttpOptions | None = None,
) -> Generator[SourceClient]:
    options = SourceHttpOptions() if options is None else options
    with http_session(options) as session:
        yield SessionSourceClient(session=session, options=options)


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
