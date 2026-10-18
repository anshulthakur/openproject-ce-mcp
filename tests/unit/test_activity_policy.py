from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.policies import activity_policy


@pytest.mark.parametrize(
    ("read_projects", "allowed"),
    [
        (("*",), True),
        ((" * ",), True),
        (("demo", "*"), True),
        ((), False),
        (("demo",), False),
        (("team-*",), False),
        (("**",), False),
    ],
)
def test_details_are_allowed_only_when_the_read_scope_allows_all(read_projects: tuple[str, ...], allowed: bool) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=read_projects)

    assert activity_policy.details_allowed(settings) is allowed


@pytest.mark.parametrize(
    "hiding",
    [
        {"hidden_fields": {"work_package": ("estimated_time",)}},
        {"hide_work_package_fields": ("version",)},
        {"hide_custom_fields": ("customField12",)},
    ],
)
def test_details_are_left_out_when_a_work_package_or_custom_field_is_hidden(hiding: dict) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), **hiding)

    assert activity_policy.details_allowed(settings) is False


@pytest.mark.parametrize("hiding", [{"hidden_fields": {"activity": ("comment",), "project": ("description",)}}, {}])
def test_details_stay_when_only_other_entities_are_hidden(hiding: dict) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), **hiding)

    assert activity_policy.details_allowed(settings) is True
