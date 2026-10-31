from pathlib import Path
from dataclasses import dataclass, field

from app.ScriptingFiles.FullDataScript.contracts.tests.fixtures import SavedResponse

import pytest
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts import repository as persistence
from sqlalchemy import create_engine, text

FIXTURE = Path(__file__).parent.joinpath(
    "fixtures", "ingestion", "capspace_datsyuk.html"
)


@dataclass(slots=True, kw_only=True, frozen=True)
class FixtureSession:
    body: str
    requests: list[str] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def get(self, url, timeout):
        self.requests.append(url)
        return SavedResponse(status_code=200, headers={}, text=self.body, url=url)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractPreviewScenario:
    session: FixtureSession
    before: tuple[int, int, int]


@pytest.fixture()
def database(disposable_database_url):
    engine = create_engine(disposable_database_url)
    with engine.begin() as connection:
        if (
            connection.execute(
                text("SELECT to_regclass('public.players')")
            ).scalar_one()
            is None
        ):
            raise pytest.skip.Exception("the disposable database has not been migrated")
        if (
            connection.execute(
                text("SELECT to_regclass('public.source_records')")
            ).scalar_one()
            is None
        ):
            raise pytest.skip.Exception("the disposable database has not been migrated")
        has_capspace = connection.execute(
            text("SELECT count(*) FROM data_sources WHERE code='capspace'")
        ).scalar_one()
        if not has_capspace:
            raise pytest.skip.Exception(
                "the disposable database has not been upgraded to the CapSpace migration"
            )
        connection.execute(
            text("TRUNCATE teams, players, ingestion_runs RESTART IDENTITY CASCADE")
        )

    yield engine
    engine.dispose()


def seed_player(
    engine, player_id: int, season: int = 2008, *, with_nhl_id: str = "8467514"
):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id,abbreviation,name) VALUES (900,'DET','Detroit Red Wings')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO players (id,first_name,last_name,primary_position) VALUES (:id,'Pavel','Datsyuk','C')"
            ),
            {"id": player_id},
        )
        source_id = connection.execute(
            text("SELECT id FROM data_sources WHERE code='nhl'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO player_external_ids (player_id,source_id,external_id) VALUES (:p,:s,:e)"
            ),
            {"p": player_id, "s": source_id, "e": with_nhl_id},
        )
        for target_season in (season, season + 1):
            connection.execute(
                text(
                    """INSERT INTO skater_season_stats
                           (player_id,season_start_year,team_id,stat_scope,
                            game_type,source_id,games_played)
                       VALUES (:p,:y,NULL,'TOTAL',2,:s,50)"""
                ),
                {"p": player_id, "y": target_season, "s": source_id},
            )


def counts(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM contracts),(SELECT count(*) FROM contract_seasons),(SELECT count(*) FROM source_records WHERE entity_type='capspace_player_profile')"
                )
            ).one()
        )


class TestFirstApplySecondRunIsIdempotentAndGapDriven:
    @pytest.fixture
    def scenario(self, database):
        seed_player(database, 8001)
        session = FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))
        return session

    @pytest.mark.integration
    def test_first_apply_second_run_is_idempotent_and_gap_driven(
        self, scenario, database
    ):
        session = scenario
        first = capspace._run(
            session, dry_run=False, first_season=2008, last_season=2009, workers=1
        )
        first_counts = counts(database)
        second = capspace._run(
            session, dry_run=False, first_season=2008, last_season=2009, workers=1
        )

        assert first["contracts_created"] == 1
        assert first["contract_seasons_created"] == 2
        assert first["profiles_requested"] == 1
        assert second["candidate_players"] == 0
        assert session.calls == 1
        assert counts(database) == first_counts

        with database.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT c.total_value_cents,cs.cap_hit_cents,cs.base_salary_cents,cs.signing_bonus_cents,cs.performance_bonus_cents,cs.cap_percentage,cs.clauses->>'clause' FROM contracts c JOIN contract_seasons cs ON cs.contract_id=c.id WHERE cs.season_start_year=2008"
                )
            ).one()
        assert row[0:5] == (4_690_000_000, 670_000_000, 670_000_000, 0, 0)
        assert float(row[5]) == pytest.approx(670_000_000 / 5_670_000_000)
        assert row[6] == "NMC"


