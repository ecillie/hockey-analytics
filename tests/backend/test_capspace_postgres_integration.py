from pathlib import Path
import pytest
from app.ScriptingFiles.FullDataScript import capspace
from app.ScriptingFiles.FullDataScript.contracts import repository as persistence
from sqlalchemy import text
from app.ScriptingFiles.FullDataScript.contracts.tests.postgres import (
    FixtureSession,
    ContractPreviewScenario,
    seed_player,
    counts,
)

FIXTURE = Path(__file__).parent.joinpath(
    "fixtures", "ingestion", "capspace_datsyuk.html"
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

    @pytest.fixture
    def preview_session(self):
        return FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))

    @pytest.fixture
    def apply_session(self):
        return FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.integration
    def test_existing_contract_gets_missing_season_without_overwrite(
        self, scenario, database, preview_session, apply_session
    ):
        first = scenario
        preview = capspace._run(
            preview_session,
            dry_run=True,
            first_season=2008,
            last_season=2009,
            workers=1,
        )

        assert preview["contract_seasons_created"] == 1
        assert counts(database) == first

        result = capspace._run(
            apply_session,
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

    @pytest.fixture
    def conflicting_session(self):
        return FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.integration
    def test_dry_run_and_conflict_are_mutation_free(
        self, scenario, database, conflicting_session
    ):
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
            conflicting_session,
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

    @pytest.fixture
    def failed_session(self):
        return FixtureSession(body=FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.integration
    def test_transaction_rolls_back_partial_persistence(
        self, scenario, database, failed_session
    ):
        database = scenario
        with pytest.raises(RuntimeError, match="fixture failure"):
            capspace._run(
                failed_session,
                dry_run=False,
                first_season=2008,
                last_season=2008,
                workers=1,
            )
        assert counts(database)[0:2] == (0, 0)


@pytest.mark.integration
class TestAmbiguousContractMatches:
    @pytest.fixture
    def scenario(self, database):
        seed_player(database, 8005)
        with database.begin() as connection:
            connection.execute(
                text("""INSERT INTO contracts
                    (player_id,signing_team_id,source_id,external_id,
                     start_season,end_season,term_years,total_value_cents)
                    SELECT 8005,900,ds.id,'ambiguous-' || n,2008,2009,7,4690000000
                    FROM data_sources ds CROSS JOIN generate_series(1,2) n
                    WHERE ds.code='capwages'""")
            )
        return ContractPreviewScenario(
            session=FixtureSession(body=FIXTURE.read_text(encoding="utf-8")),
            before=counts(database),
        )

    def test_ambiguous_matches_are_preserved_without_season_writes(
        self, scenario, database
    ):
        result = capspace._run(
            scenario.session,
            dry_run=False,
            first_season=2008,
            last_season=2009,
            workers=1,
        )
        assert result["reconciliation_conflicts"] == 1
        assert result.get("contracts_created", 0) == 0
        assert counts(database)[:2] == scenario.before[:2] == (2, 0)
