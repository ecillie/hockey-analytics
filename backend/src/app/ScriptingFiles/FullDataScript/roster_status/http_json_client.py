"""Bounded synchronous JSON/JSONP transport for roster feeds."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import TypeAdapter, ValidationError

from app.ScriptingFiles.FullDataScript.roster_status.domain import HttpOptions
from app.ScriptingFiles.FullDataScript.roster_status.errors import (
    InvalidJsonResponseError,
)


@runtime_checkable
class JsonClient(Protocol):
    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> object: ...


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
        with urlopen(request, timeout=self.options.timeout_seconds) as response:
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
