"""Counts reported by completed ingestion work without inferring row writes."""

from collections.abc import Mapping


def collect_ingestion_counts(summary: Mapping[str, object]) -> dict[str, int]:
    values: dict[str, int] = {}
    if type(fetched := summary.get("records_read")) is int:
        values["fetched"] = fetched
    created = summary.get("records_created", 0)
    updated = summary.get("records_updated", 0)
    if (
        ("records_created" in summary or "records_updated" in summary)
        and type(created) is int
        and type(updated) is int
    ):
        values["committed"] = created + updated
    return values
