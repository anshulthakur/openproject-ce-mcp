"""Rendered-text-only policy. Pure, no I/O."""

from __future__ import annotations

from ...config import Settings
from ..errors import PermissionDeniedError
from .hidden_fields import hidden_patterns
from .scope import scope_allows_all

# The entities whose name, title or display id a macro can render.
MACRO_ENTITIES = (
    "work_package",
    "project",
    "version",
    "document",
    "meeting",
    "post",
    "user",
    "group",
    "principal",
    "view",
)


def ensure_render_allowed(settings: Settings) -> None:
    """OpenProject expands macros such as `#123` or `version#4` into the name or display id of the
    record they name, in markdown and plain text alike and whatever its project, and the request
    carries no record to check them against; only an unrestricted scope without hidden fields of
    those records may render."""
    if not scope_allows_all(settings.read_projects):
        raise PermissionDeniedError(
            "render_text is disabled by OPENPROJECT_READ_PROJECTS: OpenProject renders macros such as #123 or "
            "version#4 into the name or display id of any record, whatever its project. "
            "Set OPENPROJECT_READ_PROJECTS=* to allow it."
        )
    hidden = [entity for entity in MACRO_ENTITIES if hidden_patterns(entity, settings=settings)]
    if hidden:
        raise PermissionDeniedError(
            "render_text is disabled while fields of "
            + ", ".join(hidden)
            + " are hidden: OpenProject renders macros such as #123 or version#4 into the name or "
            "display id of the record they name, which a hide setting would remove from other results."
        )
