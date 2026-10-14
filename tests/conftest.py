"""Shared unit-test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# The api-check scripts import each other as plain modules, which works when run
# as scripts (their directory is sys.path[0]) but not when a test loads one by file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "api-check"))


@pytest.fixture(autouse=True)
def _no_inherited_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # A git hook that runs the suite exports GIT_DIR and friends. A git call in
    # a test would then act on the hooked repository: git init with a
    # worktree's GIT_DIR writes core.bare=true into the shared config.
    for name in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(name)
