"""The shared July 1 NHL season visibility boundary."""

from datetime import date


def latest_started_season(as_of: date) -> int:
    return as_of.year if as_of.month >= 7 else as_of.year - 1
