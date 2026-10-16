from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import InvalidInputError, PermissionDeniedError
from openproject_ce_mcp.app.ports.meeting_api import MeetingRecord
from openproject_ce_mcp.app.services.meeting_service import MeetingService
from openproject_ce_mcp.models import MeetingSummary


def _summary(meeting_id: int = 12, **extra) -> MeetingSummary:
    defaults = {
        "id": meeting_id,
        "title": "Sprint Planning",
        "location": None,
        "lock_version": 0,
        "start_time": "2026-09-01T09:00:00Z",
        "end_time": "2026-09-01T10:00:00Z",
        "duration": "PT1H",
        "state": "open",
        "sharing": "invited",
        "template": False,
        "notify": True,
        "author": "Alice",
        "participants": [],
        "project_id": 6,
        "project": "Demo",
        "recurring_meeting_id": None,
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
    }
    defaults.update(extra)
    return MeetingSummary(**defaults)


class _FormResult:
    def __init__(self, payload, validation_errors=None):
        self.payload = payload
        self.validation_errors = validation_errors or {}


class _FakeMeetingApi:
    def __init__(self, records: list[MeetingRecord] | None = None, *, project_link=None) -> None:
        self._records = records or [
            MeetingRecord(
                summary=_summary(), project_link=project_link or {"href": "/api/v3/projects/6", "title": "Demo"}
            )
        ]
        self.list_calls: list[tuple[int, int, int | None]] = []
        self.create_form_calls: list[dict] = []
        self.update_form_calls: list[tuple[int, dict]] = []
        self.commit_create_calls: list[dict] = []
        self.commit_update_calls: list[tuple[int, dict]] = []
        self.delete_calls: list[int] = []

    async def list_page(self, *, offset: int, limit: int, project_id: int | None, title: str | None = None, **kwargs):
        self.list_calls.append((offset, limit, project_id, title))
        return list(self._records), len(self._records)

    async def get(self, meeting_id: int) -> MeetingRecord:
        return self._records[0]

    async def create_form(self, payload: dict):
        self.create_form_calls.append(payload)
        return _FormResult(payload)

    async def update_form(self, meeting_id: int, payload: dict):
        self.update_form_calls.append((meeting_id, payload))
        return _FormResult(payload)

    async def commit_create(self, payload: dict) -> MeetingRecord:
        self.commit_create_calls.append(payload)
        return MeetingRecord(summary=_summary(), project_link={"href": "/api/v3/projects/6", "title": "Demo"})

    async def commit_update(self, meeting_id: int, payload: dict) -> MeetingRecord:
        self.commit_update_calls.append((meeting_id, payload))
        return MeetingRecord(
            summary=_summary(title="Updated"), project_link={"href": "/api/v3/projects/6", "title": "Demo"}
        )

    async def delete(self, meeting_id: int) -> None:
        self.delete_calls.append(meeting_id)


async def _resolve_project_ref_ok(project_ref, *, write: bool = False, context=None):
    return {"id": 6, "name": "Demo", "identifier": "demo"}


async def _resolve_project_ref_denied(project_ref, *, write: bool = False, context=None):
    raise PermissionDeniedError("OpenProject writes to this project are disabled.")


async def _resolve_project_id_ok(project_ref, *, write: bool = False):
    return "6"


async def _resolve_principal_id_ok(ref):
    return "5"


def _service(
    *,
    api: _FakeMeetingApi | None = None,
    settings=None,
    resolve_project_ref=None,
    resolve_project_id=None,
    resolve_principal_id=None,
) -> MeetingService:
    return MeetingService(
        api=api or _FakeMeetingApi(),
        settings=settings or make_settings(),
        project_id_to_identifier={6: "demo"},
        resolve_project_ref=resolve_project_ref or _resolve_project_ref_ok,
        resolve_project_id=resolve_project_id or _resolve_project_id_ok,
        resolve_principal_id=resolve_principal_id or _resolve_principal_id_ok,
        api_prefix="/api/v3/",
    )


# --- list_all ----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_returns_stamped_results() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.list_all()

    assert result.count == 1
    assert result.results[0].title == "Sprint Planning"


