"""Decides which versions, sprints and backlog buckets a work package result may name.

A work package carries a version, sprint or bucket shared into its project from the project that
defines it, and the link names the resource without that project. The defining project comes from
one request per reference, remembered for a while. A reference counts as visible only if its
defining project is covered by the read scope; that verdict is computed on every call from the
remembered project, so a changed scope or a renamed project takes effect at once.

Depends on the `VersionApi`, `SprintApi` and `BacklogBucketApi` Ports only. It does not check that
version, sprint or bucket reads are enabled: this is a scope check on a result of another domain,
and a work package read must not fail because those reads are off.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ...config import Settings
from ..errors import NotFoundError
from ..policies.backlog_bucket_policy import backlog_bucket_payload_allowed
from ..policies.scope import defining_project_link_allowed
from ..policies.sprint_policy import sprint_payload_allowed
from ..ports.backlog_bucket_api import BacklogBucketApi
from ..ports.scoped_reference import ScopedReference
from ..ports.sprint_api import SprintApi
from ..ports.version_api import VersionApi

# Bounds the requests of all concurrent work package reads. It is its own semaphore so that a read
# holding a batch-read permit cannot wait on it for its own nested check.
_LOOKUP_CONCURRENCY = 10
# A version's project cannot be changed through the API, a sprint's or bucket's can; one window
# keeps the rule simple and bounds how long a moved resource stays unnoticed.
_FRESHNESS_SECONDS = 300.0
_MAX_ENTRIES = 4096


@dataclass(frozen=True)
class _DefiningProject:
    """What the server said about a resource's defining project; None for a resource the token
    cannot see."""

    link: Any
    embedded: dict[str, Any] | None = None


class ScopedReferenceResolver:
    def __init__(
        self,
        *,
        version_api: VersionApi,
        sprint_api: SprintApi,
        backlog_bucket_api: BacklogBucketApi,
        settings: Settings,
        project_id_to_identifier: Mapping[int, str],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._version_api = version_api
        self._sprint_api = sprint_api
        self._backlog_bucket_api = backlog_bucket_api
        self._settings = settings
        self._project_id_to_identifier = project_id_to_identifier
        self._clock = clock
        self._semaphore = asyncio.Semaphore(_LOOKUP_CONCURRENCY)
        self._known: OrderedDict[ScopedReference, tuple[float, _DefiningProject | None]] = OrderedDict()

    async def references_allowed(
        self, references: Iterable[ScopedReference]
    ) -> dict[ScopedReference, bool | Exception]:
        """One outcome per distinct reference: a remembered project is judged without a request,
        any other reference costs one. A resource the token cannot see (`NotFoundError`) is not
        allowed; any other failure is returned for the caller to re-raise."""
        outcomes: dict[ScopedReference, bool | Exception] = {}
        lookups: list[ScopedReference] = []
        for reference in dict.fromkeys(references):
            found, remembered = self._recall(reference)
            if found:
                outcomes[reference] = self._verdict(reference, remembered)
            else:
                lookups.append(reference)

        async def look_up(reference: ScopedReference) -> None:
            async with self._semaphore:
                try:
                    project = await self._fetch(reference)
                except NotFoundError:
                    project = None
                except Exception as exc:  # noqa: BLE001 -- returned as a deferred outcome, see docstring
                    outcomes[reference] = exc
                    return
            self._remember(reference, project)
            outcomes[reference] = self._verdict(reference, project)

        await asyncio.gather(*(look_up(reference) for reference in lookups))
        return outcomes

    def _recall(self, reference: ScopedReference) -> tuple[bool, _DefiningProject | None]:
        entry = self._known.get(reference)
        if entry is None or self._clock() - entry[0] > _FRESHNESS_SECONDS:
            return False, None
        self._known.move_to_end(reference)
        return True, entry[1]

    def _remember(self, reference: ScopedReference, project: _DefiningProject | None) -> None:
        self._known[reference] = (self._clock(), project)
        self._known.move_to_end(reference)
        while len(self._known) > _MAX_ENTRIES:
            self._known.popitem(last=False)

    async def _fetch(self, reference: ScopedReference) -> _DefiningProject:
        if reference.kind == "version":
            return _DefiningProject((await self._version_api.get(reference.id)).defining_project_link)
        if reference.kind == "sprint":
            sprint = await self._sprint_api.get(reference.id)
            return _DefiningProject(sprint.defining_workspace_link, sprint.defining_workspace_payload)
        bucket = await self._backlog_bucket_api.get(reference.id)
        return _DefiningProject(bucket.defining_workspace_link, bucket.defining_workspace_payload)

    def _verdict(self, reference: ScopedReference, project: _DefiningProject | None) -> bool:
        if project is None:
            return False
        settings, known = self._settings, self._project_id_to_identifier
        if reference.kind == "version":
            return defining_project_link_allowed(project.link, settings=settings, project_id_to_identifier=known)
        check = sprint_payload_allowed if reference.kind == "sprint" else backlog_bucket_payload_allowed
        return check(
            defining_workspace_payload=project.embedded,
            defining_workspace_link=project.link,
            settings=settings,
            project_id_to_identifier=known,
        )