class TestExistingContractGetsMissingSeasonWithoutOverwrite:
    @pytest.fixture
    def scenario(self, database):
        seed_player(database, 8002)
        with database.begin() as connection:
            source_id = connection.execute(
                text("SELECT id FROM data_sources WHERE code='capwages'")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO contracts (id,player_id,signing_team_id,source_id,external_id,signed_on,start_season,end_season,term_years,total_value_cents) VALUES (9100,8002,900,:s,'trusted','2007-04-06',2008,2009,7,4690000000)"
                ),
                {"s": source_id},
            )
            connection.execute(
                text(
                    "INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,base_salary_cents,cap_hit_cents) VALUES (9100,2008,900,670000000,670000000)"
                )
            )

        first = counts(database)
        return first

    @pytest.mark.integration
    def test_existing_contract_gets_missing_season_without_overwrite(
        self, scenario, database
    ):
        first = scenario
        preview = capspace._run(
            FixtureSession(body=FIXTURE.read_text(encoding="utf-8")),
            dry_run=True,
            first_season=2008,
            last_season=2009,
            workers=1,
        )

        assert preview["contract_seasons_created"] == 1
        assert counts(database) == first

        result = capspace._run(
            FixtureSession(body=FIXTURE.read_text(encoding="utf-8")),
            dry_run=False,
            first_season=2008,
            last_season=2009,
            workers=1,
        )

        assert result.get("contracts_created", 0) == 0
        assert result["contracts_matched"] == 1
        assert counts(database)[0] == first[0]
        with database.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM contract_seasons WHERE contract_id=9100")
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        "SELECT base_salary_cents FROM contract_seasons WHERE contract_id=9100 AND season_start_year=2008"
                    )
                ).scalar_one()
                == 670000000
            )


class TestDryRunAndConflictAreMutationFree:
    @pytest.fixture
    def scenario(self, database):
        seed_player(database, 8003)
        session = FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))
        before = counts(database)
        return ContractPreviewScenario(session=session, before=before)

    @pytest.mark.integration
    def test_dry_run_and_conflict_are_mutation_free(self, scenario, database):
        session = scenario.session
        before = scenario.before
        preview = capspace._run(
            session, dry_run=True, first_season=2008, last_season=2008, workers=1
        )
        assert preview["records_created"] == 0
        assert counts(database) == before

        with database.begin() as connection:
            source_id = connection.execute(
                text("SELECT id FROM data_sources WHERE code='capwages'")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO contracts (id,player_id,signing_team_id,source_id,external_id,start_season,end_season,term_years,total_value_cents) VALUES (9101,8003,900,:s,'conflict',2008,2009,7,1)"
                ),
                {"s": source_id},
            )
        result = capspace._run(
            FixtureSession(body=FIXTURE.read_text(encoding="utf-8")),
            dry_run=False,
            first_season=2008,
            last_season=2009,
            workers=1,
        )
        assert result.get("reconciliation_conflicts", 0) == 1, result
        with database.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT total_value_cents FROM contracts WHERE id=9101")
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM contract_seasons WHERE contract_id=9101")
                ).scalar_one()
                == 0
            )


class TestTransactionRollsBackPartialPersistence:
    @pytest.fixture
    def scenario(self, database, monkeypatch):
        seed_player(database, 8004)
        original = persistence.persist_contracts

        def fail_after_insert(cursor, *args, **kwargs):
            original(cursor, *args, **kwargs)
            raise RuntimeError("fixture failure")

        monkeypatch.setattr(persistence, "persist_contracts", fail_after_insert)
        return database

    @pytest.mark.integration
    def test_transaction_rolls_back_partial_persistence(
        self, scenario, database, monkeypatch
    ):
        database = scenario
        with pytest.raises(RuntimeError, match="fixture failure"):
            capspace._run(
                FixtureSession(body=FIXTURE.read_text(encoding="utf-8")),
                dry_run=False,
                first_season=2008,
                last_season=2008,
                workers=1,
            )
        assert counts(database)[0:2] == (0, 0)
