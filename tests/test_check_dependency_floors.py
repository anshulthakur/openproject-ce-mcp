from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
_PATH = ROOT / "tools" / "check_dependency_floors.py"
_spec = importlib.util.spec_from_file_location("check_dependency_floors", _PATH)
assert _spec is not None and _spec.loader is not None
check_dependency_floors = importlib.util.module_from_spec(_spec)
sys.modules["check_dependency_floors"] = check_dependency_floors
_spec.loader.exec_module(check_dependency_floors)

PYPROJECT_TOML = """\
[project]
name = "app"
dependencies = ["httpx[socks]>=0.27,<0.29", "tomli>=2; python_version < '3'"]

[project.optional-dependencies]
dev = ["pytest>=8.3,<10"]
measure = ["tiktoken>=0.8,<1"]

[dependency-groups]
dev = ["pytest>=8.3,<10", "ruff>=0.15.9"]
"""
PYPROJECT = check_dependency_floors.tomllib.loads(PYPROJECT_TOML)
AT_FLOOR = {"httpx": "0.27", "pytest": "8.3.0", "ruff": "0.15.9"}


def _installed(versions: dict[str, str]) -> Callable[[str], str]:
    def version(name: str) -> str:
        if name not in versions:
            raise metadata.PackageNotFoundError(name)
        return versions[name]

    return version


def _requirements(*raw: str) -> list[Requirement]:
    return [Requirement(entry) for entry in raw]


def test_reads_dependencies_and_only_the_named_extras_and_groups() -> None:
    requirements = check_dependency_floors.declared_requirements(PYPROJECT, ["dev"], ["dev"])

    assert [r.name for r in requirements] == ["httpx", "tomli", "pytest", "ruff"]


def test_same_name_with_a_different_specifier_is_kept() -> None:
    pyproject = {"project": {"dependencies": ["pytest>=8.3,<10"]}, "dependency-groups": {"dev": ["pytest>=8.4"]}}

    requirements = check_dependency_floors.declared_requirements(pyproject, [], ["dev"])

    assert [str(r.specifier) for r in requirements] == ["<10,>=8.3", ">=8.4"]


def test_real_pyproject_selection_covers_the_dev_group() -> None:
    pyproject = check_dependency_floors.tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    names = {r.name for r in check_dependency_floors.declared_requirements(pyproject, ["dev"], ["dev"])}

    assert {"mcp", "httpx", "pydantic", "pytest", "ruff", "mypy"} <= names
    assert "tiktoken" not in names


@pytest.mark.parametrize(
    ("extras", "groups", "message"),
    [
        (["docs"], [], "no extra 'docs'"),
        ([], ["lint"], "no dependency group 'lint'"),
    ],
)
def test_unknown_selection_is_rejected(extras: list[str], groups: list[str], message: str) -> None:
    with pytest.raises(check_dependency_floors.FloorError, match=message):
        check_dependency_floors.declared_requirements(PYPROJECT, extras, groups)


def test_marker_variants_of_one_requirement_are_all_checked() -> None:
    pyproject = {
        "project": {"dependencies": ["tomli>=2; python_version < '3'"]},
        "dependency-groups": {"dev": ["tomli>=2; python_version >= '3'"]},
    }
    requirements = check_dependency_floors.declared_requirements(pyproject, [], ["dev"])

    problems = check_dependency_floors.off_floor(requirements, _installed({"tomli": "2.0.1"}))

    assert problems == ["tomli 2.0.1 is not its floor 2"]


@pytest.mark.parametrize(
    ("project", "extras"),
    [
        ({"dynamic": ["dependencies"]}, []),
        ({"dependencies": ["mcp>=2"], "dynamic": ["optional-dependencies"]}, ["dev"]),
    ],
)
def test_dynamic_dependencies_are_rejected(project: dict[str, list[str]], extras: list[str]) -> None:
    with pytest.raises(check_dependency_floors.FloorError, match="dynamic"):
        check_dependency_floors.declared_requirements({"project": project}, extras, [])


