"""Activity-only policy. Pure, no I/O."""

from __future__ import annotations

from ...config import Settings
from .hidden_fields import hidden_patterns
from .scope import scope_allows_all


def details_allowed(settings: Settings) -> bool:
    """Whether change details may be returned. OpenProject renders them as text in the API
    user's language with no structure to check against the allowlist, and the text can name
    parents, projects and versions of projects outside it, or the value of a field the hide
    settings remove from work packages; only an unrestricted scope without such settings serves them."""
    return (
        scope_allows_all(settings.read_projects)
        and not hidden_patterns("work_package", settings=settings)
        and not settings.hide_custom_fields
    )
