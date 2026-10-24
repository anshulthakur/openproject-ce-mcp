"""Decides which versions and sprints a work package result may name.

A work package carries a version or sprint shared into its project from the project that defines
it, and the link names the resource without that project. The defining project comes from the
resource the server embedded in the response, or from one request per reference otherwise. A
reference counts as visible only if its defining project is covered by the read scope.

Depends on the `VersionApi` and `SprintApi` Ports only. It does not check that version or sprint
reads are enabled: this is a scope check on a result of another domain, and a work package read
must not fail because version reads are off.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any

from ...config import Settings
from ..errors import NotFoundError
from ..policies import scope as scope_policy
from ..policies.sprint_policy import sprint_payload_allowed
from ..policies.version_policy import version_payload_allowed
from ..ports.scoped_reference import ScopedReference
from ..ports.sprint_api import SprintApi
from ..ports.version_api import VersionApi

# Bounds the version and sprint requests of all concurrent work package reads. It is its own
# semaphore so that a read holding a batch-read permit cannot wait on it for its own nested check.
_LOOKUP_CONCURRENCY = 10


class ScopedReferenceResolver:
    def __init__(
        self,
        *,
        version_api: VersionApi,
        sprint_api: SprintApi,
        settings: Settings,
        project_id_to_identifier: Mapping[int, str],
    ) -> None:
        self._version_api = version_api
        self._sprint_api = sprint_api
        self._settings = settings
        self._project_id_to_identifier = project_id_to_identifier
        self._semaphore = asyncio.Semaphore(_LOOKUP_CONCURRENCY)

    async def references_allowed(
        self, references: Iterable[ScopedReference], *, seeds: Mapping[ScopedReference, Mapping[str, Any]]
    ) -> dict[ScopedReference, bool | Exception]:
        """One outcome per distinct reference: a seed is judged without a request, any other
        reference by one request. `NotFoundError` means the resource is not visible to the token,
        which is not allowed; any other failure is returned for the caller to re-raise."""
        outcomes: dict[ScopedReference, bool | Exception] = {}
        lookups: list[ScopedReference] = []
        for reference in dict.fromkeys(references):
            seed = seeds.get(reference)
            if seed is not None:
                outcomes[reference] = self._seed_allowed(reference, seed)
            else:
                lookups.append(reference)

        async def look_up(reference: ScopedReference) -> None:
            async with self._semaphore:
                try:
                    outcomes[reference] = await self._fetched_allowed(reference)
                except asyncio.CancelledError:
                    raise
                except NotFoundError:
                    outcomes[reference] = False
                except Exception as exc:  # noqa: BLE001 -- returned as a deferred outcome, see docstring
                    outcomes[reference] = exc

        await asyncio.gather(*(look_up(reference) for reference in lookups))
        return outcomes

    def _seed_allowed(self, reference: ScopedReference, seed: Mapping[str, Any]) -> bool:
        links = seed.get("_links", {})
        if reference.kind == "version":
            return version_payload_allowed(
                dict(seed), settings=self._settings, project_id_to_identifier=self._project_id_to_identifier
            )
        embedded = seed.get("_embedded", {})
        return sprint_payload_allowed(
            defining_workspace_payload=embedded.get("definingWorkspace"),
            defining_workspace_link=links.get("definingWorkspace"),
            settings=self._settings,
            project_id_to_identifier=self._project_id_to_identifier,
        )

    async def _fetched_allowed(self, reference: ScopedReference) -> bool:
        if reference.kind == "version":
            version = await self._version_api.get(reference.id)
            return scope_policy.project_link_allowed(
                version.defining_project_link,
                settings=self._settings,
                project_id_to_identifier=self._project_id_to_identifier,
            )
        sprint = await self._sprint_api.get(reference.id)
        return sprint_payload_allowed(
            defining_workspace_payload=sprint.defining_workspace_payload,
            defining_workspace_link=sprint.defining_workspace_link,
            settings=self._settings,
            project_id_to_identifier=self._project_id_to_identifier,
        )
