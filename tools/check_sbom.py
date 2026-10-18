"""Check that the generated SBOM describes this project and its whole runtime dependency graph.

The SBOM comes from `uv export --format cyclonedx1.5`. It must name the project (name and version
from pyproject.toml) as its root component, give every component a name and a version, reach
every component from the root through the dependency graph, list every direct dependency, and
contain no package that only an extra or a dependency group brings in. A component called "unknown"
or without a version is what an editable install in a requirements export used to produce.

Usage: python tools/check_sbom.py sbom.json [--pyproject pyproject.toml]
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def problems(
    sbom: Mapping[str, Any],
    *,
    name: str,
    version: str,
    runtime: Collection[str] = (),
    development: Collection[str] = (),
) -> list[str]:
    """What is wrong with the SBOM. `runtime` are the names of the direct dependencies, `development`
    those of packages that only an extra or a dependency group installs."""
    found: list[str] = []
    root = sbom.get("metadata", {}).get("component") or {}
    if root.get("name") != name or root.get("version") != version:
        found.append(f"root component is {root.get('name')!r} {root.get('version')!r}, expected {name!r} {version!r}")

    components = sbom.get("components") or []
    if not components:
        found.append("no components")
    for component in components:
        label = f"{component.get('name')!r} {component.get('version')!r}"
        if not component.get("name") or component.get("name") == "unknown":
            found.append(f"component without a name: {label}")
        elif not component.get("version"):
            found.append(f"component without a version: {label}")

    edges = {entry["ref"]: entry.get("dependsOn", []) for entry in sbom.get("dependencies") or []}
    reached: set[str] = set()
    pending = [root.get("bom-ref")]
    while pending:
        ref = pending.pop()
        if ref is None or ref in reached:
            continue
        reached.add(ref)
        pending.extend(edges.get(ref, []))
    missing = sorted(str(c.get("name")) for c in components if c.get("bom-ref") not in reached)
    if missing:
        found.append(f"not reachable from the root component: {', '.join(missing)}")

    refs = [c.get("bom-ref") for c in components]
    duplicated = sorted({str(ref) for ref in refs if refs.count(ref) > 1})
    if duplicated:
        found.append(f"bom-ref used twice: {', '.join(duplicated)}")

    present = {canonicalize_name(str(c.get("name"))) for c in components}
    absent = sorted(canonicalize_name(n) for n in runtime if canonicalize_name(n) not in present)
    if absent:
        found.append(f"direct dependency missing: {', '.join(absent)}")
    leaked = sorted(canonicalize_name(n) for n in development if canonicalize_name(n) in present)
    if leaked:
        found.append(f"development package listed: {', '.join(leaked)}")
    return found


def _names(requirements: Sequence[str]) -> set[str]:
    return {canonicalize_name(Requirement(entry).name) for entry in requirements}


def _runtime_and_development(project: Mapping[str, Any], groups: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    runtime = _names(project.get("dependencies", []))
    extras = [entry for entries in project.get("optional-dependencies", {}).values() for entry in entries]
    grouped = [entry for entries in groups.values() for entry in entries if isinstance(entry, str)]
    return runtime, _names(extras + grouped) - runtime


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args(argv)
    pyproject = tomllib.loads(args.pyproject.read_text(encoding="utf-8"))
    project = pyproject["project"]
    runtime, development = _runtime_and_development(project, pyproject.get("dependency-groups", {}))
    sbom = json.loads(args.sbom.read_text(encoding="utf-8"))
    found = problems(sbom, name=project["name"], version=project["version"], runtime=runtime, development=development)
    for line in found:
        print(f"SBOM: {line}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
