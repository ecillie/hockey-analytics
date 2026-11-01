"""Repository migration loading and subprocess verification."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
import pytest


def load_initial_revision():
    spec = importlib.util.spec_from_file_location(
        "tradevalue_initial_revision", INITIAL_REVISION
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_command(database_url: str, *arguments: str, success=True):
    environment = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DEV_DATABASE_URL": database_url,
        "TEST_DATABASE_URL": database_url,
        "ENV": "dev",
    }
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if success and result.returncode != 0:
        raise pytest.fail.Exception(
            f"command failed: {arguments}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not success and result.returncode == 0:
        raise pytest.fail.Exception(f"command unexpectedly passed: {arguments}")
    return result


ROOT = Path(__file__).resolve().parents[5]
INITIAL_REVISION = ROOT.joinpath(
    "backend", "migrations", "versions", "20260910_0001_initial_schema.py"
)
