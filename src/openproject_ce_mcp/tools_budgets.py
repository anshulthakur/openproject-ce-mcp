"""Budget tool handlers: list_project_budgets."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context

from .models import BudgetListResult, BudgetSummary
from .tool_params import ProjectRef, select_field
from .tools_runtime import _client_from_context, _run_tool, register_tool
from .tools_validation import _validate_project_ref, _validate_select


@register_tool
async def list_project_budgets(
    ctx: Context,
    project: ProjectRef,
    select: Annotated[list[str] | None, select_field(BudgetSummary)] = None,
) -> BudgetListResult:
    """List the cost budgets of a project (Budgets module; an instance without it answers permission denied)."""
    client = _client_from_context(ctx)
    safe_project = _validate_project_ref(project)
    _validate_select(select, row_type=BudgetSummary)
    return await _run_tool(client.budget.list(safe_project))
