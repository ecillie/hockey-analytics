#!/usr/bin/env python3
"""Print the newest exact Release-MAJOR.MINOR.PATCH branch read from stdin."""

from __future__ import annotations

import re
import sys


RELEASE_BRANCH = re.compile(r"^Release-(\d+)\.(\d+)\.(\d+)$")


def latest_release_branch(branches: list[str]) -> str:
    candidates: list[tuple[tuple[int, int, int], str]] = []

    for branch in branches:
        branch = branch.strip()
        match = RELEASE_BRANCH.fullmatch(branch)
        if match:
            candidates.append((tuple(map(int, match.groups())), branch))

    if not candidates:
        raise ValueError("No Release-MAJOR.MINOR.PATCH branch exists")

    return max(candidates, key=lambda candidate: candidate[0])[1]


if __name__ == "__main__":
    try:
        print(latest_release_branch(sys.stdin.readlines()))
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
