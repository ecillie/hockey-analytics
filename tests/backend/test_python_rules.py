"""Repository syntax checks reject forbidden forms without executing source."""

from pathlib import Path
import subprocess

import pytest

from app.shared.tests.python_rules import SyntaxCase
from backend.database.verify_python_rules import (
    Rule,
    SourceScopeError,
    find_source_paths,
    inspect_source,
    main,
)


class TestForbiddenSyntax:
    cases = (
        pytest.param(
            SyntaxCase(source="value = lambda: 1", rules=(Rule.LAMBDA,), lines=(1,)),
            id="lambda",
        ),
        pytest.param(
            SyntaxCase(
                source="class Value:\n    @staticmethod\n    def read(): pass",
                rules=(Rule.STATIC_METHOD,),
                lines=(3,),
            ),
            id="static-method",
        ),
        pytest.param(
            SyntaxCase(
                source="class Value:\n    @classmethod\n    def read(cls): pass",
                rules=(),
                lines=(),
            ),
            id="class-method-requires-review",
        ),
        pytest.param(
            SyntaxCase(
                source="while True:\n    pass", rules=(Rule.UNBOUNDED_LOOP,), lines=(1,)
            ),
            id="unbounded-loop",
        ),
        pytest.param(
            SyntaxCase(
                source="from __future__ import annotations",
                rules=(Rule.POSTPONED_ANNOTATIONS,),
                lines=(1,),
            ),
            id="postponed-annotations",
        ),
        pytest.param(
            SyntaxCase(
                source="from typing import Any as Value",
                rules=(Rule.ANY_IMPORT,),
                lines=(1,),
            ),
            id="aliased-any",
        ),
        pytest.param(
            SyntaxCase(
                source="from typing_extensions import ClassVar",
                rules=(),
                lines=(),
            ),
            id="class-variable-context-requires-review",
        ),
        pytest.param(
            SyntaxCase(
                source="class _Value: pass", rules=(Rule.PRIVATE_CLASS,), lines=(1,)
            ),
            id="private-class",
        ),
        pytest.param(
            SyntaxCase(
                source="class Value:\n    def __post_init__(self): pass",
                rules=(Rule.POST_INIT,),
                lines=(2,),
            ),
            id="post-init",
        ),
        pytest.param(
            SyntaxCase(
                source='object.__setattr__(value, "field", 1)',
                rules=(Rule.FROZEN_MUTATION,),
                lines=(1,),
            ),
            id="frozen-mutation",
        ),
        pytest.param(
            SyntaxCase(source="match value:\n    case 1: pass", rules=(), lines=()),
            id="match-requires-review",
        ),
        pytest.param(
            SyntaxCase(source="del value", rules=(Rule.DELETE,), lines=(1,)),
            id="delete",
        ),
        pytest.param(
            SyntaxCase(
                source='text = "lambda: 1"\nwhile pending:\n    pending = False',
                rules=(),
                lines=(),
            ),
            id="source-strings-and-bounded-loop",
        ),
        pytest.param(
            SyntaxCase(
                source="class Value:\n    def read(self): return self.value",
                rules=(),
                lines=(),
            ),
            id="instance-method",
        ),
        pytest.param(
            SyntaxCase(
                source="from typing import Protocol\nclass Values(Protocol): pass",
                rules=(),
                lines=(),
            ),
            id="allowed-typing",
        ),
        pytest.param(
            SyntaxCase(
                source="class _Value:\n    read = lambda: 1",
                rules=(Rule.PRIVATE_CLASS, Rule.LAMBDA),
                lines=(1, 2),
            ),
            id="multiple-violations",
        ),
        pytest.param(
            SyntaxCase(
                source='raise RuntimeError("must not execute")', rules=(), lines=()
            ),
            id="no-source-execution",
        ),
    )

    @pytest.fixture(params=cases)
    def scenario(self, request):
        return request.param

    @pytest.fixture
    def path(self):
        return Path("example.py")

    def test_reports_syntax_and_source_location(self, scenario, path):
        violations = inspect_source(scenario.source, path)
        assert tuple(violation.rule for violation in violations) == scenario.rules
        assert tuple(violation.line for violation in violations) == scenario.lines
        assert all(violation.path == path for violation in violations)


class TestSourceScope:
    @pytest.fixture
    def root(self, tmp_path):
        for directory in (
            "backend/src",
            "backend/database",
            "backend/migrations",
            "ml/src",
            "tests",
            "backend/.venv",
            "backend/legacy_loaders",
        ):
            tmp_path.joinpath(directory).mkdir(parents=True)
        for name in (
            "backend/__init__.py",
            "backend/export_openapi.py",
            "backend/index.py",
            "backend/src/source.py",
            "backend/.venv/dependency.py",
            "backend/legacy_loaders/retired.py.txt",
        ):
            tmp_path.joinpath(name).write_text("", encoding="utf-8")
        return tmp_path

    @pytest.fixture
    def violating_root(self, root):
        root.joinpath("backend/src/source.py").write_text(
            "value = lambda: 1", encoding="utf-8"
        )
        return root

    @pytest.fixture
    def malformed_root(self, root):
        root.joinpath("backend/src/source.py").write_text("def (", encoding="utf-8")
        return root

    def test_scope_excludes_dependencies_and_retired_text(self, root):
        assert {str(path.relative_to(root)) for path in find_source_paths(root)} == {
            "backend/__init__.py",
            "backend/export_openapi.py",
            "backend/index.py",
            "backend/src/source.py",
        }

    def test_missing_roots_fail_instead_of_reporting_success(self, tmp_path):
        with pytest.raises(SourceScopeError) as raised:
            find_source_paths(tmp_path)
        assert raised.value.root == tmp_path
        assert "backend/src" in raised.value.missing

    def test_clean_source_returns_success(self, root, capsys):
        assert main(["--root", str(root)]) == 0
        assert "semantic rules require manual review" in capsys.readouterr().out

    def test_violations_report_relative_paths_and_fail(self, violating_root, caplog):
        assert main(["--root", str(violating_root)]) == 1
        assert "backend/src/source.py:1: lambda" in caplog.text

    def test_invalid_syntax_fails_closed(self, malformed_root, caplog):
        assert main(["--root", str(malformed_root)]) == 1
        assert "SyntaxError" in caplog.text


class TestRepositoryScope:
    @pytest.fixture
    def root(self):
        return Path(__file__).resolve().parents[2]

    @pytest.fixture
    def tracked_sources(self, root):
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return frozenset(
            root.joinpath(name) for name in result.stdout.split("\0") if name != ""
        )

    def test_every_tracked_python_source_is_in_scope(self, root, tracked_sources):
        assert tracked_sources.issubset(find_source_paths(root))
