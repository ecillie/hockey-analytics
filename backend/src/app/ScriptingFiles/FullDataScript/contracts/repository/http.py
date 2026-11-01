"""Profile transport ownership for concurrent contract fetching."""

import math
import time
from _thread import LockType
from collections.abc import Callable, Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

import requests
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.shared.observability.domain import LogLevel
from app.ScriptingFiles.FullDataScript.contracts.domain import (
    AbsenceReason,
    Candidate,
    ContractsAbsent,
    FailureReason,
    ProfileFailure,
    ProfileResult,
    ProfileSource,
    build_parsed_profile,
)
from app.ScriptingFiles.FullDataScript.contracts.errors import CapSpaceError
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    find_profile_http_violation,
)
from app.ScriptingFiles.FullDataScript.contracts.domain import ProfileHttpOptions
from app.ScriptingFiles.FullDataScript.contracts.policy import (
    matches_capwages_document as _capwages_document_matches,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas import parse_source_document
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_capspace_page,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.contracts import (
    parse_contract_document as _parse_contract_document,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository.http import (
    open_http_session,
    open_owned_http_session,
    report_request_recovery,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    build_player_slug as _slug_from_name,
)


@runtime_checkable
class ProfileResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def headers(self) -> Mapping[str, str]: ...


@runtime_checkable
class ProfileSession(Protocol):
    def get(self, url: str, *, timeout: float) -> ProfileResponse: ...


@runtime_checkable
class ActiveProfileResponse(Protocol):
    @property
    def text(self) -> str: ...

    def raise_for_status(self) -> None: ...


@runtime_checkable
class ActiveProfileSession(Protocol):
    def get(self, url: str, *, timeout: float) -> ActiveProfileResponse: ...


type ProfileSessionFactory = Callable[[], AbstractContextManager[ProfileSession]]


@contextmanager
def open_profile_session() -> Generator[ProfileSession]:
    with open_owned_http_session(open_http_session()) as session:
        yield session


@dataclass(slots=True, kw_only=True, frozen=True)
class SynchronizedProfileSession:
    session: ProfileSession
    lock: LockType = field(default_factory=Lock)

    def get(self, url: str, *, timeout: float) -> ProfileResponse:
        with self.lock:
            return self.session.get(url, timeout=timeout)


@dataclass(slots=True, kw_only=True, frozen=True)
class BorrowedProfileSessionFactory:
    session: ProfileSession

    @contextmanager
    def __call__(self) -> Generator[ProfileSession]:
        yield self.session


def calculate_retry_delay(
    response: ProfileResponse, attempt: int, options: ProfileHttpOptions
) -> float:
    fallback = min(2**attempt, options.maximum_backoff)
    value = response.headers.get("Retry-After")
    if value is None or value == "":
        return fallback
    try:
        delay = float(value)
    except ValueError:
        return fallback
    if not math.isfinite(delay) or delay < 0:
        return fallback
    return min(delay, options.maximum_retry_after)


def parse_capspace_response(
    response: ProfileResponse, candidate: Candidate, url: str
) -> ProfileResult:
    returned_url = getattr(response, "url", "")
    if (
        isinstance(returned_url, str)
        and returned_url != ""
        and urlsplit(returned_url).path.rstrip("/") != f"/person/nhl:{candidate.nhl_id}"
    ):
        return ProfileResult(
            candidate=candidate,
            url=url,
            html=response.text,
            outcome=ProfileFailure(
                reason=FailureReason.PARSE_FAILED,
                detail="CapSpace redirected to a different player identity",
            ),
        )
    try:
        contracts = parse_capspace_page(response.text, expected_nhl_id=candidate.nhl_id)
    except CapSpaceError as failure:
        return ProfileResult(
            candidate=candidate,
            url=url,
            html=response.text,
            outcome=ProfileFailure(
                reason=FailureReason.PARSE_FAILED, detail=str(failure)
            ),
        )
    return build_parsed_profile(
        candidate=candidate, url=url, html=response.text, contracts=contracts
    )


def request_capspace_attempt(
    session: ProfileSession,
    candidate: Candidate,
    attempt: int,
    options: ProfileHttpOptions,
    *,
    context: IngestionContext | None = None,
) -> ProfileResult | None:
    url = f"{options.capspace_base_url}/person/nhl:{candidate.nhl_id}"
    try:
        response = session.get(url, timeout=options.timeout)
    except requests.RequestException as failure:
        if attempt + 1 == options.max_attempts:
            return ProfileResult(
                candidate=candidate,
                url=url,
                outcome=ProfileFailure(
                    reason=FailureReason.FAILED,
                    detail="timeout"
                    if isinstance(failure, requests.Timeout)
                    else str(failure),
                ),
            )
        report_ingestion_progress(
            context,
            event="ingestion.retry_scheduled",
            values={"attempt": attempt + 2},
            level=LogLevel.DEBUG,
        )
        time.sleep(min(2**attempt, options.maximum_backoff))
        return None
    report_request_recovery(response, context)
    if response.status_code == 404:
        return ProfileResult(
            candidate=candidate,
            url=url,
            outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND),
        )
    if response.status_code == 200:
        return parse_capspace_response(response, candidate, url)
    if (
        response.status_code not in options.retryable_statuses
        or attempt + 1 == options.max_attempts
    ):
        return ProfileResult(
            candidate=candidate,
            url=url,
            outcome=ProfileFailure(
                reason=FailureReason.FAILED, detail=f"HTTP {response.status_code}"
            ),
        )
    report_ingestion_progress(
        context,
        event="ingestion.retry_scheduled",
        values={"attempt": attempt + 2, "status": response.status_code},
        level=LogLevel.DEBUG,
    )
    time.sleep(calculate_retry_delay(response, attempt, options))
    return None


def fetch_profile(
    session: ProfileSession,
    candidate: Candidate,
    *,
    max_attempts: int | None = None,
    options: ProfileHttpOptions | None = None,
    context: IngestionContext | None = None,
) -> ProfileResult:
    options = ProfileHttpOptions() if options is None else options
    if max_attempts is not None:
        options = replace(options, max_attempts=max_attempts)
    if violation := find_profile_http_violation(options):
        raise violation
    if candidate.nhl_id in (None, ""):
        return ProfileResult(
            candidate=candidate,
            url="",
            outcome=ContractsAbsent(reason=AbsenceReason.NO_NHL_ID),
        )
    attempts = (
        result
        for attempt in range(options.max_attempts)
        if (
            result := request_capspace_attempt(
                session, candidate, attempt, options, context=context
            )
        )
        is not None
    )
    return next(attempts)


def covers_target_seasons(result: ProfileResult) -> set[int]:
    return set(result.target_seasons_covered)


def matches_capwages_identity(html: str, candidate: Candidate, url: str) -> bool:
    return _capwages_document_matches(parse_source_document(html), candidate, url)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContinueSlugSearch:
    result: ProfileResult | None = None


def request_capwages_slug(
    session: ProfileSession,
    candidate: Candidate,
    url: str,
    *,
    is_base: bool,
    options: ProfileHttpOptions,
    context: IngestionContext | None = None,
) -> ProfileResult | ContinueSlugSearch:
    try:
        response = session.get(url, timeout=options.timeout)
    except requests.RequestException as failure:
        return ContinueSlugSearch(
            result=ProfileResult(
                candidate=candidate,
                url=url,
                source_code=ProfileSource.CAPWAGES,
                outcome=ProfileFailure(
                    reason=FailureReason.FAILED,
                    detail="timeout"
                    if isinstance(failure, requests.Timeout)
                    else str(failure),
                ),
            )
        )
    report_request_recovery(response, context)
    if response.status_code == 404:
        if is_base:
            return ProfileResult(
                candidate=candidate,
                url=url,
                source_code=ProfileSource.CAPWAGES,
                outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND),
            )
        return ContinueSlugSearch()
    if response.status_code != 200:
        return ProfileResult(
            candidate=candidate,
            url=url,
            source_code=ProfileSource.CAPWAGES,
            outcome=ProfileFailure(
                reason=FailureReason.FAILED, detail=f"HTTP {response.status_code}"
            ),
        )
    document = parse_source_document(response.text)
    pages = document.next_data
    if not _capwages_document_matches(document, candidate, url, pages=pages):
        return ContinueSlugSearch(
            result=ProfileResult(
                candidate=candidate,
                url=url,
                html=response.text,
                source_code=ProfileSource.CAPWAGES,
                outcome=ProfileFailure(
                    reason=FailureReason.PARSE_FAILED,
                    detail="CapWages profile identity could not be validated",
                ),
            )
        )
    try:
        contracts = _parse_contract_document(
            document, expected_nhl_id=candidate.nhl_id, pages=pages
        )
    except CapSpaceError as failure:
        return ProfileResult(
            candidate=candidate,
            url=url,
            html=response.text,
            source_code=ProfileSource.CAPWAGES,
            outcome=ProfileFailure(
                reason=FailureReason.PARSE_FAILED, detail=str(failure)
            ),
        )
    return build_parsed_profile(
        candidate=candidate,
        url=url,
        html=response.text,
        source_code=ProfileSource.CAPWAGES,
        contracts=contracts,
    )


