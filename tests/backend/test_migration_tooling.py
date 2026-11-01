from app.shared.tests.fakes import build_migration_history, build_migration_revision
from pathlib import Path
import json
from collections.abc import Generator
from app.shared.tests.fakes import (
    CatalogDatabase,
    SavedApiClient,
    MigrationContext,
    MigrationBind,
    MigrationConnection,
    MigrationCursor,
    StageOutcome,
)
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from backend.database import (
    migration_preflight,
    migration_smoke,
    schema_snapshot,
    verify_migrations,
)
from app.shared.tests.fakes import (
    RevisionScenario,
    SnapshotScenario,
    build_http_response,
)
from app.shared.tests.migrations import (
    load_initial_revision,
    run_command,
)

ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIG = ROOT.joinpath("backend", "alembic.ini")
INITIAL_REVISION = ROOT.joinpath(
    "backend", "migrations", "versions", "20260910_0001_initial_schema.py"
)


class TestFrozenRevision:
    @pytest.fixture
    def revision(self):
        return load_initial_revision()

    def test_frozen_initial_schema_checksum_and_transaction_stripping(self, revision):
        body = revision._schema_body()
        assert "CREATE TYPE roster_status" in body
        assert "CREATE TABLE predictions" in body
        assert "\nBEGIN;" not in body
        assert "\nCOMMIT;" not in body

    @pytest.fixture
    def changed_revision(self, revision, tmp_path, monkeypatch):
        changed_schema = tmp_path.joinpath("schema.sql")
        changed_schema.write_text("BEGIN;\nSELECT 1;\nCOMMIT;\n", encoding="utf-8")
        monkeypatch.setattr(revision, "SCHEMA_PATH", changed_schema)
        return revision

    def test_frozen_initial_schema_rejects_edits(self, changed_revision):
        with pytest.raises(RuntimeError, match="frozen initial-schema snapshot"):
            changed_revision._schema_body()

    @pytest.fixture(
        params=[pytest.param(True, id="offline"), pytest.param(False, id="online")]
    )
    def execution(self, revision, request, monkeypatch):
        context = MigrationContext(as_sql=request.param)
        cursor = MigrationCursor()
        bind = MigrationBind(connection=MigrationConnection(active_cursor=cursor))

        def provide_context():
            return context

        def provide_bind():
            return bind

        monkeypatch.setattr(revision.op, "get_context", provide_context)
        monkeypatch.setattr(revision.op, "get_bind", provide_bind)
        return RevisionScenario(revision=revision, context=context, cursor=cursor)

    def test_initial_revision_executes_raw_sql_and_closes_online_cursor(
        self, execution
    ):
        execution.revision._execute_script("SELECT 100 % 9;")
        if execution.context.as_sql:
            assert execution.context.impl.statements == ["SELECT 100 % 9;\n"]
            assert execution.cursor.statements == []
            assert execution.cursor.closures == []
            return
        assert execution.cursor.statements == ["SELECT 100 % 9;"]
        assert execution.cursor.closures == [True]


class TestMigrationHistory:
    @pytest.fixture(
        params=[
            pytest.param(
                (build_migration_history(build_migration_revision("one")), None),
                id="linear",
            ),
            pytest.param(
                (
                    build_migration_history(build_migration_revision(), heads=()),
                    "exactly one migration head",
                ),
                id="no-head",
            ),
            pytest.param(
                (
                    build_migration_history(
                        build_migration_revision(), heads=("one", "two")
                    ),
                    "exactly one migration head",
                ),
                id="multiple-heads",
            ),
            pytest.param(
                (build_migration_history(heads=("one",)), "migration history is empty"),
                id="empty-history",
            ),
            pytest.param(
                (
                    build_migration_history(build_migration_revision(doc="")),
                    "has no description",
                ),
                id="missing-description",
            ),
            pytest.param(
                (
                    build_migration_history(build_migration_revision(merge=True)),
                    "unapproved merge point",
                ),
                id="merge-point",
            ),
        ]
    )
    def history(self, request, monkeypatch):
        scripts, message = request.param
        monkeypatch.setattr(
            verify_migrations.ScriptDirectory,
            "from_config",
            StageOutcome(result=scripts),
        )
        return message

    def test_only_documented_linear_history_is_accepted(self, history):
        errors = verify_migrations.validate(ALEMBIC_CONFIG)
        if history is None:
            assert errors == []
            return
        assert any(history in error for error in errors)


