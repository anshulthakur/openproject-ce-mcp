from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError
from openproject_ce_mcp.app.policies import rendered_text_policy


@pytest.mark.parametrize("read_projects", [("*",), (" * ",), ("demo", "*")])
def test_rendering_is_allowed_when_the_read_scope_allows_all(read_projects: tuple[str, ...]) -> None:
    rendered_text_policy.ensure_render_allowed(dataclasses.replace(make_settings(), read_projects=read_projects))


@pytest.mark.parametrize("entity", rendered_text_policy.MACRO_ENTITIES)
def test_rendering_is_refused_while_a_field_of_a_macro_entity_is_hidden(entity: str) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), hidden_fields={entity: ("name",)})

    with pytest.raises(PermissionDeniedError, match=f"fields of {entity} are hidden"):
        rendered_text_policy.ensure_render_allowed(settings)


def test_rendering_is_allowed_while_only_other_entities_are_hidden() -> None:
    settings = dataclasses.replace(
        make_settings(), read_projects=("*",), hidden_fields={"activity": ("comment",), "notification": ("reason",)}
    )

    rendered_text_policy.ensure_render_allowed(settings)


@pytest.mark.parametrize("read_projects", [(), ("demo",), ("team-*",), ("**",)])
def test_rendering_is_refused_for_every_other_read_scope(read_projects: tuple[str, ...]) -> None:
    settings = dataclasses.replace(make_settings(), read_projects=read_projects)

    with pytest.raises(PermissionDeniedError, match="Set OPENPROJECT_READ_PROJECTS=\\* to allow it"):
        rendered_text_policy.ensure_render_allowed(settings)
