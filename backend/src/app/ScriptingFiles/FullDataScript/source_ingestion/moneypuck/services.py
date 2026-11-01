"""Load and validate MoneyPuck snapshots before the repository is called."""

from dataclasses import dataclass
import json
from typing import Protocol, runtime_checkable
from app.ScriptingFiles.FullDataScript.tracking.domain import IngestionContext
from app.ScriptingFiles.FullDataScript.tracking.services import (
    report_ingestion_progress,
)
from app.shared.observability.domain import LogLevel

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    MoneyPuckSummary,
    PlayerKind,
    StatRow,
    StatLayout,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.http import SourceClient
from app.ScriptingFiles.FullDataScript.source_ingestion.domain import select_stat_layout
from app.ScriptingFiles.FullDataScript.source_ingestion.moneypuck.domain import (
    MoneyPuckOptions,
    MoneyPuckSnapshot,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.policy import (
    find_quality_violation,
    RowPolicy,
    validate_rows,
    find_quality_options_violation,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.schemas import (
    MoneyPuckRow,
    validate_payload,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository import read_csv
from app.ScriptingFiles.FullDataScript.source_ingestion.util import (
    parse_number,
    parse_team_abbreviation,
    parse_csv,
    normalize_position,
    hash_source_row,
)


@runtime_checkable
class MoneyPuckRepository(Protocol):
    def persist(self, snapshot: MoneyPuckSnapshot) -> MoneyPuckSummary: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class MoneyPuckService:
    client: SourceClient
    repository: MoneyPuckRepository
    options: MoneyPuckOptions
    context: IngestionContext | None = None

    def ingest(self) -> MoneyPuckSummary:
        if violation := find_quality_options_violation(
            self.options.minimum_rows_per_kind, self.options.maximum_duplicate_ratio
        ):
            raise violation
        rows: list[StatRow] = []
        reports = []
        for kind in PlayerKind:
            source = f"MoneyPuck {kind}"
            incoming = read_csv(self.options.historical_file(kind)) + parse_csv(
                self.client.get_csv(self.options.current_url(kind)), source=source
            )
            policy = RowPolicy(
                source=source,
                required_fields=(
                    "playerId",
                    "season",
                    "name",
                    "situation",
                    "games_played",
                    "icetime",
                ),
                grain_fields=("playerId", "season", "team", "situation"),
                expected_seasons=self.options.expected_seasons,
                integer_fields=frozenset({"playerId", "season", "games_played"}),
                numeric_fields=frozenset({"icetime"}),
            )
            valid, report = validate_rows(incoming, policy)
            report_ingestion_progress(
                self.context,
                event="ingestion.rows_read",
                values={
                    "fetched": len(incoming),
                    "validated": len(valid),
                    "player_kind": kind.value,
                },
                level=LogLevel.DEBUG,
            )
            if violation := find_quality_violation(
                report,
                minimum_rows=self.options.minimum_rows_per_kind,
                maximum_duplicate_ratio=self.options.maximum_duplicate_ratio,
            ):
                raise violation
            layout = select_stat_layout(kind, advanced=True)
            rows.extend(normalize_row(row, kind, layout) for row in valid)
            reports.append(report)
        report_ingestion_progress(
            self.context, event="ingestion.validated", values={"validated": len(rows)}
        )
        return self.repository.persist(
            MoneyPuckSnapshot(rows=tuple(rows), quality=tuple(reports))
        )


def normalize_row(
    raw: dict[str, object], kind: PlayerKind, layout: StatLayout
) -> StatRow:
    value = validate_payload(
        raw,
        MoneyPuckRow,
        source=f"MoneyPuck {kind}",
    )
    metrics = tuple(
        parse_number(raw.get(spec.source_field), spec.integer)
        for spec in layout.metrics
    )
    extra = {
        key: parse_number(item) if item not in (None, "") else None
        for key, item in raw.items()
    }
    team = parse_team_abbreviation(value.team)
    return StatRow(
        kind=kind,
        external_id=str(value.playerId),
        season=value.season,
        name=value.name,
        position=normalize_position(value.position, kind == PlayerKind.GOALIE),
        teams=(team,) if team is not None else (),
        game_type=2,
        situation=value.situation[:24],
        metrics=metrics,
        source_row_hash=hash_source_row(raw),
        extra_metrics_json=json.dumps(extra),
    )
