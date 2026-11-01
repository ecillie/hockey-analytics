"""Check stable Python syntax rules without importing application modules."""

import argparse
import ast
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from app.shared.cli import ExitCode


class Rule(StrEnum):
    LAMBDA = auto()
    STATIC_METHOD = auto()
    UNBOUNDED_LOOP = auto()
    POSTPONED_ANNOTATIONS = auto()
    ANY_IMPORT = auto()
    PRIVATE_CLASS = auto()
    POST_INIT = auto()
    FROZEN_MUTATION = auto()
    DELETE = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class Violation:
    path: Path
    line: int
    rule: Rule


class SourceScopeError(ValueError):
    def __init__(self, *, root: Path, missing: tuple[str, ...]) -> None:
        super().__init__(
            f"Python source scope is missing under {root}: {', '.join(missing)}"
        )
        self.root = root
        self.missing = missing


def identify_forbidden_syntax(node: ast.AST) -> Rule | None:
    if isinstance(node, ast.Lambda):
        return Rule.LAMBDA
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name == "__post_init__":
            return Rule.POST_INIT
        if any(
            isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
            for decorator in node.decorator_list
        ):
            return Rule.STATIC_METHOD
    if (
        isinstance(node, ast.While)
        and isinstance(node.test, ast.Constant)
        and node.test.value is True
    ):
        return Rule.UNBOUNDED_LOOP
    if isinstance(node, ast.ImportFrom):
        names = {name.name for name in node.names}
        if node.module == "__future__" and "annotations" in names:
            return Rule.POSTPONED_ANNOTATIONS
        if node.module in {"typing", "typing_extensions"} and "Any" in names:
            return Rule.ANY_IMPORT
    if isinstance(node, ast.ClassDef) and node.name.startswith("_"):
        return Rule.PRIVATE_CLASS
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    ):
        return Rule.FROZEN_MUTATION
    if isinstance(node, ast.Delete):
        return Rule.DELETE
    return None


def inspect_source(source: str, path: Path) -> tuple[Violation, ...]:
    tree = ast.parse(source, filename=str(path))
    return tuple(
        Violation(path=path, line=node.lineno, rule=rule)
        for node in ast.walk(tree)
        if isinstance(node, (ast.stmt, ast.expr))
        if (rule := identify_forbidden_syntax(node)) is not None
    )


def find_source_paths(root: Path) -> tuple[Path, ...]:
    directories = (
        "backend/src",
        "backend/database",
        "backend/migrations",
        "ml/src",
        "tests",
    )
    files = ("backend/__init__.py", "backend/export_openapi.py", "backend/index.py")
    missing = tuple(
        directory for directory in directories if not root.joinpath(directory).is_dir()
    ) + tuple(file for file in files if not root.joinpath(file).is_file())
    if len(missing) > 0:
        raise SourceScopeError(root=root, missing=missing)
    paths = {
        path
        for directory in directories
        for path in root.joinpath(directory).rglob("*.py")
    }
    paths.update(root.joinpath(file) for file in files)
    return tuple(sorted(paths))


def inspect_repository(root: Path) -> tuple[Violation, ...]:
    return tuple(
        violation
        for path in find_source_paths(root)
        for violation in inspect_source(
            path.read_text(encoding="utf-8"), path.relative_to(root)
        )
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandOptions:
    root: Path


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = CommandOptions(**vars(parser.parse_args(argv)))
    logging.basicConfig(level=logging.INFO)
    try:
        violations = inspect_repository(options.root.resolve())
    except Exception:
        logger.exception("Python rule inspection failed")
        return ExitCode.FAILURE
    for violation in violations:
        logger.error("%s:%s: %s", violation.path, violation.line, violation.rule)
    if len(violations) > 0:
        return ExitCode.FAILURE
    print("Python structural rules passed; semantic rules require manual review.")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
