from __future__ import annotations

from pathlib import Path

PUBLISH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish.yml"


def _release_step() -> str:
    text = PUBLISH.read_text(encoding="utf-8")
    return text[text.index("- name: Create GitHub Release") :]


def test_the_new_draft_is_taken_from_the_create_response_not_listed_again() -> None:
    step = _release_step()
    created = step.index('-X POST "repos/$GITHUB_REPOSITORY/releases"')

    assert "list_releases" not in step[created:], (
        "GitHub may not list a release created a moment ago; use the response of the create call"
    )


def test_the_draft_is_only_created_for_a_tag_that_exists() -> None:
    step = _release_step()

    assert step.index('git/ref/tags/$tag" --silent') < step.index('-X POST "repos/$GITHUB_REPOSITORY/releases"')