def fetch_capwages_profile(
    session: ProfileSession,
    candidate: Candidate,
    *,
    options: ProfileHttpOptions | None = None,
    context: IngestionContext | None = None,
) -> ProfileResult:
    options = ProfileHttpOptions() if options is None else options
    if violation := find_profile_http_violation(options):
        raise violation
    if candidate.nhl_id in (None, ""):
        return ProfileResult(
            candidate=candidate,
            url="",
            source_code=ProfileSource.CAPWAGES,
            outcome=ContractsAbsent(reason=AbsenceReason.NO_NHL_ID),
        )
    slug = _slug_from_name(f"{candidate.first_name} {candidate.last_name}")
    url = f"{options.capwages_base_url}/players/{slug}"
    if slug == "":
        return ProfileResult(
            candidate=candidate,
            url="",
            source_code=ProfileSource.CAPWAGES,
            outcome=ContractsAbsent(
                reason=AbsenceReason.NOT_FOUND,
                detail="player name cannot form a CapWages slug",
            ),
        )
    result: ProfileResult | None = None
    suffixes = iter(options.capwages_slug_suffixes)
    searching = True
    while searching and (suffix := next(suffixes, None)) is not None:
        attempt = request_capwages_slug(
            session,
            candidate,
            f"{url}{suffix}",
            is_base=suffix == "",
            options=options,
            context=context,
        )
        if isinstance(attempt, ProfileResult):
            result = attempt
            searching = False
        if isinstance(attempt, ContinueSlugSearch) and attempt.result is not None:
            result = attempt.result
    if result is not None:
        return result
    return ProfileResult(
        candidate=candidate,
        url=url,
        source_code=ProfileSource.CAPWAGES,
        outcome=ContractsAbsent(reason=AbsenceReason.NOT_FOUND),
    )


