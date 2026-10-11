"""The ``doctor`` command: every OpenProject entry is checked the way its client starts the server.

One client's broken entry is never hidden by another client's entry or by the shell
running the doctor.
"""

from __future__ import annotations

import platform
import sys

MIN_PYTHON = (3, 11)  # pyproject.toml's requires-python floor


def run_doctor() -> int:
    """CLI entry point for doctor command."""
    # Checked before the checks are imported: they need this Python's stdlib (tomllib).
    if sys.version_info[:2] < MIN_PYTHON:
        print(
            f"[FAIL] Python: {platform.python_version()} ({sys.executable}) "
            f"-- requires >= {'.'.join(map(str, MIN_PYTHON))}"
        )
        return 1
    # Imported here so ``python -m openproject_ce_mcp.doctor.probe`` loads only the probe.
    from .run import run_doctor as run

    return run()
