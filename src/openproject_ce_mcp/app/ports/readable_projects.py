"""The projects whose work packages the read allowlist covers: matched by
OPENPROJECT_READ_PROJECTS and not archived."""

from __future__ import annotations

from typing import Protocol


class ReadableProjects(Protocol):
    async def current_readable_project_ids(self) -> frozenset[int]:
        """Rescanned when the last scan is old enough that a new project could
        be missing; every project its id alone does not match is re-read."""
        ...
