"""Explicit fixture plugins for backend concept tests."""

pytest_plugins = (
    "app.shared.observability.tests.fixtures",
    "app.api.tests.fixtures",
    "app.ScriptingFiles.FullDataScript.roster_status.tests.fixtures",
    "app.ScriptingFiles.FullDataScript.source_ingestion.tests.fixtures",
    "app.ScriptingFiles.FullDataScript.contracts.tests.fixtures",
)
