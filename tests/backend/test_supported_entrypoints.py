"""Smoke tests for every supported backend and ingestion entrypoint."""

from app.shared.tests.entrypoints import (
    ROOT,
    BACKEND,
    APP,
    FULL_DATA_SCRIPT,
    LEGACY_LOADERS,
    SUPPORTED_CLI_MODULES,
    QUARANTINED_LOADERS,
    supported_python_files,
    full_data_modules,
    imported_modules,
    has_main_guard,
)
import os
import subprocess
import sys
import py_compile
import pytest


def test_complete_backend_application_compiles(tmp_path):
    for source in supported_python_files():
        target = tmp_path.joinpath(source.relative_to(APP).with_suffix(".pyc"))
        target.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(str(source), cfile=str(target), doraise=True)


def test_supported_tree_does_not_reference_removed_orm_or_legacy_loaders():
    failures = []
    for source in supported_python_files():
        imports = imported_modules(source)
        forbidden = sorted(
            name for name in imports if name == "app.models" or ".save_" in name
        )
        if forbidden:
            failures.append(f"{source.relative_to(ROOT)}: {', '.join(forbidden)}")

    assert failures == []
    assert list(FULL_DATA_SCRIPT.glob("save_*.py")) == []


def test_complete_legacy_loader_set_is_quarantined_outside_application_tree():
    archived = {path.name for path in LEGACY_LOADERS.glob("save_*.py.txt")}

    assert archived == QUARANTINED_LOADERS
    assert list(LEGACY_LOADERS.rglob("*.py")) == []
    assert list(LEGACY_LOADERS.rglob("*.pyc")) == []
    assert (LEGACY_LOADERS.joinpath("README.md")).is_file()


def test_supported_cli_manifest_matches_executable_modules():
    executable_modules = {
        ".".join(path.relative_to(BACKEND.joinpath("src")).with_suffix("").parts)
        for path in FULL_DATA_SCRIPT.rglob("*.py")
        if has_main_guard(path)
    }
    assert executable_modules == SUPPORTED_CLI_MODULES


@pytest.mark.parametrize("module", full_data_modules())
class TestSupportedIngestionImports:
    @pytest.fixture
    def environment(self):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        return environment

    def test_supported_ingestion_module_imports_in_fresh_interpreter(
        self, module, environment
    ):
        completed = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0, (
            f"failed to import {module}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
