"""Minimal post-migration API smoke checks against an empty migrated database."""

import argparse
import logging
from collections.abc import Sequence

from app.config import get_database_settings
from app.database import open_database_resources
from app.main import create_runtime_app
from app.shared.smoke import (
    is_valid_health_response,
    is_valid_seasons_response as valid_season_payload,
    SmokeResponseError,
    ReferenceDataError,
)
from app.shared.cli import ExitCode
from app.config import load_environment
from app.shared.observability.domain import CommandOutcome, read_logging_settings
from app.shared.observability.errors import LoggingSettingsError
from app.shared.observability.services import (
    configure_logging,
    start_command,
    configure_command_exceptions,
    finish_command,
)
from fastapi.testclient import TestClient
from sqlalchemy import text


def validate_reference_data(session) -> None:
    source_codes = (
        session.execute(text("SELECT code FROM data_sources ORDER BY code"))
        .scalars()
        .all()
    )
    season_count = session.execute(text("SELECT COUNT(*) FROM seasons")).scalar_one()
    if (
        source_codes != ["capspace", "capwages", "moneypuck", "nhl"]
        or season_count != 22
    ):
        raise ReferenceDataError(sources=list(source_codes), seasons=season_count)


def build_smoke_checks(client) -> None:
    checks = {
        "/api/health": is_valid_health_response,
        "/api/seasons": is_valid_seasons_response,
        "/api/teams": is_valid_teams_response,
    }
    for path, validate in checks.items():
        response = client.get(path)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200 or not validate(body):
            raise SmokeResponseError(
                operation="post-migration",
                path=path,
                status=response.status_code,
                body=response.text,
            )


def is_valid_seasons_response(body: object) -> bool:
    if not valid_season_payload(body) or not isinstance(body, dict):
        return False
    return body["currentSeason"] >= 2005


def is_valid_teams_response(body: object) -> bool:
    return body == []


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    try:
        settings = read_logging_settings(load_environment())
    except LoggingSettingsError as error:
        parser.error(str(error))
    configure_logging(settings)
    context = start_command("migration_smoke")
    configure_command_exceptions(context)
    try:
        result = execute_command()
    except Exception:
        logger.exception(
            "Database check failed", extra=context.fields | {"event": "command.failed"}
        )
        finish_command(context, CommandOutcome.FAILED)
        return ExitCode.FAILURE
    finish_command(context, CommandOutcome.COMPLETED)
    return result


def execute_command() -> int:
    with (
        open_database_resources(get_database_settings()) as resources,
        resources.sessions() as session,
    ):
        validate_reference_data(session)
        print("PASS initial reference data")

    with TestClient(create_runtime_app()) as client:
        build_smoke_checks(client)
        print("PASS /api/health")
        print("PASS /api/seasons")
        print("PASS /api/teams")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
