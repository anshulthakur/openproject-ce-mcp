"""The ``doctor`` command: every OpenProject entry is checked the way its client starts the server.

One client's broken entry is never hidden by another client's entry or by the shell
running the doctor.
"""

from __future__ import annotations


def run_doctor() -> int:
    """CLI entry point for doctor command."""
    # Imported here so ``python -m openproject_ce_mcp.doctor.probe`` loads only the probe.
    from .run import run_doctor as run

    return run()
