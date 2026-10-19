"""A dependency a class receives is a dependency it uses.

A constructor parameter that is stored in a private attribute and never read looks like a check
or a collaborator the class relies on, and misleads the next reader about what enforces a rule.
The attribute and its parameter go, or the class reads them. Supported syntax: a plain or
annotated assignment `self._x = parameter` in `__init__`, read as `self._x` anywhere in the class.
"""

from __future__ import annotations

import ast

from _source_scan import SRC


def _constructor_stores(cls: ast.ClassDef) -> dict[str, str]:
    """Private attribute -> constructor parameter, for each `self._x = parameter` in `__init__`."""
    init = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
    if init is None:
        return {}
    parameters = {a.arg for a in (*init.args.args, *init.args.kwonlyargs)}
    stored: dict[str, str] = {}
    for node in ast.walk(init):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not (isinstance(value, ast.Name) and value.id in parameters):
            continue
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr.startswith("_")
            ):
                stored[target.attr] = value.id
    return stored


def _self_reads(cls: ast.ClassDef) -> set[str]:
    return {
        node.attr
        for node in ast.walk(cls)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }


def _classes(source: str) -> list[ast.ClassDef]:
    return [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ClassDef)]


def stored_and_never_read(source: str) -> list[str]:
    """`Class._attr <- parameter` for each constructor store that nothing in the class reads."""
    return [
        f"{cls.name}.{attr} <- {param}"
        for cls in _classes(source)
        for attr, param in _constructor_stores(cls).items()
        if attr not in _self_reads(cls)
    ]


def test_no_class_stores_a_constructor_parameter_it_never_reads() -> None:
    unused = {
        f"{path.relative_to(SRC)}: {entry}"
        for path in sorted(SRC.rglob("*.py"))
        for entry in stored_and_never_read(path.read_text())
    }

    assert unused == set(), "remove the parameter with its attribute, or read it"


def test_the_scan_reads_enough_constructor_stores_to_mean_something() -> None:
    stores = sum(len(_constructor_stores(cls)) for path in SRC.rglob("*.py") for cls in _classes(path.read_text()))

    assert stores >= 250, "the scan found too few constructor stores to be reading the source"


def test_the_scan_flags_an_unread_dependency_and_leaves_a_read_one() -> None:
    source = (
        "class A:\n"
        "    def __init__(self, used, unused, annotated, *, kw):\n"
        "        self._used = used\n"
        "        self._unused = unused\n"
        "        self._annotated: int = annotated\n"
        "        self._kw = kw\n"
        "        self.public = unused\n"
        "    def run(self):\n"
        "        return self._used\n"
    )

    assert stored_and_never_read(source) == ["A._unused <- unused", "A._annotated <- annotated", "A._kw <- kw"]