class TestMigrationDatabaseSettings:
    @pytest.fixture(
        params=[
            pytest.param(
                (
                    {
                        "DATABASE_URL": "postgresql://primary/db",
                        "TEST_DATABASE_URL": "postgresql://test/db",
                    },
                    "postgresql://primary/db",
                ),
                id="primary",
            ),
            pytest.param(
                ({"TEST_DATABASE_URL": "postgresql://test/db"}, "postgresql://test/db"),
                id="test-fallback",
            ),
            pytest.param(({}, None), id="missing"),
        ]
    )
    def url(self, request, monkeypatch):
        values, expected = request.param
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        return expected

    def test_url_precedence_and_required_value(self, url):
        if url is None:
            with pytest.raises(RuntimeError, match="DATABASE_URL or TEST_DATABASE_URL"):
                schema_snapshot.resolve_database_url()
            with pytest.raises(RuntimeError, match="DATABASE_URL or TEST_DATABASE_URL"):
                migration_preflight.resolve_database_url()
            return
        assert schema_snapshot.resolve_database_url() == url
        assert migration_preflight.resolve_database_url() == url


def test_schema_snapshot_render_is_deterministic():
    rendered = schema_snapshot.render({"tables": [{"table_name": "players"}]})

    assert (
        rendered
        == '{\n  "tables": [\n    {\n      "table_name": "players"\n    }\n  ]\n}\n'
    )


@pytest.mark.usefixtures("isolate_command_logging")
class TestSchemaSnapshot:
    @pytest.fixture
    def paths(self, tmp_path):
        return SnapshotScenario(
            expected=tmp_path.joinpath("expected.json"),
            actual=tmp_path.joinpath("actual.json"),
        )

    @pytest.fixture
    def catalog(self, monkeypatch):
        catalog = {"tables": [{"table_name": "players"}]}
        monkeypatch.setattr(
            schema_snapshot, "capture_schema_catalog", StageOutcome(result=catalog)
        )
        return catalog

    @pytest.mark.usefixtures("catalog")
    def test_schema_snapshot_update_then_compare(self, paths):
        assert (
            schema_snapshot.main(["--expected", str(paths.expected), "--update"]) == 0
        )
        assert (
            schema_snapshot.main(
                ["--expected", str(paths.expected), "--actual", str(paths.actual)]
            )
            == 0
        )
        assert paths.expected.read_text(encoding="utf-8") == paths.actual.read_text(
            encoding="utf-8"
        )

    @pytest.fixture
    def drifted(self, paths, catalog):
        paths.expected.write_text(
            schema_snapshot.render({"tables": []}), encoding="utf-8"
        )
        return paths

    def test_schema_snapshot_reports_drifted_contract(self, drifted, caplog):
        assert (
            schema_snapshot.main(
                ["--expected", str(drifted.expected), "--actual", str(drifted.actual)]
            )
            == 1
        )
        assert "does not match" in caplog.text
        assert "players" in drifted.actual.read_text(encoding="utf-8")

    @pytest.mark.usefixtures("catalog")
    def test_schema_snapshot_reports_missing_contract(self, paths, caplog):
        assert schema_snapshot.main(["--expected", str(paths.expected)]) == 1
        assert "snapshot is missing" in caplog.text


@pytest.mark.parametrize(
    ("tables", "versions", "expected"),
    [
        pytest.param([], [], None, id="empty-database"),
        pytest.param(["players"], ["20260910_0001"], None, id="versioned-database"),
        pytest.param(["players"], [], "no Alembic revision", id="unversioned-tables"),
        pytest.param(
            ["players"],
            ["one", "two"],
            "multiple Alembic revisions",
            id="multiple-revisions",
        ),
    ],
)
def test_migration_preflight_decisions(tables, versions, expected):
    error = migration_preflight.validate_preconditions(tables, versions)

    if expected is None:
        assert error is None
        return
    assert error is not None
    assert expected in error


