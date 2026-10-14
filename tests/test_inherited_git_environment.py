"""Tests run without the GIT_* variables a git hook exports (see conftest)."""

from __future__ import annotations

import os


def test_no_git_variable_reaches_a_test() -> None:
    assert [key for key in os.environ if key.startswith("GIT_")] == []
