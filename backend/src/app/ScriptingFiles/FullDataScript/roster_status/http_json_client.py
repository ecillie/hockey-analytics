"""Bounded synchronous JSON/JSONP transport for roster feeds."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.ScriptingFiles.FullDataScript.roster_status.domain import HttpOptions
from app.shared.cleanup import complete_cleanup
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    InvalidJsonResponseError,
    FeedFetchError,
)


@runtime_checkable
class JsonClient(Protocol):
    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> object: ...


def fetch_validated[T: BaseModel](
    client: JsonClient,
    url: str,
    model: type[T],
    source: str,
    params: Mapping[str, str] | None = None,
) -> T:
    try:
        return model.model_validate(client.get_json(url, params))
    except (
        URLError,
        OSError,
        UnicodeError,
        InvalidJsonResponseError,
        ValidationError,
    ) as exc:
        reason = (
            "response shape is invalid"
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        raise FeedFetchError(source=source, reason=reason) from exc


@dataclass(slots=True, kw_only=True, frozen=True)
class JsonHttpClient:
    options: HttpOptions = field(default_factory=HttpOptions)

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> object:
        if params is not None and len(params) > 0:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json, text/javascript",
                "User-Agent": self.options.user_agent,
            },
        )
        try:
            response = urlopen(request, timeout=self.options.timeout_seconds)
        except HTTPError as error:
            complete_cleanup((error.close,), error)
            raise
        with response:
            body = response.read().decode("utf-8")
        return decode_json_or_jsonp(body)


def decode_json_or_jsonp(body: str) -> dict[str, object]:
    payload = body.strip()
    if not payload.startswith("{"):
        callback = re.fullmatch(
            r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*\((.*)\)\s*;?",
            payload,
            flags=re.DOTALL,
        )
        if callback is None:
            raise InvalidJsonResponseError(
                reason="expected a JSON object or callback-wrapped object"
            )
        payload = callback.group(1)
    try:
        return TypeAdapter(dict[str, object]).validate_json(payload)
    except ValidationError as exc:
        raise InvalidJsonResponseError(
            reason="payload must be a valid JSON object"
        ) from exc
