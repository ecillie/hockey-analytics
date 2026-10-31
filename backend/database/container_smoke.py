"""Validate the externally served API from the built backend container."""

import argparse
import json
import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from app.shared.cli import CommandOptionError, ExitCode


def valid_health(body: object) -> bool:
    return body == {"status": "ok"}


def valid_seasons(body: object) -> bool:
    return (
        isinstance(body, dict)
        and bool(body.get("availableSeasons"))
        and isinstance(body.get("currentSeason"), int)
    )


def valid_teams(body: object) -> bool:
    return isinstance(body, list)


type ResponseCheck = tuple[str, Callable[[object], bool]]


def response_checks() -> tuple[ResponseCheck, ...]:
    return (
        ("/api/health", valid_health),
        ("/api/seasons", valid_seasons),
        ("/api/teams", valid_teams),
    )


def request_json(url: str, timeout: float) -> tuple[int, object, str]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - caller supplies CI URL
            text = response.read().decode("utf-8")
            return response.status, json.loads(text), text
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, text


def validate(base_url: str, *, attempts: int, delay: float, timeout: float) -> None:
    base_url = base_url.rstrip("/")
    last_error = readiness_error(base_url, timeout)
    attempt = 1
    while last_error is not None and attempt < attempts:
        time.sleep(delay)
        last_error = readiness_error(base_url, timeout)
        attempt += 1
    if last_error is not None:
        raise RuntimeError(
            f"container did not become healthy after {attempts} attempts: {last_error}"
        )

    for path, check in response_checks():
        status, body, text = request_json(f"{base_url}{path}", timeout)
        if status != 200 or not check(body):
            raise RuntimeError(
                f"container smoke check failed for {path}: status={status} body={text}"
            )
        print(f"PASS {path}")


def readiness_error(base_url: str, timeout: float) -> Exception | None:
    try:
        status, body, text = request_json(f"{base_url}/api/health", timeout)
    except (URLError, OSError, json.JSONDecodeError) as exc:
        return exc
    if status != 200 or not valid_health(body):
        return RuntimeError(f"health returned status={status} body={text}")
    return None


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    base_url: str
    attempts: int
    delay: float
    timeout: float


logger = logging.getLogger(__name__)


def find_option_violation(options: CommandOptions) -> CommandOptionError | None:
    if options.attempts < 1:
        return CommandOptionError(option="attempts", requirement="must be positive")
    if not math.isfinite(options.delay) or options.delay < 0:
        return CommandOptionError(
            option="delay", requirement="must be finite and nonnegative"
        )
    if not math.isfinite(options.timeout) or options.timeout <= 0:
        return CommandOptionError(
            option="timeout", requirement="must be finite and positive"
        )
    try:
        url = urlsplit(options.base_url)
        valid_url = (
            url.scheme in ("http", "https")
            and url.hostname is not None
            and url.port != 0
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        return CommandOptionError(
            option="base-url",
            requirement="must be an HTTP or HTTPS URL with a host and valid port",
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = CommandOptions(**vars(parser.parse_args(argv)))
    if violation := find_option_violation(options):
        parser.error(str(violation))
    logging.basicConfig(level=logging.INFO)
    try:
        return execute_command(options)
    except Exception:
        logger.exception("Command failed")
        return ExitCode.FAILURE


def execute_command(options: CommandOptions) -> int:
    validate(
        options.base_url,
        attempts=options.attempts,
        delay=options.delay,
        timeout=options.timeout,
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
