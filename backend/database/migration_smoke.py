"""Minimal post-migration API smoke checks against an empty migrated database."""

import argparse
import logging
from collections.abc import Sequence

from app.config import get_database_settings
from app.database import database_resources
from app.main import create_runtime_app
from app.shared.cli import ExitCode
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
        raise RuntimeError(
            "initial reference data is incomplete: "
            f"sources={source_codes} seasons={season_count}"
        )


def smoke_checks(client) -> None:
    checks = {
        "/api/health": valid_health,
        "/api/seasons": valid_seasons,
        "/api/teams": valid_teams,
    }
    for path, validate in checks.items():
        response = client.get(path)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200 or not validate(body):
            raise RuntimeError(
                f"post-migration smoke check failed for {path}: "
                f"status={response.status_code} body={response.text}"
            )


def valid_health(body: object) -> bool:
    return body == {"status": "ok"}


def valid_seasons(body: object) -> bool:
    return (
        isinstance(body, dict)
        and bool(body.get("availableSeasons"))
        and isinstance(body.get("currentSeason"), int)
        and body["currentSeason"] >= 2005
    )


def valid_teams(body: object) -> bool:
    return body == []


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        return execute_command()
    except Exception:
        logger.exception("Database check failed")
        return ExitCode.FAILURE


def execute_command() -> int:
    with (
        database_resources(get_database_settings()) as resources,
        resources.sessions() as session,
    ):
        validate_reference_data(session)
        print("PASS initial reference data")

    with TestClient(create_runtime_app()) as client:
        smoke_checks(client)
        print("PASS /api/health")
        print("PASS /api/seasons")
        print("PASS /api/teams")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
