from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError, ProjectScopeDeniedError
from openproject_ce_mcp.app.ports.revision_api import RevisionRecord
from openproject_ce_mcp.app.services.revision_service import RevisionService
from openproject_ce_mcp.models import RevisionSummary
from openproject_ce_mcp.presentation import _to_payload

IDENTIFIERS = {6: "demo", 7: "other"}


def _record(project_id: int | None, *, revision_id: int = 1, link: dict | None = ...) -> RevisionRecord:  # type: ignore[assignment]
    if link is ...:
        link = {"href": f"/api/v3/projects/{project_id}", "title": "P"} if project_id is not None else None
    return RevisionRecord(
        summary=RevisionSummary(
            id=revision_id,
            identifier=f"rev{revision_id}",
            formatted_identifier=f"rev{revision_id}",
            author_name="<user-content>Ada</user-content>",
            message="<user-content>Fix</user-content>",
            message_truncated=True,
            message_length=900,
            created_at="2026-10-01T10:00:00Z",
            project_id=project_id,
            project="P",
        ),
        project_link=link,
    )


class _FakeRevisionApi:
    def __init__(self, records: list[RevisionRecord]) -> None:
        self._records = records
        self.calls: list[tuple[int, int | None]] = []

    async def list_for_work_package(self, work_package_id: int, *, text_limit: int | None) -> list[RevisionRecord]:
        self.calls.append((work_package_id, text_limit))
        return self._records


def _service(records: list[RevisionRecord], *, resolve=None, **overrides) -> tuple[RevisionService, _FakeRevisionApi]:
    api = _FakeRevisionApi(records)

    async def resolve_work_package_id(ref, *, write: bool = False, context=None) -> int:
        assert write is False
        return 42

    service = RevisionService(
        api=api,
        settings=dataclasses.replace(make_settings(), **overrides),
        project_id_to_identifier=IDENTIFIERS,
        resolve_work_package_id=resolve or resolve_work_package_id,
    )
    return service, api


@pytest.mark.asyncio
async def test_rows_of_projects_outside_the_read_scope_are_dropped() -> None:
    service, api = _service(
        [_record(6, revision_id=1), _record(7, revision_id=2)], read_projects=("demo",), text_limit=300
    )

    result = await service.list_for_work_package("DEMO-1")

    assert [r.id for r in result.results] == [1]
    assert result.count == 1
    assert api.calls == [(42, 300)]


@pytest.mark.asyncio
async def test_a_row_without_a_project_link_is_dropped_under_every_scope() -> None:
    service, _ = _service([_record(None, link=None)], read_projects=("*",))

    assert (await service.list_for_work_package(42)).results == []


@pytest.mark.asyncio
async def test_a_row_with_a_malformed_project_link_is_dropped_under_every_scope() -> None:
    service, _ = _service([_record(6, link={"href": "https://evil.example/api/v3/projects/6"})], read_projects=("*",))

    assert (await service.list_for_work_package(42)).results == []


@pytest.mark.asyncio
async def test_hidden_message_masks_the_text_and_its_length() -> None:
    service, _ = _service([_record(6)], hidden_fields={"revision": ("message",)}, read_projects=("*",))

    revision = (await service.list_for_work_package(42)).results[0]

    payload = _to_payload(revision)
    assert "message" not in payload
    assert revision.message_truncated is False
    assert revision.message_length is None


@pytest.mark.asyncio
async def test_a_work_package_outside_the_read_scope_is_refused_before_any_request() -> None:
    async def resolve(ref, *, write: bool = False, context=None) -> int:
        raise ProjectScopeDeniedError("OPENPROJECT_READ_PROJECTS")

    service, api = _service([_record(6)], resolve=resolve)

    with pytest.raises(ProjectScopeDeniedError):
        await service.list_for_work_package(42)

    assert api.calls == []


@pytest.mark.asyncio
async def test_work_package_reads_must_be_enabled() -> None:
    service, api = _service([_record(6)], enable_work_package_read=False)

    with pytest.raises(PermissionDeniedError):
        await service.list_for_work_package(42)

    assert api.calls == []
