"""Compatibility imports for canonical source transport adapters."""

from app.ScriptingFiles.FullDataScript.source_ingestion.domain import (
    SourceHttpOptions as SourceHttpOptions,
)
from app.ScriptingFiles.FullDataScript.source_ingestion.repository.http import (
    SourceResponse as SourceResponse,
    SourceSession as SourceSession,
    SourceClient as SourceClient,
    SessionSourceClient as SessionSourceClient,
    report_request_recovery as report_request_recovery,
    open_http_session as open_http_session,
    configure_http_session as configure_http_session,
    open_source_client as open_source_client,
    ContextualSourceClientFactory as ContextualSourceClientFactory,
    SynchronizedSourceClient as SynchronizedSourceClient,
)
