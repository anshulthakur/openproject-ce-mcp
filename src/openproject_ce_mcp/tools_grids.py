"""Grids domain MCP tool handlers: list_grids, get_grid, create_grid,
update_grid, delete_grid.

Their `@register_tool` decorators come from `tools_runtime`, never from
`tools.py` -- see that module's own docstring for why. `tools.py` imports
this module for the decorator's registration side effect and re-exports
these five names because `test_project_and_domain_tools.py` imports them
directly from `openproject_ce_mcp.tools`.

Grids is a standalone dashboard-grid CRUD domain, distinct from Boards
(`tools_boards.py`) -- both are saved-layout resources but map to different
OpenProject API resources (`/api/v3/grids` vs `/api/v3/queries`) and are not
otherwise related.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context
from pydantic import Field

from .models import GridListResult, GridSummary, GridWriteResult
from .tool_params import Confirm, Limit, Offset, select_field
from .tools_runtime import _client_from_context, _run_tool, register_tool
from .tools_validation import (
    _require_at_least_one,
    _validate_limit,
    _validate_offset,
    _validate_optional_query,
    _validate_positive_int,
    _validate_required_query,
    _validate_select,
)


@register_tool
async def list_grids(
    ctx: Context,
    scope: str | None = None,
    offset: Offset = 1,
    limit: Limit = None,
    select: Annotated[list[str] | None, select_field(GridSummary)] = None,
) -> GridListResult:
    """List dashboard grids, optionally filtered by scope (page path).

    total is only the count of allowed grids returned on THIS page, not a full count of all matches; the search
    stops as soon as it has enough, so an exact total would need an extra full walk. Page until next_offset is null.
    """
    client = _client_from_context(ctx)
    safe_scope = _validate_optional_query(scope, field_name="scope", max_length=500)
    safe_offset = _validate_offset(offset)
    safe_limit = _validate_limit(limit)
    _validate_select(select, row_type=GridSummary)
    return await _run_tool(client.grid.list(scope=safe_scope, offset=safe_offset, limit=safe_limit))


@register_tool
async def get_grid(ctx: Context, grid_id: int) -> GridSummary:
    """Get a single dashboard grid by id."""
    client = _client_from_context(ctx)
    safe_id = _validate_positive_int(grid_id, field_name="grid_id")
    return await _run_tool(client.grid.get(safe_id))


@register_tool
async def create_grid(
    ctx: Context,
    name: Annotated[str, Field(description="Display name, at most 255 characters.")],
    scope: Annotated[
        str,
        Field(
            description=(
                'Page path: "/my/page", "/projects/<identifier>" or "/projects/<identifier>/boards", after the '
                "instance's root path on a subpath install. Any other scope is rejected before a request."
            )
        ),
    ],
    row_count: Annotated[int | None, Field(description="Positive integer; omitted lets OpenProject choose.")] = None,
    column_count: Annotated[int | None, Field(description="Positive integer; omitted lets OpenProject choose.")] = None,
    confirm: Confirm = False,
) -> GridWriteResult:
    """Create a dashboard grid on a page.

    A grid is the widget layout of My Page, a project overview or a board. The grid starts with OpenProject's
    default widgets for that page; other widgets are added in OpenProject. A board's saved work package
    queries are created with create_board.
    """
    client = _client_from_context(ctx)
    safe_name = _validate_required_query(name, field_name="name", max_length=255)
    safe_scope = _validate_required_query(scope, field_name="scope", max_length=500)
    if not safe_scope.startswith("/"):
        raise ValueError("scope must start with '/'.")
    safe_row_count = _validate_positive_int(row_count, field_name="row_count") if row_count is not None else None
    safe_column_count = (
        _validate_positive_int(column_count, field_name="column_count") if column_count is not None else None
    )
    return await _run_tool(
        client.grid.create(
            name=safe_name,
            scope=safe_scope,
            row_count=safe_row_count,
            column_count=safe_column_count,
            confirm=confirm,
        )
    )


@register_tool
async def update_grid(
    ctx: Context,
    grid_id: Annotated[int, Field(description="Grid id, from list_grids.")],
    name: Annotated[str | None, Field(description="New display name, at most 255 characters.")] = None,
    row_count: Annotated[int | None, Field(description="New number of rows, a positive integer.")] = None,
    column_count: Annotated[int | None, Field(description="New number of columns, a positive integer.")] = None,
    confirm: Confirm = False,
) -> GridWriteResult:
    """Rename or resize a dashboard grid; omitted fields stay unchanged.

    The widgets stay as they are; a size that would leave a widget outside the grid is rejected.
    """
    client = _client_from_context(ctx)
    safe_id = _validate_positive_int(grid_id, field_name="grid_id")
    safe_name = _validate_optional_query(name, field_name="name", max_length=255)
    safe_row_count = _validate_positive_int(row_count, field_name="row_count") if row_count is not None else None
    safe_column_count = (
        _validate_positive_int(column_count, field_name="column_count") if column_count is not None else None
    )
    _require_at_least_one(
        safe_name, safe_row_count, safe_column_count, message="At least one field to update is required."
    )
    return await _run_tool(
        client.grid.update(
            grid_id=safe_id,
            name=safe_name,
            row_count=safe_row_count,
            column_count=safe_column_count,
            confirm=confirm,
        )
    )


@register_tool
async def delete_grid(
    ctx: Context,
    grid_id: int,
    confirm: Confirm = False,
) -> GridWriteResult:
    """Delete a board grid; My Page and project overview grids cannot be deleted.

    17.0+: its column queries are deleted too, as far as you may delete them. This cannot be undone.
    """
    client = _client_from_context(ctx)
    safe_id = _validate_positive_int(grid_id, field_name="grid_id")
    return await _run_tool(client.grid.delete(grid_id=safe_id, confirm=confirm))
