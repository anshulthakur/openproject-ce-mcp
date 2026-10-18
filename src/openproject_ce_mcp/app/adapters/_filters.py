"""Filter values for OpenProject collection filters."""

from __future__ import annotations


def escape_like(text: str) -> str:
    """OpenProject 16.0 to 17.9 build `LIKE '%value%'` from the value of the project and user
    name filters without escaping, so `_` and `%` in the search text would act as wildcards
    (PostgreSQL's escape is the backslash). Drop this once a release escapes the value itself."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
