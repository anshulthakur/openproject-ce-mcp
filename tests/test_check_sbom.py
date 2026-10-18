from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_sbom", ROOT / "tools" / "check_sbom.py")
assert _spec is not None and _spec.loader is not None
check_sbom = importlib.util.module_from_spec(_spec)
sys.modules["check_sbom"] = check_sbom
_spec.loader.exec_module(check_sbom)


def _sbom(**overrides: Any) -> dict[str, Any]:
    sbom: dict[str, Any] = {
        "metadata": {"component": {"bom-ref": "app@1.0", "name": "app", "version": "1.0"}},
        "components": [
            {"bom-ref": "a@1", "name": "a", "version": "1"},
            {"bom-ref": "b@2", "name": "b", "version": "2"},
        ],
        "dependencies": [
            {"ref": "app@1.0", "dependsOn": ["a@1"]},
            {"ref": "a@1", "dependsOn": ["b@2"]},
            {"ref": "b@2"},
        ],
    }
    sbom.update(overrides)
    return sbom


def test_an_sbom_that_names_the_project_and_reaches_every_component_passes() -> None:
    assert check_sbom.problems(_sbom(), name="app", version="1.0") == []


def test_another_root_component_is_reported() -> None:
    sbom = _sbom(metadata={"component": {"bom-ref": "x", "name": "unknown", "version": None}})

    assert any("root component" in p for p in check_sbom.problems(sbom, name="app", version="1.0"))


def test_the_root_version_must_match_the_project() -> None:
    assert check_sbom.problems(_sbom(), name="app", version="2.0")


@pytest.mark.parametrize(
    "component", [{"bom-ref": "u", "name": "unknown", "version": "1"}, {"bom-ref": "v", "name": "v", "version": None}]
)
def test_a_component_without_a_name_or_a_version_is_reported(component: dict[str, Any]) -> None:
    sbom = _sbom()
    sbom["components"].append(component)
    sbom["dependencies"][1]["dependsOn"].append(component["bom-ref"])

    assert any("component without" in p for p in check_sbom.problems(sbom, name="app", version="1.0"))


def test_a_component_the_root_does_not_reach_is_reported() -> None:
    sbom = _sbom()
    sbom["components"].append({"bom-ref": "orphan@1", "name": "orphan", "version": "1"})

    (problem,) = check_sbom.problems(sbom, name="app", version="1.0")

    assert "orphan" in problem and "not reachable" in problem


def test_an_sbom_without_components_is_reported() -> None:
    assert "no components" in check_sbom.problems(_sbom(components=[], dependencies=[]), name="app", version="1.0")


def test_main_reads_the_project_from_pyproject_and_sets_the_exit_code(tmp_path: Path, capsys) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "app"\nversion = "1.0"\n')
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_sbom()))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_sbom(components=[])))

    assert check_sbom.main([str(good), "--pyproject", str(pyproject)]) == 0
    assert check_sbom.main([str(bad), "--pyproject", str(pyproject)]) == 1
    assert "SBOM:" in capsys.readouterr().err


def test_a_direct_dependency_the_sbom_lacks_is_reported() -> None:
    found = check_sbom.problems(_sbom(), name="app", version="1.0", runtime={"a", "Missing_Pkg"})

    assert found == ["direct dependency missing: missing-pkg"]


def test_a_development_package_in_the_sbom_is_reported() -> None:
    found = check_sbom.problems(_sbom(), name="app", version="1.0", development={"B"})

    assert found == ["development package listed: b"]


def test_a_bom_ref_used_twice_is_reported() -> None:
    sbom = _sbom()
    sbom["components"].append({"bom-ref": "a@1", "name": "a2", "version": "1"})

    assert any("bom-ref used twice: a@1" in p for p in check_sbom.problems(sbom, name="app", version="1.0"))


def test_main_holds_the_sbom_to_the_runtime_and_development_dependencies_of_pyproject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "app"\nversion = "1.0"\ndependencies = ["a>=1", "tomli>=2; python_version < \'3.11\'"]\n'
        '[project.optional-dependencies]\ndev = ["b>=2"]\n'
        '[dependency-groups]\ndev = ["b>=2", {include-group = "other"}]\n'
    )
    sbom = tmp_path / "sbom.json"
    sbom.write_text(json.dumps(_sbom()))

    assert check_sbom.main([str(sbom), "--pyproject", str(pyproject)]) == 1
    err = capsys.readouterr().err
    assert "direct dependency missing: tomli" in err
    assert "development package listed: b" in err
