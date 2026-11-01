"""Smoke tests for every supported backend and ingestion entrypoint."""

from app.shared.tests.entrypoints import (
    ROOT,
    BACKEND,
    APP,
    FULL_DATA_SCRIPT,
    LEGACY_LOADERS,
    SUPPORTED_CLI_MODULES,
    QUARANTINED_LOADERS,
    find_supported_python_files,
    find_full_data_modules,
    find_imported_modules,
    has_main_guard,
)
import os
import subprocess
import sys
import py_compile
import pytest
import importlib.util
from pathlib import Path
from app.shared.tests.fakes import StageOutcome


class TestInspectionHelperImports:
    @pytest.fixture(
        params=[
            pytest.param(
                "backend/src/app/shared/tests/entrypoints.py",
                id="entrypoint-inspection",
            ),
            pytest.param(
                "backend/src/app/shared/tests/migrations.py", id="migration-inspection"
            ),
            pytest.param("tests/backend/test_openapi_contract.py", id="openapi-test"),
            pytest.param("tests/ml/test_paths.py", id="model-path-test"),
        ]
    )
    def guarded_import(self, request, monkeypatch):
        spec = importlib.util.spec_from_file_location(
            "guarded_import", ROOT.joinpath(request.param)
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        rejected = StageOutcome(
            result=None, failure=AssertionError("filesystem work during import")
        )
        for name in ("resolve", "glob", "rglob", "read_text", "open"):
            monkeypatch.setattr(Path, name, rejected)
        return spec.loader, module

    def test_import_does_not_resolve_or_scan_files(self, guarded_import):
        loader, module = guarded_import
        loader.exec_module(module)


def test_complete_backend_application_compiles(tmp_path):
    for source in find_supported_python_files():
        target = tmp_path.joinpath(source.relative_to(APP).with_suffix(".pyc"))
        target.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(str(source), cfile=str(target), doraise=True)


def test_supported_tree_does_not_reference_removed_orm_or_legacy_loaders():
    failures = []
    for source in find_supported_python_files():
        imports = find_imported_modules(source)
        forbidden = sorted(
            name for name in imports if name == "app.models" or ".save_" in name
        )
        if len(forbidden) > 0:
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


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "module" in metafunc.fixturenames:
        metafunc.parametrize(
            "module", [pytest.param(name, id=name) for name in find_full_data_modules()]
        )


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
