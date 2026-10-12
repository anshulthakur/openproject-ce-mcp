"""Integration tests for notification read/write operations.

OpenProject never sends a notification for a change the acting user makes
themselves (self-notifications are suppressed by design) -- confirmed live
against this suite's own test instance: creating a work package, assigning
it to the calling user, and adding a comment all produced zero
notifications for that same user. Most tests here exercise the real
(possibly empty) notification list from the admin token's own inbox.

The two confirmed-write tests use second_user_client (a real second user,
its own minted token -- see conftest.py, which needs the disposable Docker
instance) to trigger genuine notifications FOR the admin: a comment from
that user on a work package the admin watches.
test_mark_notification_read_confirmed_roundtrip marks ONE such notification
read. test_mark_all_notifications_read_rewrites_only_unread confirms
mark_all_notifications_read, which also marks every other unread
notification of the admin read; it records them first and marks them unread
again afterwards through the API.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json

import httpx
import pytest

from openproject_ce_mcp.client import OpenProjectClient, PermissionDeniedError

pytestmark = pytest.mark.integration


async def test_list_notifications(client: OpenProjectClient) -> None:
    result = await client.notification.list_all()
    assert result is not None
    assert result.count >= 0
    assert result.total >= 0
    if result.count > 0:
        assert result.results[0].subject


async def test_list_notifications_unread_only(client: OpenProjectClient) -> None:
    result = await client.notification.list_all(unread_only=True)
    assert result is not None
    assert result.count >= 0
    # Proves the actual filter contract, not just that a call succeeded --
    # every returned notification must genuinely be unread.
    assert all(n.read is False for n in result.results)


async def test_list_notifications_scoped_by_read_allowlist(client: OpenProjectClient) -> None:
    """_notification_payload_allowed gates each notification by its project
    (or, absent a project link, its resolved work package) -- under a
    read-allowlist that permits nothing, the list must come back empty
    rather than raising."""
    denied_settings = dataclasses.replace(client.settings, read_projects=())
    denied_client = OpenProjectClient(denied_settings)
    await denied_client.initialize()

    result = await denied_client.notification.list_all()
    assert result.count == 0


async def test_mark_notification_read_preview_does_not_write(client: OpenProjectClient) -> None:
    """No real notification exists to mark read in this suite (see module
    docstring) -- confirm the preview path is side-effect-free and reports
    requires_confirmation, without ever calling confirm=true against a real
    notification id."""
    preview = await client.notification.mark_read(999999999, confirm=False)
    assert preview.state == "preview"


async def test_mark_all_notifications_read_preview_does_not_write(client: OpenProjectClient) -> None:
    """Deliberately never confirmed -- see module docstring. Only the
    preview/dry-run path is safe to exercise against a real account."""
    preview = await client.notification.mark_all_read(confirm=False)
    assert preview.state == "preview"


async def test_mark_notification_read_denied_when_personal_write_disabled(client: OpenProjectClient) -> None:
    disabled_settings = dataclasses.replace(client.settings, enable_personal_write=False)
    disabled_client = OpenProjectClient(disabled_settings)
    await disabled_client.initialize()

    with pytest.raises(PermissionDeniedError):
        await disabled_client.notification.mark_read(999999999, confirm=True)


async def _admit_second_user(
    client: OpenProjectClient, test_project: str, second_user_client: tuple[int, OpenProjectClient]
) -> OpenProjectClient:
    second_user_id, second_client = second_user_client
    roles = await client.role.list_roles()
    role_name = next((r.name for r in roles.results if r.name == "Member"), None)
    if role_name is None:
        pytest.skip("instance has no 'Member' role configured")
    membership = await client.membership.create(
        project=test_project, principal=str(second_user_id), roles=[role_name], confirm=True
    )
    assert membership.ready, membership.validation_errors

    # second_client.initialize() (already called once by the second_user_client
    # fixture, before this membership existed) is what populates
    # project_id_to_identifier -- it walks list_projects() for projects the
    # token owner can currently see. At fixture-creation time the second user
    # had no membership yet, so that walk found nothing and the cache stayed
    # empty; re-running it now (after create_membership above) populates it,
    # which the write-allowlist check in add_comment needs to map the work
    # package's numeric project id back to test_project's identifier.
    await second_client.initialize()
    return second_client


async def _notification_from_second_user(
    client: OpenProjectClient, second_client: OpenProjectClient, test_project: str, wp_ids: list[int]
) -> int:
    me = await client.current_user.get_current_user()
    wp_result = await client.work_package.create(
        project=test_project, type="Task", subject="Integration test WP for notifications", confirm=True
    )
    assert wp_result.ready, wp_result.validation_errors
    wp_id = wp_result.work_package_id
    assert wp_id is not None
    wp_ids.append(wp_id)

    watch_result = await client.watcher.add(wp_id, me.id, confirm=True)
    assert watch_result.state == "confirmed"

    # The comment must come from a DIFFERENT user (second_client) -- OpenProject
    # never notifies a user about their own change (see module docstring).
    # notify=True is required here: OpenProject's own `notify` request param
    # maps directly to `send_notifications`, and False (this tool's own
    # default, chosen to avoid unwanted emails in the common case) suppresses
    # notification creation entirely server-side, not just outbound email --
    # confirmed live (a notify=False comment produced zero Notification rows
    # and zero enqueued Notifications::WorkflowJob work at all).
    comment_result = await second_client.work_package.add_comment(
        work_package_id=wp_id,
        comment="Comment from a different user to trigger a real notification",
        notify=True,
        confirm=True,
    )
    assert comment_result.ready, comment_result.validation_errors

    # This is a genuine test failure, not a skip, if it never appears: every
    # precondition above (comment from a different user, notify=True,
    # work_package_commented enabled via docker/test/seed.rb) was set up
    # specifically to make this deterministic against the seeded Docker
    # instance this suite is meant to run against -- an absent notification
    # here means notification generation or listing actually regressed, not
    # environment flakiness to shrug off. The wait window is 20s (not 10s):
    # under load (the full suite running back-to-back), GoodJob's queue can
    # fall behind enough that 10s occasionally isn't enough even though the
    # notification always eventually appears -- widened after an observed
    # spurious failure that a same-config re-run (isolated and full-suite)
    # could not reproduce.
    for _ in range(20):
        listed = await client.notification.list_all(unread_only=True)
        match = next((n for n in listed.results if n.work_package_id == wp_id), None)
        if match is not None:
            return match.id
        await asyncio.sleep(1)
    pytest.fail("no notification appeared for the watched work package within the wait window")


async def test_mark_notification_read_confirmed_roundtrip(
    client: OpenProjectClient,
    test_project: str,
    wp_ids: list[int],
    second_user_client: tuple[int, OpenProjectClient],
) -> None:
    """Confirms a real write against a single, specifically identified
    notification. See module docstring for why a second real user is
    required to trigger a genuine notification at all."""
    second_client = await _admit_second_user(client, test_project, second_user_client)
    notification_id = await _notification_from_second_user(client, second_client, test_project, wp_ids)

    marked = await client.notification.mark_read(notification_id, confirm=True)
    assert marked.state == "confirmed"
    assert marked.notification_id == notification_id

    # Confirm the read actually took effect server-side, not just that the
    # write call itself reported success -- a no-op 2xx response would
    # otherwise pass this test just as well as a real state change.
    after = await client.notification.list_all(unread_only=True)
    assert notification_id not in {n.id for n in after.results}


async def _raw_notification(http: httpx.AsyncClient, notification_id: int) -> dict:
    response = await http.get(f"notifications/{notification_id}")
    response.raise_for_status()
    return response.json()


async def _raw_unread_ids(http: httpx.AsyncClient) -> list[int]:
    filters = json.dumps([{"readIAN": {"operator": "=", "values": ["f"]}}])
    ids: list[int] = []
    offset = 1
    while True:
        response = await http.get("notifications", params={"filters": filters, "offset": offset, "pageSize": 100})
        response.raise_for_status()
        payload = response.json()
        elements = payload["_embedded"]["elements"]
        ids.extend(element["id"] for element in elements)
        if not elements or len(ids) >= payload["total"]:
            return ids
        offset += 1


async def test_mark_all_notifications_read_rewrites_only_unread(
    client: OpenProjectClient,
    test_project: str,
    wp_ids: list[int],
    second_user_client: tuple[int, OpenProjectClient],
) -> None:
    """Without a filter, OpenProject's bulk route sets read_ian and
    updated_at on every visible notification, so an already-read one would
    get a new updatedAt. Only the unread ones may change."""
    second_client = await _admit_second_user(client, test_project, second_user_client)
    already_read_id = await _notification_from_second_user(client, second_client, test_project, wp_ids)
    unread_id = await _notification_from_second_user(client, second_client, test_project, wp_ids)

    async with httpx.AsyncClient(
        base_url=f"{client.settings.api_base_url}/",
        auth=("apikey", client.settings.api_token),
        timeout=client.settings.timeout,
    ) as http:
        marked = await client.notification.mark_read(already_read_id, confirm=True)
        assert marked.state == "confirmed"
        already_read_before = await _raw_notification(http, already_read_id)
        assert already_read_before["readIAN"] is True

        unread_before = await _raw_unread_ids(http)
        assert unread_id in unread_before
        try:
            marked_all = await client.notification.mark_all_read(confirm=True)
            assert marked_all.state == "confirmed"

            already_read_after = await _raw_notification(http, already_read_id)
            assert already_read_after["updatedAt"] == already_read_before["updatedAt"]
            assert already_read_after["readIAN"] is True
            assert (await _raw_notification(http, unread_id))["readIAN"] is True
            assert set(unread_before).isdisjoint(await _raw_unread_ids(http))
        finally:
            # Restoring moves each notification's updatedAt; only its read state comes back.
            failed = []
            for notification_id in unread_before:
                response = await http.post(f"notifications/{notification_id}/unread_ian", json={})
                if response.is_error:
                    failed.append((notification_id, response.status_code))
            assert not failed, f"could not mark these notifications unread again: {failed}"
