"""Shared version-gate error translation.

Package-root shared kernel: pure, dependency-free wrapper used by any app/
Service whose underlying endpoint only exists from some OpenProject version
onward, without creating a layering violation.

Before this module, exactly one domain (Projects' `set_favorite`) translated
a version-gated endpoint's 404 into a version-aware hint; every other
version-gated domain (Meetings, wiki-page-links, user-schedule) let a plain
`NotFoundError` bubble up with no version context, contradicting what their
own docstrings already promise the caller ("Requires OpenProject X.Y+.").
`call_version_gated` generalizes the one existing pattern instead of leaving
each domain to reinvent it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import InvalidInputError, NotFoundError

_T = TypeVar("_T")


async def call_version_gated(call: Callable[[], Awaitable[_T]], *, feature: str, floor: str) -> _T:
    """Await `call()`; on `NotFoundError`, re-raise with a version-aware hint.

    `feature` names what the caller was trying to do (e.g. "Project
    favorites", "Meeting sections"); `floor` is the version floor from that
    feature's own docstring (e.g. "17.0", "17.6"). Only `NotFoundError` is
    translated -- every other exception (including a `NotFoundError` for a
    genuinely missing resource on an instance that DOES support the
    endpoint) is indistinguishable from "unsupported on this version" at
    this layer, so the hint is phrased as a possibility ("appears to be
    older"), not a certainty, matching the existing Projects wording this
    generalizes.
    """
    try:
        return await call()
    except NotFoundError as exc:
        raise NotFoundError(
            f"{feature} requires OpenProject {floor} or newer; this instance appears to be older."
        ) from exc


async def call_query_version_gated(call: Callable[[], Awaitable[_T]], *, feature: str, floor: str) -> _T:
    """Await `call()`; on `InvalidInputError`, add the version floor to OpenProject's own message.

    For a query filter operator the server does not know yet, OpenProject
    answers 400 InvalidQuery, not 404, and on a new enough instance that same
    error also reports any other invalid filter or sort of the request. The
    server's reason therefore comes first and the floor is only offered as a
    condition, never as the diagnosis.
    """
    try:
        return await call()
    except InvalidInputError as exc:
        raise InvalidInputError(
            f"{exc} If this instance is older than OpenProject {floor}, {feature} is the cause: "
            f"it requires {floor} or newer."
        ) from exc