class TestMigrationPreflightInspectsTablesAndRevision:
    @pytest.fixture
    def scenario(self):
        connection = CatalogDatabase(
            tables=("players", "teams"),
            versions=("20260910_0001",),
            version_table_exists=True,
        )
        return connection

    def test_migration_preflight_inspects_tables_and_revision(self, scenario):
        connection = scenario
        assert migration_preflight.inspect_database(connection) == (
            ["players", "teams"],
            ["20260910_0001"],
        )


class TestMigrationPreflightDoesNotQueryMissingVersionTable:
    @pytest.fixture
    def scenario(self):
        connection = CatalogDatabase()
        return connection

    def test_migration_preflight_does_not_query_missing_version_table(self, scenario):
        connection = scenario
        assert migration_preflight.inspect_database(connection) == ([], [])
        assert len(connection.statements) == 2


class TestReferenceDataSmokeAcceptsCompleteBaseline:
    @pytest.fixture
    def scenario(self):
        session = CatalogDatabase()
        return session

    def test_reference_data_smoke_accepts_complete_baseline(self, scenario):
        session = scenario
        migration_smoke.validate_reference_data(session)


class TestReferenceDataSmokeRejectsIncompleteBaseline:
    cases = [
        pytest.param((["nhl"], 22), id="missing-sources"),
        pytest.param((["capwages", "moneypuck", "nhl"], 21), id="missing-seasons"),
    ]

    @pytest.fixture(params=cases)
    def scenario(self, request):
        sources, seasons = request.param
        session = CatalogDatabase(sources=tuple(sources), seasons=seasons)
        return session

    def test_reference_data_smoke_rejects_incomplete_baseline(self, scenario):
        session = scenario
        with pytest.raises(RuntimeError, match="initial reference data is incomplete"):
            migration_smoke.validate_reference_data(session)


class TestApiSmokeAcceptsExpectedEmptyDatabaseResponses:
    @pytest.fixture
    def scenario(self):
        client = SavedApiClient(
            responses=dict(
                zip(
                    ("/api/health", "/api/seasons", "/api/teams"),
                    [
                        build_http_response(200, {"status": "ok"}),
                        build_http_response(
                            200, {"availableSeasons": [{}], "currentSeason": 2026}
                        ),
                        build_http_response(200, []),
                    ],
                )
            )
        )
        return client

    def test_api_smoke_accepts_expected_empty_database_responses(self, scenario):
        client = scenario
        migration_smoke.build_smoke_checks(client)

        assert client.paths == [
            "/api/health",
            "/api/seasons",
            "/api/teams",
        ]


class TestApiSmokeRejectsBadStatusOrPayload:
    cases = [
        pytest.param(
            [build_http_response(503, {"error": "down"})], id="unhealthy-status"
        ),
        pytest.param(
            [build_http_response(200, {"status": "wrong"})], id="invalid-health"
        ),
        pytest.param(
            [
                build_http_response(200, {"status": "ok"}),
                build_http_response(
                    200, {"availableSeasons": [], "currentSeason": 2026}
                ),
            ],
            id="missing-seasons",
        ),
        pytest.param(
            [
                build_http_response(200, {"status": "ok"}),
                build_http_response(
                    200, {"availableSeasons": [{}], "currentSeason": 2026}
                ),
                build_http_response(200, [{"id": 1}]),
            ],
            id="nonempty-teams",
        ),
    ]

    @pytest.fixture(params=cases)
    def scenario(self, request):
        responses = request.param
        client = SavedApiClient(
            responses=dict(
                zip(("/api/health", "/api/seasons", "/api/teams"), responses)
            )
        )
        return client

    def test_api_smoke_rejects_bad_status_or_payload(self, scenario):
        client = scenario
        with pytest.raises(RuntimeError, match="post-migration smoke check failed"):
            migration_smoke.build_smoke_checks(client)


