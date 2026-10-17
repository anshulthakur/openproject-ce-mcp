"""MCP tool annotations derived from what each tool can do to OpenProject.

Clients act on these hints (VS Code skips its confirmation for read-only
tools), so a write tool marked read-only would let it run without a human.
A write tool is annotated by what ``confirm=true`` does, never by its
preview. Generic verbs are classified by name prefix; every tool whose
effect differs from its verb is listed explicitly, so a new tool with an
unknown verb fails at import instead of shipping unannotated.

``idempotentHint`` is true only if a second identical confirmed call changes
nothing at all on any supported OpenProject version: no data, timestamp,
revision counter, journal, queued job, notification, mail or webhook.
Annotations are per tool, so an effect that only some arguments or some
versions cause still makes the tool non-idempotent.

``openWorldHint`` is true for every tool: each call acts on an external
OpenProject instance whose data other users change. Notifications OpenProject
sends as a side effect, and reordering or recalculating derived values
around a new item, do not make a tool destructive here; changed or removed
existing data does.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum, auto

from mcp.types import ToolAnnotations


class Effect(Enum):
    READ = auto()
    # Creates something new and changes nothing that exists.
    ADDITIVE = auto()
    # Sets existing state to the given value; repeating it changes nothing more.
    OVERWRITE = auto()
    # Sets existing state, and a repeat still changes or sends something.
    OVERWRITE_WITH_REPEAT_EFFECT = auto()
    REMOVE = auto()
    # Removes existing data, and a repeat still changes or sends something.
    REMOVE_WITH_REPEAT_EFFECT = auto()
    TOGGLE = auto()
    # Changes existing data beyond what it was asked for, and a repeat acts again.
    REPLACE = auto()


# (read_only, destructive, idempotent)
_HINTS: dict[Effect, tuple[bool, bool, bool]] = {
    Effect.READ: (True, False, True),
    Effect.ADDITIVE: (False, False, False),
    Effect.OVERWRITE: (False, True, True),
    Effect.OVERWRITE_WITH_REPEAT_EFFECT: (False, True, False),
    Effect.REMOVE: (False, True, True),
    Effect.REMOVE_WITH_REPEAT_EFFECT: (False, True, False),
    Effect.TOGGLE: (False, True, False),
    Effect.REPLACE: (False, True, False),
}

_EFFECT_BY_PREFIX: dict[str, Effect] = {
    "create": Effect.ADDITIVE,
    "bulk_create": Effect.ADDITIVE,
    "update": Effect.OVERWRITE,
    "bulk_update": Effect.OVERWRITE,
    "set": Effect.OVERWRITE,
    "delete": Effect.REMOVE,
    "toggle": Effect.TOGGLE,
}

_EFFECT_BY_TOOL: dict[str, Effect] = {
    "add_work_package_comment": Effect.ADDITIVE,
    "copy_project": Effect.ADDITIVE,
    # Cancelling an already cancelled occurrence is answered 204 without effect.
    "cancel_recurring_meeting_occurrence": Effect.OVERWRITE,
    # A repeat returns the existing occurrence, or the slot's unique index
    # refuses it, without writing; restoring a cancelled one resets it to the
    # template (ResetToTemplateService).
    "init_recurring_meeting_occurrence": Effect.OVERWRITE,
    # The single-notification route sets updated_at on every call, read or not.
    "mark_notifications_read": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # Every update bumps the series' ical_sequence (bump_ical_sequence!).
    "update_recurring_meeting": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # For a series template id, every update bumps the series' ical_sequence.
    "update_meeting": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # Every update touches the parent meeting (touch_and_save_journals).
    "update_meeting_agenda_item": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # The committed form payload's filters re-save the query on every call.
    "update_board": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # For a user, Members::UpdateService sends MEMBER_UPDATED (a mail) after
    # every successful call.
    "update_membership": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # Projects::UpdateService sends PROJECT_UPDATED (project webhooks) after
    # every successful call.
    "update_project": Effect.OVERWRITE_WITH_REPEAT_EFFECT,
    # Every call schedules another DeleteProjectJob.
    "delete_project": Effect.REMOVE_WITH_REPEAT_EFFECT,
    # Before OpenProject 16.4, every call schedules another Principals::DeleteJob.
    "delete_user": Effect.REMOVE_WITH_REPEAT_EFFECT,
    "delete_group": Effect.REMOVE_WITH_REPEAT_EFFECT,
    # A parent or a follows/precedes relation switches the affected existing
    # work package to automatic scheduling and moves its dates.
    "create_work_package": Effect.REPLACE,
    "create_subtask": Effect.REPLACE,
    "bulk_create_work_packages": Effect.REPLACE,
    "create_work_package_relation": Effect.REPLACE,
    # A reverse type (precedes, blocked, ...) swaps from and to on every save
    # (Relation#reverse_if_needed), so a repeat flips the direction back.
    "update_relation": Effect.REPLACE,
}


def build_tool_annotations(read_names: Iterable[str], write_names: Iterable[str]) -> dict[str, ToolAnnotations]:
    """Annotations for every read and write tool; raises for a write tool no rule classifies."""
    write_names = tuple(write_names)
    stale = sorted(set(_EFFECT_BY_TOOL) - set(write_names))
    if stale:
        raise ValueError(f"Effect table names tools that are not classified write tools: {', '.join(stale)}")
    annotations = {name: _annotations(Effect.READ) for name in read_names}
    for name in write_names:
        annotations[name] = _annotations(_write_effect(name))
    return annotations


def _write_effect(name: str) -> Effect:
    if name in _EFFECT_BY_TOOL:
        return _EFFECT_BY_TOOL[name]
    matches = [effect for prefix, effect in _EFFECT_BY_PREFIX.items() if name.startswith(f"{prefix}_")]
    if len(matches) != 1:
        raise ValueError(
            f"No write effect for tool {name!r}: give its verb a prefix rule or the tool an entry in _EFFECT_BY_TOOL"
        )
    return matches[0]


def _annotations(effect: Effect) -> ToolAnnotations:
    read_only, destructive, idempotent = _HINTS[effect]
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=True,
    )