@pytest.mark.asyncio
async def test_list_all_passes_the_title_filter_to_the_api() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    await service.list_all(title="planning")

    assert api.list_calls[0][3] == "planning"


@pytest.mark.asyncio
async def test_list_all_masks_hidden_title() -> None:
    settings = dataclasses.replace(make_settings(), hidden_fields={"meeting": ("title",)})
    service = _service(settings=settings)

    result = await service.list_all()

    assert getattr(result.results[0], "_hidden_keys", frozenset()) == {"title"}


@pytest.mark.asyncio
async def test_list_all_filters_out_disallowed_project_under_client_side_scan() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("other-project",))
    api = _FakeMeetingApi(project_link={"href": "/api/v3/projects/6", "title": "Demo"})
    service = _service(api=api, settings=settings)

    result = await service.list_all()

    assert result.count == 0


# --- get -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_stamped_summary() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.get(12)

    assert result.id == 12


@pytest.mark.asyncio
async def test_get_denies_read_outside_read_allowlist() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("other-project",))
    api = _FakeMeetingApi()
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.get(12)


# --- create ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_preview_without_confirm_does_not_call_commit() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.create(project="demo", title="Sprint Planning", confirm=False)

    assert result.state == "preview"
    assert result.result is None
    assert api.commit_create_calls == []
    assert api.create_form_calls


@pytest.mark.asyncio
async def test_create_commit_with_confirm_calls_commit_create() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.create(project="demo", title="Sprint Planning", confirm=True)

    assert result.state == "confirmed"
    assert result.result is not None
    assert api.commit_create_calls


@pytest.mark.asyncio
async def test_create_denies_write_outside_write_allowlist() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api, resolve_project_ref=_resolve_project_ref_denied)

    with pytest.raises(PermissionDeniedError):
        await service.create(project="demo", title="Sprint Planning", confirm=True)

    assert api.create_form_calls == []


@pytest.mark.asyncio
async def test_create_denies_write_even_without_confirm() -> None:
    """The write-allowlist check (via resolve_project_ref(..., write=True)) runs
    before the confirm branch -- must fire on a preview call too."""
    api = _FakeMeetingApi()
    service = _service(api=api, resolve_project_ref=_resolve_project_ref_denied)

    with pytest.raises(PermissionDeniedError):
        await service.create(project="demo", title="Sprint Planning", confirm=False)

    assert api.create_form_calls == []


@pytest.mark.asyncio
async def test_create_resolves_participant_refs() -> None:
    api = _FakeMeetingApi()
    resolved_refs: list[str] = []

    async def resolve_principal_id(ref: str) -> str:
        resolved_refs.append(ref)
        return "5"

    service = _service(api=api, resolve_principal_id=resolve_principal_id)

    await service.create(project="demo", title="Standup", participant_user_refs=["alice"], confirm=False)

    assert resolved_refs == ["alice"]
    assert api.create_form_calls[0]["_links"]["participants"] == [{"href": "/api/v3/users/5"}]


# --- update ------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_preview_without_confirm_does_not_call_commit() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.update(meeting_id=12, title="Updated", confirm=False)

    assert result.state == "preview"
    assert api.commit_update_calls == []


@pytest.mark.asyncio
async def test_update_commit_with_confirm_calls_commit_update() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.update(meeting_id=12, title="Updated", confirm=True)

    assert result.state == "confirmed"
    assert api.commit_update_calls


@pytest.mark.asyncio
async def test_update_denies_write_outside_write_allowlist() -> None:
    settings = dataclasses.replace(make_settings(), write_projects=("other-project",))
    api = _FakeMeetingApi()
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.update(meeting_id=12, title="Updated", confirm=True)

    assert api.update_form_calls == []


@pytest.mark.asyncio
async def test_update_denies_write_even_without_confirm() -> None:
    settings = dataclasses.replace(make_settings(), write_projects=("other-project",))
    api = _FakeMeetingApi()
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.update(meeting_id=12, title="Updated", confirm=False)

    assert api.update_form_calls == []


