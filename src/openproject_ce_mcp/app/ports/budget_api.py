"""Budgets Domain API port -- narrow, no universal gateway."""

from __future__ import annotations

from typing import Protocol

from ...models import BudgetSummary


class BudgetApi(Protocol):
    async def list_for_project(self, project_id: int, *, project_name: str | None) -> list[BudgetSummary]: ...
