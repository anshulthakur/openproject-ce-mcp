"""Revision tool handlers: list_work_package_revisions."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context

from .models import RevisionListResult, RevisionSummary
from .tool_params import WorkPackageRef, select_field
from .tools_runtime import _client_from_context, _run_tool, register_tool
from .tools_validation import _validate_select, _validate_work_package_ref


@register_tool
async def list_work_package_revisions(
    ctx: Context,
    work_package_id: WorkPackageRef,
    select: Annotated[list[str] | None, select_field(RevisionSummary)] = None,
) -> RevisionListResult:
    """List the repository revisions linked to a work package, limited to projects the read scope covers.

    An empty list also means the repository module is off or the caller may not view changesets; the author name
    and message come from the repository and are delimited as untrusted content."""
    client = _client_from_context(ctx)
    safe_wp = _validate_work_package_ref(work_package_id)
    _validate_select(select, row_type=RevisionSummary)
    return await _run_tool(client.revision.list_for_work_package(safe_wp))
