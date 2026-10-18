"""Text that OpenProject renders from several records is served only where its reach is known.

A change detail or a rendered markup string is assembled by the server, in the API user's language,
from records that can belong to projects the read allowlist does not cover, and it carries no
structure to check them against. An adapter that starts reading such a key fails this test until it
is classified here, and a service that builds an activity summary has to decide on the details.
"""

from __future__ import annotations

from _source_scan import ADAPTERS, SERVICES, calls_named, constant_key_reads, matching_nodes

SCANNED = (ADAPTERS, SERVICES)
RENDERED_KEYS = ("details", "html")

# file:function -> why the read cannot name a record outside the read scope
SAFE: dict[str, str] = {
    "httpx_activity_api.py:normalize_activity": "reads the change details only when the caller passes details=True, which the services derive from the read scope and the hide settings, or False",
    "_text.py:_extract_formattable_text": "raw is always a string and html is its rendering, so html is read only when raw is empty and then holds no text",
    "_text.py:extract_formattable_text_with_meta": "raw is always a string and html is its rendering, so html is read only when raw is empty and then holds no text",
    "httpx_attachment_api.py:_extract_formattable_text": "raw is always a string and html is its rendering, so html is read only when raw is empty and then holds no text",
}

# file:function -> the gap that is known and not closed by the read scope
OPEN: dict[str, str] = {
    "httpx_extended_metadata_api.py:render_text": "markdown macros render the name or display id of the record they name, with no scope check",
}


def _unclassified(reads: dict[str, int]) -> dict[str, int]:
    return {name: line for name, line in reads.items() if name not in SAFE and name not in OPEN}


def test_every_read_of_server_rendered_text_is_classified() -> None:
    reads = constant_key_reads(RENDERED_KEYS, directories=SCANNED)

    assert len(reads) >= 5, "the scan found too few reads to be reading the adapters and services"
    assert _unclassified(reads) == {}, "classify these functions in SAFE with the reason, or in OPEN with the gap"


def test_no_classification_outlives_the_read_it_describes() -> None:
    assert sorted((set(SAFE) | set(OPEN)) - set(constant_key_reads(RENDERED_KEYS, directories=SCANNED))) == []


def test_a_safe_function_is_not_also_listed_as_open() -> None:
    assert sorted(set(SAFE) & set(OPEN)) == []


def test_the_scan_sees_a_planted_read() -> None:
    planted = "def by_get(p):\n    return p.get('details')\n\n\ndef by_subscript(p):\n    return p['html']\n"

    assert list(constant_key_reads(RENDERED_KEYS, source=planted)) == ["planted.py:by_get", "planted.py:by_subscript"]


def _undecided_summary_calls(source: str | None = None) -> tuple[list[str], int]:
    """`.to_summary(...)` calls without a `details=` keyword, and how many calls there are."""
    calls = matching_nodes(calls_named("to_summary"), directories=(SERVICES,), source=source)
    undecided = [
        f"{name}:{call.lineno}"  # type: ignore[attr-defined]
        for name, nodes in calls.items()
        for call in nodes
        if "details" not in {k.arg for k in call.keywords}  # type: ignore[attr-defined]
    ]
    return undecided, sum(len(nodes) for nodes in calls.values())


def test_every_service_decides_on_the_details_when_it_builds_an_activity_summary() -> None:
    undecided, checked = _undecided_summary_calls()

    assert checked >= 2, "the scan found too few activity summaries to be reading the services"
    assert undecided == [], "pass details= to to_summary: the policy decision, or False where nothing may be returned"


def test_the_service_scan_refuses_a_call_without_the_decision() -> None:
    assert _undecided_summary_calls("def f(r):\n    r.to_summary(None)\n") == (["planted.py:f:2"], 1)
    assert _undecided_summary_calls("def f(r):\n    r.to_summary(None, details=False)\n") == ([], 1)
