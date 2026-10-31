"""External output directories for source and wheel installations."""

import os
from pathlib import Path


def artifact_directory(variable: str, relative: Path) -> Path:
    if configured := os.environ.get(variable):
        return Path(configured)
    source_project = Path(__file__).resolve().parents[2]
    if source_project.joinpath("pyproject.toml").is_file():
        return source_project.joinpath(relative)
    return Path.cwd().joinpath("ml", relative)
