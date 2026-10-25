"""Versions-only policy. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...config import Settings
from .scope import defining_project_link_allowed


def version_payload_allowed(
    payload: dict[str, Any], *, settings: Settings, project_id_to_identifier: Mapping[int, str]
) -> bool:
    return defining_project_link_allowed(
        payload.get("_links", {}).get("definingProject"),
        settings=settings,
        project_id_to_identifier=project_id_to_identifier,
    )