def fetch_profile_with_fallback(
    session: ProfileSession,
    candidate: Candidate,
    *,
    options: ProfileHttpOptions | None = None,
    context: IngestionContext | None = None,
) -> ProfileResult:
    options = ProfileHttpOptions() if options is None else options
    primary = fetch_profile(session, candidate, options=options, context=context)
    if primary.covers_target or candidate.nhl_id in (None, ""):
        return primary
    report_ingestion_progress(
        context,
        event="ingestion.fallback_started",
        values={"source": "capwages"},
        level=LogLevel.DEBUG,
    )
    fallback = fetch_capwages_profile(
        session, candidate, options=options, context=context
    )
    report_ingestion_progress(
        context,
        event="ingestion.fallback_finished",
        values={"source": "capwages", "outcome": fallback.status.value},
        level=LogLevel.DEBUG,
    )
    chosen = fallback if fallback.covers_target else primary
    return replace(
        chosen,
        fallback_attempted=True,
        primary_status=primary.status,
        fallback_status=fallback.status,
    )


type ActiveSessionFactory = Callable[[], AbstractContextManager[ActiveProfileSession]]


@contextmanager
def open_active_session() -> Generator[ActiveProfileSession]:
    with open_owned_http_session(open_http_session()) as session:
        yield session


@dataclass(slots=True, kw_only=True, frozen=True)
class SynchronizedActiveSession:
    session: ActiveProfileSession
    lock: LockType = field(default_factory=Lock)

    def get(self, url: str, *, timeout: float) -> ActiveProfileResponse:
        with self.lock:
            return self.session.get(url, timeout=timeout)


@dataclass(slots=True, kw_only=True, frozen=True)
class BorrowedActiveSessionFactory:
    session: ActiveProfileSession

    @contextmanager
    def __call__(self) -> Generator[ActiveProfileSession]:
        yield self.session
