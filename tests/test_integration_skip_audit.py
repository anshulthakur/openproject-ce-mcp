"""An integration test does not turn an unexpected failure into a skip.

A skip inside an `except` reads as "not available on this instance". That is right for the named
absences below (a route a version does not have, a Rails capability the instance lacks), and wrong
for a catch that also swallows a parse error, a server error or a refusal of this server's own
policies: the breakage then passes as a skip and nobody sees it. A handler that skips on any
other exception has to re-raise when the absence is not the expected one, or be classified here.
"""

from __future__ import annotations

import ast

from _source_scan import INTEGRATION, matching_nodes

NARROW = {"NotFoundError", "RailsCapabilityUnavailable"}

# file:function -> why this catch may skip on a broad failure without re-raising
CLASSIFIED: dict[str, str] = {}


def _names(handler: ast.ExceptHandler) -> set[str]:
    if handler.type is None:
        return {"<bare>"}
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return {ast.unparse(node).rsplit(".", maxsplit=1)[-1] for node in nodes}


def _contains(handler: ast.ExceptHandler, kind: type[ast.AST]) -> bool:
    return any(isinstance(node, kind) for node in ast.walk(handler))


def _skips(handler: ast.ExceptHandler) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "skip"
        for node in ast.walk(handler)
    )


def _skipping_handler(node: ast.AST) -> bool:
    return isinstance(node, ast.ExceptHandler) and _skips(node)


def skipping_handlers(source: str | None = None) -> dict[str, set[str]]:
    """`file:function` -> exception names caught by a handler that skips without re-raising."""
    found: dict[str, set[str]] = {}
    for name, handlers in matching_nodes(_skipping_handler, directories=(INTEGRATION,), source=source).items():
        for handler in handlers:
            assert isinstance(handler, ast.ExceptHandler)
            if not _contains(handler, ast.Raise):
                found.setdefault(name, set()).update(_names(handler))
    return found


def test_a_handler_that_skips_catches_only_named_absences_or_is_classified() -> None:
    found = skipping_handlers()

    assert len(found) >= 40, "the scan found too few skipping handlers to be reading the integration tests"
    broad = {name for name, caught in found.items() if caught - NARROW}
    assert broad - set(CLASSIFIED) == set(), (
        "catch a named absence, re-raise unless the absence is the expected one, or classify the handler in CLASSIFIED"
    )


def test_no_classification_outlives_the_handler_it_describes() -> None:
    found = skipping_handlers()

    assert sorted(name for name in CLASSIFIED if not found.get(name, set()) - NARROW) == []


def test_the_scan_flags_a_broad_catch_and_a_bare_catch_but_not_a_gated_one() -> None:
    source = (
        "def a():\n    try:\n        f()\n    except (OpenProjectError, json.JSONDecodeError):\n        pytest.skip('x')\n"
        "def b():\n    try:\n        f()\n    except:\n        pytest.skip('x')\n"
        "def c():\n    try:\n        f()\n    except client.NotFoundError:\n        pytest.skip('x')\n"
        "def d():\n    try:\n        f()\n    except ValueError:\n        raise\n"
        "def e():\n    try:\n        f()\n    except PermissionDeniedError:\n"
        "        if version != (16, 6):\n            raise\n        pytest.skip('x')\n"
    )

    assert skipping_handlers(source) == {
        "planted.py:a": {"OpenProjectError", "JSONDecodeError"},
        "planted.py:b": {"<bare>"},
        "planted.py:c": {"NotFoundError"},
    }