class TestApiSmokeRejectsInvalidJson:
    @pytest.fixture
    def scenario(self):
        client = SavedApiClient(
            responses={"/api/health": build_http_response(200, {}, "not-json")}
        )
        return client

    def test_api_smoke_rejects_invalid_json(self, scenario):
        client = scenario
        with pytest.raises(RuntimeError, match="body=not-json"):
            migration_smoke.build_smoke_checks(client)


def test_alembic_environment_rejects_non_postgresql_database(tmp_path):
    result = run_command(
        f"sqlite:///{tmp_path.joinpath('wrong.db')}",
        "-m",
        "alembic",
        "-c",
        str(ALEMBIC_CONFIG),
        "upgrade",
        "head",
        "--sql",
        success=False,
    )

    events = [json.loads(line) for line in result.stderr.splitlines()]
    failures = [item for item in events if item["event"] == "command.failed"]
    assert len(failures) == 1
    assert failures[0]["stage"] == "postgresql_required"
    assert failures[0]["exceptions"][0]["type"] == "ConfigurationError"
    assert "wrong.db" not in result.stderr


@pytest.mark.integration
class TestCompleteMigrationLifecycle:
    alembic = ("-m", "alembic", "-c", str(ALEMBIC_CONFIG))

    @pytest.fixture
    def isolated_database(self, disposable_database_url) -> Generator[str]:
        source_url = make_url(disposable_database_url)
        database_name = f"tradevalue_migration_{uuid4().hex[:12]}"
        database_url = source_url.set(database=database_name).render_as_string(
            hide_password=False
        )
        admin_url = source_url.set(database="postgres")
        admin = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True
        )
        quoted_name = admin.dialect.identifier_preparer.quote(database_name)

        with admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {quoted_name}"))

        try:
            yield database_url
        finally:
            with admin.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": database_name},
                )
                connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_name}"))
            admin.dispose()

    def test_complete_migration_lifecycle_on_isolated_database(
        self, tmp_path, isolated_database
    ):
        database_url = isolated_database
        run_command(database_url, "backend/database/verify_migrations.py")
        run_command(database_url, "backend/database/migration_preflight.py")

        isolated = create_engine(database_url)
        with isolated.begin() as connection:
            connection.execute(text("CREATE TABLE players (id bigint PRIMARY KEY)"))
        unsafe = run_command(
            database_url,
            "backend/database/migration_preflight.py",
            success=False,
        )
        unsafe_events = [json.loads(line) for line in unsafe.stderr.splitlines()]
        assert unsafe_events[1]["event"] == "command.verification_failed"
        assert unsafe_events[1]["stage"] == "unversioned_schema"
        assert unsafe_events[-1]["outcome"] == "failed"
        with isolated.begin() as connection:
            connection.execute(text("DROP TABLE players"))
        isolated.dispose()

        offline_sql = run_command(
            database_url,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            "upgrade",
            "head",
            "--sql",
        ).stdout
        assert "CREATE TABLE players" in offline_sql
        assert "20260910_0001" in offline_sql

        run_command(database_url, *self.alembic, "upgrade", "head")
        run_command(database_url, *self.alembic, "upgrade", "head")
        current = run_command(database_url, *self.alembic, "current", "--check-heads")
        assert "20260920_0002 (head)" in current.stdout
        run_command(
            database_url,
            "backend/database/schema_snapshot.py",
            "--actual",
            str(tmp_path.joinpath("actual.json")),
        )
        run_command(database_url, "backend/database/migration_smoke.py")

        run_command(database_url, *self.alembic, "downgrade", "base")
        run_command(database_url, "backend/database/migration_preflight.py")
        run_command(database_url, *self.alembic, "upgrade", "head")
        run_command(database_url, "backend/database/schema_snapshot.py")

        isolated = create_engine(database_url)
        with isolated.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == "20260920_0002"
            )
            assert (
                connection.execute(text("SELECT COUNT(*) FROM seasons")).scalar_one()
                == 22
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM data_sources")
                ).scalar_one()
                == 4
            )
        isolated.dispose()