def test_empty_selection_is_rejected() -> None:
    pyproject = {"project": {"dependencies": []}, "dependency-groups": {"dev": []}}

    with pytest.raises(check_dependency_floors.FloorError, match="names no requirements"):
        check_dependency_floors.declared_requirements(pyproject, [], ["dev"])


def test_include_group_entry_is_rejected() -> None:
    pyproject = {"project": {}, "dependency-groups": {"dev": [{"include-group": "test"}]}}

    with pytest.raises(check_dependency_floors.FloorError, match="include-group"):
        check_dependency_floors.declared_requirements(pyproject, [], ["dev"])


def test_every_requirement_on_its_floor_passes(capsys: pytest.CaptureFixture[str]) -> None:
    requirements = _requirements("httpx[socks]>=0.27,<0.29", "ruff>=0.15.9")

    assert check_dependency_floors.off_floor(requirements, _installed(AT_FLOOR)) == []
    assert "httpx 0.27 (floor 0.27)" in capsys.readouterr().out


def test_version_above_the_floor_is_reported() -> None:
    requirements = _requirements("httpx[socks]>=0.27,<0.29", "ruff>=0.15.9")

    problems = check_dependency_floors.off_floor(requirements, _installed({**AT_FLOOR, "ruff": "0.15.10"}))

    assert problems == ["ruff 0.15.10 is not its floor 0.15.9"]


@pytest.mark.parametrize("raw", ["ruff", "ruff<1", "ruff==0.15.9", "ruff~=0.15.9", "ruff>=0.15,>=0.15.9"])
def test_requirement_without_exactly_one_floor_is_reported(raw: str) -> None:
    problems = check_dependency_floors.off_floor(_requirements(raw), _installed(AT_FLOOR))

    assert problems == [f"{Requirement(raw)} needs exactly one >= lower bound"]


def test_missing_package_is_reported() -> None:
    problems = check_dependency_floors.off_floor(_requirements("mypy>=1.14,<3"), _installed(AT_FLOOR))

    assert problems == ["mypy is not installed (floor 1.14)"]


def test_requirement_whose_marker_does_not_apply_is_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    looked_up: list[str] = []

    def version(name: str) -> str:
        looked_up.append(name)
        raise AssertionError("not installed here")

    assert check_dependency_floors.off_floor(_requirements("tomli>=2; python_version < '3'"), version) == []
    assert looked_up == []
    assert "tomli: not required here" in capsys.readouterr().out


def test_requirement_whose_marker_applies_is_checked() -> None:
    looked_up: list[str] = []

    def version(name: str) -> str:
        looked_up.append(name)
        return "2.0.1"

    problems = check_dependency_floors.off_floor(_requirements("tomli>=2; python_version >= '3'"), version)

    assert looked_up == ["tomli"]
    assert problems == ["tomli 2.0.1 is not its floor 2"]


def test_main_exit_code_follows_the_installed_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_TOML, encoding="utf-8")
    argv = ["--pyproject", str(pyproject), "--extra", "dev", "--group", "dev"]

    monkeypatch.setattr(check_dependency_floors.metadata, "version", _installed(AT_FLOOR))
    assert check_dependency_floors.main(argv) == 0

    monkeypatch.setattr(check_dependency_floors.metadata, "version", _installed({**AT_FLOOR, "pytest": "9.0.0"}))
    assert check_dependency_floors.main(argv) == 1
    out = capsys.readouterr().out
    assert out.index("pytest 9.0.0 (floor 8.3)") < out.index("FAIL: pytest 9.0.0 is not its floor 8.3")


def test_main_rejects_an_unknown_group(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_TOML, encoding="utf-8")

    assert check_dependency_floors.main(["--pyproject", str(pyproject), "--group", "lint"]) == 1
    assert "no dependency group 'lint'" in capsys.readouterr().err
