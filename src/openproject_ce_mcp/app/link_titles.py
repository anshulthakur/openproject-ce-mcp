"""Link titles of a write preview.

A preview echoes the form OpenProject returns, whose links carry the title and display id of
what they point to. A link such as `parent`, `version` or a custom field value can point into a
project the read allowlist does not cover and would show its subject or name. Only links to
resources every user of the instance sees alike, or to the project the write targets, keep
their title; every other link keeps its href.
"""

from __future__ import annotations

from typing import Any

_TITLE_KEYS = ("title", "displayId")

KEPT_LINK_NAMES = frozenset(
    {
        "self",
        "type",
        "status",
        "priority",
        "project",
        "category",
        "projectPhase",
        "projectPhaseDefinition",
        "assignee",
        "responsible",
        "author",
        "user",
        "principal",
        "role",
        "roles",
        "activity",
        "filter",
        "operator",
    }
)


# The query filters whose values are such resources; the values of any other filter (project,
# subproject, parent, version, work package ...) can name something in another project.
KEPT_FILTER_KEYS = frozenset({"status", "type", "priority", "assignee", "author", "responsible"})


def without_foreign_capable_titles(value: Any) -> Any:
    """A copy of a preview payload in which every link outside `KEPT_LINK_NAMES` has no title and
    no display id."""
    if isinstance(value, list):
        return [without_foreign_capable_titles(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _links(child) if key == "_links" and isinstance(child, dict) else without_foreign_capable_titles(child)
        for key, child in value.items()
    }


def _links(links: dict[str, Any]) -> dict[str, Any]:
    return {name: _link(link, keep_titles=name in KEPT_LINK_NAMES) for name, link in links.items()}


def _link(link: Any, *, keep_titles: bool) -> Any:
    return link if keep_titles else without_titles(link)


def without_titles(link: Any) -> Any:
    """A link (or list of links) with no title and no display id."""
    if isinstance(link, list):
        return [without_titles(item) for item in link]
    if not isinstance(link, dict):
        return link
    return {key: child for key, child in link.items() if key not in _TITLE_KEYS}
