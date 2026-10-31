"""Shared command exit meanings and argument validation errors."""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    INCOMPLETE = 2


class CommandOptionError(ValueError):
    def __init__(self, *, option: str, requirement: str) -> None:
        super().__init__(f"{option} {requirement}")
        self.option = option
        self.requirement = requirement
