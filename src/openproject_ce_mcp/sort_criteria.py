"""The sort-criterion grammar, as a pure rule shared by the tool layer and
`app/`, neither of which may import the other."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import SortCriterion

# ASCII on purpose: OpenProject column names are ASCII, and its link parser
# matches only ASCII word characters or percent escapes.
_FIELD = re.compile(r"[A-Za-z0-9_.]+")


def parse_sort_criterion(value: str, *, label: str) -> SortCriterion:
    """Parse "field:direction", "field-direction" or a bare "field" (ascending);
    the direction is case-insensitive. Raises ValueError naming `label`."""
    text = value.strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    if ":" in text:
        field, _, direction = text.partition(":")
    elif "-" in text:
        field, direction = text.rsplit("-", 1)
    else:
        field, direction = text, "asc"
    field = field.strip()
    direction = direction.strip().lower()
    if not field:
        raise ValueError(f"{label}: field name cannot be empty")
    if direction not in ("asc", "desc"):
        raise ValueError(
            f"{label}: direction must be 'asc' or 'desc', got '{direction}'. "
            'Use "field:direction" or "field-direction", e.g. "id:asc".'
        )
    if not _FIELD.fullmatch(field):
        raise ValueError(
            f"{label}: field name '{field}' contains invalid characters "
            "(only alphanumeric, underscore, and dot allowed)"
        )
    return SortCriterion(field=field, direction=direction)


def parse_sort_by(values: Sequence[str], *, field_name: str) -> list[SortCriterion]:
    return [parse_sort_criterion(value, label=f"{field_name}[{i}]") for i, value in enumerate(values)]
