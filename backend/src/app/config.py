"""Validated settings and explicit, non-mutating environment loading."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto
import os
from pathlib import Path
import re
from urllib.parse import quote

from dotenv.main import DotEnv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(RuntimeError):
    def __init__(self, *, field: str, reason: str) -> None:
        super().__init__(f"{field} {reason}")
        self.field = field
        self.reason = reason


class AppEnvironment(StrEnum):
    DEV = auto()
    NONPROD = auto()
    PROD = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseSettings:
    environment: AppEnvironment
    database_url: str = field(repr=False)
    connect_timeout_seconds: int = 10
    pool_size: int = 2
    max_overflow: int = 3
    pool_recycle_seconds: int = 300
    cleanup_timeout_seconds: float = 10.0


@dataclass(slots=True, kw_only=True, frozen=True)
class ApiSettings:
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    cors_origin_regex: str | None = None


def load_environment(*, env_file: Path | None = None) -> dict[str, str]:
    exported = dict(os.environ)
    selected = (
        env_file
        if env_file is not None
        else Path(
            exported.get(
                "TRADEVALUE_ENV_FILE",
                Path(__file__).resolve().parents[2].joinpath(".env"),
            )
        )
    )
    values = {
        key: value
        for key, value in DotEnv(selected, override=False).dict().items()
        if value is not None
    }
    return values | exported


def get_api_settings(values: Mapping[str, str] | None = None) -> ApiSettings:
    values = load_environment() if values is None else values
    origins = tuple(
        origin.strip()
        for origin in values.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip() != ""
    )
    if len(origins) == 0:
        raise ConfigurationError(
            field="CORS_ORIGINS", reason="must contain at least one origin"
        )
    configured_regex = values.get("CORS_ORIGIN_REGEX", "").strip()
    origin_regex = None if configured_regex == "" else configured_regex
    if origin_regex is not None:
        try:
            re.compile(origin_regex)
        except re.error as error:
            raise ConfigurationError(
                field="CORS_ORIGIN_REGEX", reason="must be a valid regular expression"
            ) from error
    return ApiSettings(cors_origins=origins, cors_origin_regex=origin_regex)


def read_integer(
    values: Mapping[str, str], name: str, default: int, minimum: int
) -> int:
    configured = values.get(name, str(default)).strip()
    try:
        value = int(str(default) if configured == "" else configured)
    except ValueError as error:
        raise ConfigurationError(field=name, reason="must be an integer") from error
    if value < minimum:
        raise ConfigurationError(
            field=name,
            reason="must be nonnegative" if minimum == 0 else "must be positive",
        )
    return value


def resolve_development_database_url(values: Mapping[str, str]) -> str:
    user = values.get("DB_USER", "").strip()
    database = values.get("DB_NAME", "").strip()
    if user == "" or database == "":
        raise ConfigurationError(
            field="DATABASE_URL",
            reason="requires DEV_DATABASE_URL, DATABASE_URL, or both DB_USER and DB_NAME for ENV=dev",
        )
    port = read_integer(values, "DB_PORT", 5432, 1)
    if port > 65535:
        raise ConfigurationError(field="DB_PORT", reason="must be between 1 and 65535")
    credentials = quote(user, safe="")
    if (password := values.get("DB_PASSWORD", "")) != "":
        credentials += f":{quote(password, safe='')}"
    configured_host = values.get("DB_HOST", "localhost").strip()
    host = "localhost" if configured_host == "" else configured_host
    return f"postgresql://{credentials}@{host}:{port}/{quote(database, safe='')}"


def get_database_settings(values: Mapping[str, str] | None = None) -> DatabaseSettings:
    values = load_environment() if values is None else values
    try:
        environment = AppEnvironment(values.get("ENV", "").strip().lower())
    except ValueError as error:
        raise ConfigurationError(
            field="ENV", reason="must be one of: dev, nonprod, prod"
        ) from error
    scoped_name = f"{environment.value.upper()}_DATABASE_URL"
    scoped_url = values.get(scoped_name, "").strip()
    database_url = (
        values.get("DATABASE_URL", "").strip() if scoped_url == "" else scoped_url
    )
    if database_url == "":
        if environment is not AppEnvironment.DEV:
            raise ConfigurationError(
                field=scoped_name,
                reason=f"or DATABASE_URL is required for ENV={environment.value}",
            )
        database_url = resolve_development_database_url(values)
    try:
        make_url(database_url)
    except (ArgumentError, ValueError) as error:
        raise ConfigurationError(
            field="DATABASE_URL", reason="must be a valid database URL"
        ) from error
    return DatabaseSettings(
        environment=environment,
        database_url=database_url,
        connect_timeout_seconds=read_integer(values, "DB_CONNECT_TIMEOUT", 10, 1),
        pool_size=read_integer(values, "DB_POOL_SIZE", 2, 1),
        max_overflow=read_integer(values, "DB_MAX_OVERFLOW", 3, 0),
        pool_recycle_seconds=read_integer(values, "DB_POOL_RECYCLE_SECONDS", 300, 1),
    )
