"""Projects-only policy. Pure, no I/O.

Read/write allowlist checks for projects, built on the shared scope.py
primitives rather than duplicating candidate-matching logic here.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ..errors import PermissionDeniedError
from .scope import project_payload_candidates, project_record_candidates, scope_allows_all, scope_matches_candidates


def ensure_project_read_allowed(payload: dict[str, Any], *, settings: Settings) -> None:
    """Read-allowlist check on an already-resolved project payload."""
    if scope_allows_all(settings.read_projects):
        return
    if not scope_matches_candidates(settings.read_projects, project_payload_candidates(payload)):
        raise PermissionDeniedError("OpenProject access to this project is disabled by OPENPROJECT_READ_PROJECTS.")


def ensure_project_write_allowed(payload: dict[str, Any], *, settings: Settings) -> None:
    """Read- AND write-allowlist check (write implies read), for update/delete/favorite."""
    ensure_project_read_allowed(payload, settings=settings)
    if scope_allows_all(settings.write_projects):
        return
    if not scope_matches_candidates(settings.write_projects, project_payload_candidates(payload)):
        raise PermissionDeniedError("OpenProject writes to this project are disabled by OPENPROJECT_WRITE_PROJECTS.")


def ensure_project_create_target_allowed(
    *,
    identifier: str | None,
    name: str | None,
    settings: Settings,
) -> None:
    """Read- then write-allowlist check on an intended create/copy target.

    No resolved payload with an `id` exists yet at create time, so this checks
    the intended identifier/name directly -- read is checked first, then
    write, since a writable target must also be readable.
    """
    candidates = project_record_candidates(None, identifier, name)
    if not scope_allows_all(settings.read_projects) and not scope_matches_candidates(
        settings.read_projects, candidates
    ):
        raise PermissionDeniedError("OpenProject access to this project is disabled by OPENPROJECT_READ_PROJECTS.")
    if not scope_allows_all(settings.write_projects) and not scope_matches_candidates(
        settings.write_projects, candidates
    ):
        raise PermissionDeniedError("OpenProject writes to this project are disabled by OPENPROJECT_WRITE_PROJECTS.")
