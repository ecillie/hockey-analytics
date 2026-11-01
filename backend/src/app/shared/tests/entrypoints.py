"""Repository entrypoint manifests and source inspection helpers."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[5]

BACKEND = ROOT.joinpath("backend")

APP = BACKEND.joinpath("src", "app")

FULL_DATA_SCRIPT = APP.joinpath("ScriptingFiles", "FullDataScript")

LEGACY_LOADERS = BACKEND.joinpath("legacy_loaders")

SUPPORTED_CLI_MODULES = frozenset(
    {
        "app.ScriptingFiles.FullDataScript.capspace",
        "app.ScriptingFiles.FullDataScript.populate_roster_status",
        "app.ScriptingFiles.FullDataScript.run_all",
    }
)

QUARANTINED_LOADERS = frozenset(
    {
        "save_basic_player_stats.py.txt",
        "save_contracts_to_db.py.txt",
        "save_goalie_advanced_stats.py.txt",
        "save_individual_contract_years.py.txt",
        "save_nhl_regular_seasoe_schedule.py.txt",
        "save_players_to_db.py.txt",
        "save_previous_games_stats.py.txt",
        "save_skater_advanced_stats.py.txt",
    }
)


def find_supported_python_files() -> list[Path]:
    return sorted(path for path in APP.rglob("*.py") if "__pycache__" not in path.parts)


def find_full_data_modules() -> list[str]:
    return [
        ".".join(path.relative_to(BACKEND.joinpath("src")).with_suffix("").parts)
        for path in sorted(FULL_DATA_SCRIPT.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]


def find_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def has_main_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(is_main_guard(node) for node in ast.walk(tree))


def is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )
