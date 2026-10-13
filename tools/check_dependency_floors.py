"""Check that every direct dependency is installed at its declared lower bound.

Run it with the interpreter of an environment installed with uv's
`--resolution lowest-direct`. The requirements come straight from
pyproject.toml: [project] dependencies plus the extras and dependency groups
named on the command line, the same selection the environment was installed
with. The installed package's metadata would miss the dependency groups.

Every applicable requirement needs exactly one `>=` specifier: a requirement
without one has no version this check could hold it to, so its oldest allowed
release would go untested.

Usage: python tools/check_dependency_floors.py [--extra NAME]... [--group NAME]...
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

# Not a declared dependency: pytest brings it in.
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


class FloorError(Exception):
    """pyproject.toml lacks something the check needs."""


def declared_requirements(
    pyproject: Mapping[str, Any], extras: Iterable[str], groups: Iterable[str]
) -> list[Requirement]:
    project = pyproject["project"]
    extras = list(extras)
    dynamic = project.get("dynamic", [])
    if "dependencies" in dynamic or (extras and "optional-dependencies" in dynamic):
        raise FloorError("pyproject.toml declares its dependencies as dynamic, so it does not list the floors")
    raw: list[str] = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for extra in extras:
        if extra not in optional:
            raise FloorError(f"pyproject.toml declares no extra {extra!r}")
        raw.extend(optional[extra])
    dependency_groups = pyproject.get("dependency-groups", {})
    for group in groups:
        if group not in dependency_groups:
            raise FloorError(f"pyproject.toml declares no dependency group {group!r}")
        for entry in dependency_groups[group]:
            if not isinstance(entry, str):
                raise FloorError(f"dependency group {group!r}: include-group entries are not supported")
            raw.append(entry)
    unique: dict[tuple[str, str, str], Requirement] = {}
    for entry in raw:
        requirement = Requirement(entry)
        key = (canonicalize_name(requirement.name), str(requirement.specifier), str(requirement.marker))
        unique.setdefault(key, requirement)
    if not unique:
        raise FloorError("the selection names no requirements")
    return list(unique.values())


def declared_floor(requirement: Requirement) -> Version:
    floors = [spec.version for spec in requirement.specifier if spec.operator == ">="]
    if len(floors) != 1:
        raise FloorError(f"{requirement} needs exactly one >= lower bound")
    return Version(floors[0])


def off_floor(requirements: Iterable[Requirement], installed_version: Callable[[str], str]) -> list[str]:
    problems: list[str] = []
    for requirement in requirements:
        if requirement.marker is not None and not requirement.marker.evaluate():
            print(f"{requirement.name}: not required here ({requirement.marker})")
            continue
        try:
            floor = declared_floor(requirement)
        except FloorError as exc:
            problems.append(str(exc))
            continue
        try:
            installed = installed_version(requirement.name)
        except metadata.PackageNotFoundError:
            problems.append(f"{requirement.name} is not installed (floor {floor})")
            continue
        print(f"{requirement.name} {installed} (floor {floor})")
        if Version(installed) != floor:
            problems.append(f"{requirement.name} {installed} is not its floor {floor}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--extra", action="append", default=[])
    parser.add_argument("--group", action="append", default=[])
    args = parser.parse_args(argv)
    pyproject = tomllib.loads(args.pyproject.read_text(encoding="utf-8"))
    try:
        requirements = declared_requirements(pyproject, args.extra, args.group)
    except FloorError as exc:
        print(exc, file=sys.stderr)
        return 1
    problems = off_floor(requirements, metadata.version)
    # Same stream as the per-package lines, so a CI log keeps them in order.
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
