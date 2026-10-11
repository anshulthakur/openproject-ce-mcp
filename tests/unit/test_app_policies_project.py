from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError
from openproject_ce_mcp.app.policies import project_policy


def test_ensure_project_read_allowed_raises_when_no_candidate_matches() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("other",))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        project_policy.ensure_project_read_allowed({"id": 1, "identifier": "demo", "name": "Demo"}, settings=settings)


def test_ensure_project_read_allowed_noop_under_wildcard_scope() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",))
    project_policy.ensure_project_read_allowed(
        {"id": 1, "identifier": "demo", "name": "Demo"}, settings=settings
    )  # must not raise


def test_ensure_project_write_allowed_checks_read_before_write() -> None:
    # read_projects excludes it -> must fail on the read check, not the write one
    settings = dataclasses.replace(make_settings(), read_projects=("other",), write_projects=("*",))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        project_policy.ensure_project_write_allowed({"id": 1, "identifier": "demo", "name": "Demo"}, settings=settings)


def test_ensure_project_write_allowed_raises_for_write_restricted_scope() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), write_projects=("other",))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_WRITE_PROJECTS"):
        project_policy.ensure_project_write_allowed({"id": 1, "identifier": "demo", "name": "Demo"}, settings=settings)


def test_ensure_project_write_allowed_noop_under_wildcard_scope() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), write_projects=("*",))
    project_policy.ensure_project_write_allowed(
        {"id": 1, "identifier": "demo", "name": "Demo"}, settings=settings
    )  # must not raise


def test_ensure_project_create_target_allowed_rejects_when_read_scope_excludes_it() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("other",), write_projects=("*",))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        project_policy.ensure_project_create_target_allowed(identifier="demo", name="Demo", settings=settings)


def test_ensure_project_create_target_allowed_rejects_when_write_scope_excludes_it() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), write_projects=("other",))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_WRITE_PROJECTS"):
        project_policy.ensure_project_create_target_allowed(identifier="demo", name="Demo", settings=settings)


def test_ensure_project_create_target_allowed_noop_under_wildcard_scope() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), write_projects=("*",))
    project_policy.ensure_project_create_target_allowed(
        identifier="demo", name="Demo", settings=settings
    )  # must not raise


def test_ensure_project_create_target_allowed_matches_the_name_with_hyphens_like_every_other_check() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("my-project",), write_projects=("my-project",))
    project_policy.ensure_project_create_target_allowed(
        identifier="other", name="My Project", settings=settings
    )  # must not raise


# A project created as "fidold" and renamed: OpenProject 17.3+ still resolves the former
# identifier, but the payload it returns carries only the current one.
_RENAMED = {"id": 42, "identifier": "fidnew", "name": "Fid New"}


@pytest.mark.parametrize("pattern", ["fidold", "FIDOLD", "fidol*"])
def test_ensure_project_read_allowed_denies_a_renamed_project_by_its_former_identifier(pattern: str) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=(pattern,))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        project_policy.ensure_project_read_allowed(_RENAMED, settings=settings)


@pytest.mark.parametrize("pattern", ["fidold", "FIDOLD", "fidol*"])
def test_ensure_project_write_allowed_denies_a_renamed_project_by_its_former_identifier(pattern: str) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), write_projects=(pattern,))
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_WRITE_PROJECTS"):
        project_policy.ensure_project_write_allowed(_RENAMED, settings=settings)


@pytest.mark.parametrize("pattern", ["fidnew", "FIDNEW", "fid*", "42", "Fid New", "fid new", "fid-new"])
def test_ensure_project_read_and_write_allowed_match_id_current_identifier_and_name(pattern: str) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=(pattern,), write_projects=(pattern,))
    project_policy.ensure_project_read_allowed(_RENAMED, settings=settings)
    project_policy.ensure_project_write_allowed(_RENAMED, settings=settings)  # must not raise
