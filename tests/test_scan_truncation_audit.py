"""A scan that stopped early says so; nothing built on its rows may drop that.

`scan_*_and_paginate` and `fetch_bounded_and_paginate` return a truncation flag beside the rows. A caller
that discards it (`rows, _ = await scan...`) reports whatever it computed from the rows as if it covered
the whole collection, such as the total size of attachments.
"""

from __future__ import annotations

import ast

import pytest
from _source_scan import SERVICES

TRUNCATION_INDEX = {"scan_records_and_paginate": 1, "scan_and_paginate": 1, "fetch_bounded_and_paginate": 3}


def _discarded(source: str) -> list[int]:
    """Lines where a scan's truncation flag is bound to `_`."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Await):
            continue
        call = node.value.value
        name = getattr(call.func, "id", None) if isinstance(call, ast.Call) else None
        target = node.targets[0]
        index = TRUNCATION_INDEX.get(name or "")
        if index is None or not isinstance(target, ast.Tuple) or index >= len(target.elts):
            continue
        flag = target.elts[index]
        if isinstance(flag, ast.Name) and flag.id == "_":
            lines.append(node.lineno)
    return lines


def test_no_service_discards_the_truncation_flag_of_a_scan() -> None:
    offenders = [
        f"{path.name}:{line}" for path in sorted(SERVICES.glob("*.py")) for line in _discarded(path.read_text())
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "call",
    [
        "rows, _ = await scan_records_and_paginate(fetch, limit=1)",
        "rows, _ = await scan_and_paginate(fetch_page=f, limit=1)",
        "rows, total, nxt, _ = await fetch_bounded_and_paginate(fetch_page=f)",
    ],
)
def test_a_discarded_flag_is_found(call: str) -> None:
    assert _discarded(f"async def f():\n    {call}\n") == [2]


def test_a_kept_flag_is_not_flagged() -> None:
    assert _discarded("async def f():\n    rows, truncated = await scan_records_and_paginate(fetch)\n") == []
