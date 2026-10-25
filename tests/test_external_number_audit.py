"""Text from outside is turned into a number only where infinity and NaN are handled.

`float("nan")` and `float("1e999")` are valid input to `float()`: NaN passes every comparison as
false, so a range check lets it through, and a huge digit string becomes infinity. A conversion of
non-literal text to a float is therefore classified here with the reason it cannot hand such a
value on.
"""

from __future__ import annotations

import ast

import pytest
from _source_scan import ADAPTERS, APP, SERVICES, SRC, matching_nodes

DIRECTORIES = (SRC, APP, ADAPTERS, SERVICES, APP / "policies", APP / "resolvers", APP / "transport", SRC / "doctor")

# "file:function" -> why the float it builds is finite
CLASSIFIED: dict[str, str] = {
    "config.py:_parse_float": "rejects a value that is not finite right after the conversion",
    "retry_transport.py:_parse_retry_after": "ignores a header value that is not finite",
    "strict_mcpserver.py:_finite_float": "raises for a value that is not finite; it is json's parse_float hook",
    "time_entry_service.py:_duration_to_seconds": "returns None for a sum that is not finite",
    "httpx_recurring_meeting_api.py:normalize_recurring_meeting": "converts a number that json already parsed, guarded by isinstance",
}


def _converts_text_to_float(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        and bool(node.args)
        and not isinstance(node.args[0], ast.Constant)
    )


def _conversions(source: str | None = None) -> dict[str, list[ast.AST]]:
    return matching_nodes(_converts_text_to_float, directories=DIRECTORIES, source=source)


def test_every_conversion_of_text_to_a_float_is_classified() -> None:
    found = _conversions()

    assert len(found) >= 4, "the scan found too few conversions to be reading the source"
    assert sorted(set(found) - set(CLASSIFIED)) == [], (
        "classify these in CLASSIFIED with the reason the float is finite"
    )


def test_no_classification_outlives_its_conversion() -> None:
    assert sorted(set(CLASSIFIED) - set(_conversions())) == []


@pytest.mark.parametrize("call", ["float(text)", "float(self.value)", "float(values[0])"])
def test_a_new_conversion_of_text_is_found(call: str) -> None:
    assert list(_conversions(f"def parse(text, values):\n    return {call}\n")) == ["planted.py:parse"]


def test_a_conversion_of_a_literal_is_not_a_conversion_of_text() -> None:
    assert _conversions("def one():\n    return float(1)\n") == {}
