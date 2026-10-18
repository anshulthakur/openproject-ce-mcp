"""Project-scope check for records that belong to a meeting.

Agenda items, sections and outcomes carry no project of their own; their
project is the one of the parent meeting. Every service that reaches such a
record checks the meeting here, so the rule lives in one place.

Functions only, in an underscore-prefixed module: every public class under
app/services/ must be named `*Service`/`*Resolver`.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...config import Settings
from ..policies import scope as scope_policy
from ..ports.meeting_api import MeetingApi
from ..version_gate import call_version_gated


async def ensure_allowed(
    meeting_api: MeetingApi,
    meeting_id: int,
    *,
    write: bool,
    settings: Settings,
    project_id_to_identifier: Mapping[int, str],
) -> None:
    meeting = await call_version_gated(lambda: meeting_api.get(meeting_id), feature="Meetings", floor="17.4")
    check = scope_policy.ensure_project_write_link_allowed if write else scope_policy.ensure_project_link_allowed
    check(meeting.project_link, settings=settings, project_id_to_identifier=project_id_to_identifier)