# --- delete ------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_preview_without_confirm_does_not_call_api_delete() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.delete(meeting_id=12, confirm=False)

    assert result.state == "preview"
    assert api.delete_calls == []


@pytest.mark.asyncio
async def test_delete_commit_with_confirm_calls_api_delete() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.delete(meeting_id=12, confirm=True)

    assert result.state == "confirmed"
    assert api.delete_calls == [12]


@pytest.mark.asyncio
async def test_delete_denies_write_outside_write_allowlist() -> None:
    settings = dataclasses.replace(make_settings(), write_projects=("other-project",))
    api = _FakeMeetingApi()
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.delete(meeting_id=12, confirm=True)

    assert api.delete_calls == []


@pytest.mark.asyncio
async def test_delete_denies_write_even_without_confirm() -> None:
    settings = dataclasses.replace(make_settings(), write_projects=("other-project",))
    api = _FakeMeetingApi()
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.delete(meeting_id=12, confirm=False)

    assert api.delete_calls == []


def _api_with(summary: MeetingSummary) -> _FakeMeetingApi:
    return _FakeMeetingApi(
        [MeetingRecord(summary=summary, project_link={"href": "/api/v3/projects/6", "title": "Demo"})]
    )


_SERIES_TEMPLATE = {"template": True, "recurring_meeting_id": 91}


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_delete_rejects_the_template_of_a_recurring_series(confirm: bool) -> None:
    api = _api_with(_summary(412, **_SERIES_TEMPLATE))
    service = _service(api=api)

    with pytest.raises(InvalidInputError, match="meeting_id 412 is the template of recurring meeting 91"):
        await service.delete(meeting_id=412, confirm=confirm)

    assert api.delete_calls == []


@pytest.mark.asyncio
async def test_delete_allows_a_one_time_template() -> None:
    api = _api_with(_summary(13, template=True, recurring_meeting_id=None))
    service = _service(api=api)

    result = await service.delete(meeting_id=13, confirm=True)

    assert result.state == "confirmed"
    assert api.delete_calls == [13]


@pytest.mark.asyncio
async def test_delete_allows_an_occurrence_of_a_series() -> None:
    api = _api_with(_summary(14, template=False, recurring_meeting_id=91))
    service = _service(api=api)

    result = await service.delete(meeting_id=14, confirm=True)

    assert result.state == "confirmed"
    assert api.delete_calls == [14]


@pytest.mark.asyncio
async def test_delete_checks_the_write_allowlist_before_naming_the_series() -> None:
    settings = dataclasses.replace(make_settings(), write_projects=("other-project",))
    api = _api_with(_summary(412, **_SERIES_TEMPLATE))
    service = _service(api=api, settings=settings)

    with pytest.raises(PermissionDeniedError):
        await service.delete(meeting_id=412, confirm=True)

    assert api.delete_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [{"state": "open"}, {"state": "draft"}, {"notify": True}, {"notify": False}, {"state": "open", "notify": True}],
)
@pytest.mark.parametrize("confirm", [False, True])
async def test_create_rejects_state_and_notify_before_any_lookup_or_request(kwargs: dict, confirm: bool) -> None:
    api = _FakeMeetingApi()
    lookups: list[str] = []

    async def _resolve_and_record(project_ref, *, write: bool = False, context=None):
        lookups.append(project_ref)
        return {"id": 6, "name": "Demo", "identifier": "demo"}

    service = _service(api=api, resolve_project_ref=_resolve_and_record)

    with pytest.raises(InvalidInputError, match="does not apply state or notify.*update_meeting"):
        await service.create(project="demo", title="Weekly", confirm=confirm, **kwargs)

    assert lookups == []
    assert api.create_form_calls == []
    assert api.commit_create_calls == []


@pytest.mark.asyncio
async def test_create_without_state_and_notify_is_unchanged() -> None:
    api = _FakeMeetingApi()
    service = _service(api=api)

    result = await service.create(project="demo", title="Weekly", confirm=True)

    assert result.state == "confirmed"
    assert len(api.create_form_calls) == 1
    assert len(api.commit_create_calls) == 1
