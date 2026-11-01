"""Restore command logger ownership after in-process boundary tests."""

import logging

import pytest


@pytest.fixture
def isolate_command_logging(monkeypatch, caplog):
    namespaces = (
        "app",
        "backend",
        "ml",
        "__main__",
        "sqlalchemy",
        "httpx",
        "httpcore",
        "urllib3",
        "requests",
    )
    previous = logging.getHandlerByName("tradevalue.diagnostics")
    for namespace in namespaces:
        target = logging.getLogger(namespace)
        monkeypatch.setattr(target, "handlers", [caplog.handler])
        monkeypatch.setattr(target, "level", logging.NOTSET)
        monkeypatch.setattr(target, "propagate", False)
    yield
    installed = logging.getHandlerByName("tradevalue.diagnostics")
    if installed is not None and installed is not previous:
        installed.close()
