"""Revisions Domain API port -- narrow, no universal gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ...models import RevisionSummary


@dataclass(frozen=True)
class RevisionRecord:
    """One revision plus its raw project link: a revision belongs to the project of its repository, which need not
    be the work package's project, so each row is judged by its own link."""

    summary: RevisionSummary
    project_link: dict[str, Any] | None


class RevisionApi(Protocol):
    async def list_for_work_package(self, work_package_id: int, *, text_limit: int | None) -> list[RevisionRecord]: ...
