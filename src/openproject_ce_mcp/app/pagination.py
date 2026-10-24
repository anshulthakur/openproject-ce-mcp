"""Shared pagination-envelope helpers.

Package-root shared kernel: pure, dependency-free pagination math used by the
Versions domain (and available to any other app/ domain) without creating a
layering violation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar


def _next_offset(offset: int, limit: int, total: int) -> int | None:
    if offset * limit >= total:
        return None
    return offset + 1


def paginate_server(*, offset: int, limit: int, total: int) -> tuple[int | None, bool]:
    """next_offset/truncated for a page the server already sliced (offset/pageSize sent
    as request params, `total` trusted as reported).

    Single source of truth for this pair: `truncated` is exactly
    "next_offset is not None", derived here rather than re-derived per call site.
    """
    next_offset = _next_offset(offset, limit, total)
    return next_offset, next_offset is not None


def clamp_limit(limit: int | None, *, default_page_size: int, max_page_size: int, max_results: int) -> int:
    """Resolve a caller-supplied `limit` (or None) to an effective page size,
    capped by both `max_page_size` and `max_results`.

    Single source of truth for `effective_limit = min(limit or
    settings.default_page_size, settings.max_page_size, settings.max_results)`,
    shared across every Service that needs it rather than duplicated per call site.
    """
    return min(limit or default_page_size, max_page_size, max_results)


def effective_limit(limit: int | None, *, settings: Any) -> int:
    """`clamp_limit`, but reading `default_page_size`/`max_page_size`/`max_results`
    directly off a `Settings` instance instead of three separate keyword args.

    Shared by every Service that needs this computation, rather than each
    duplicating its own `_effective_limit(self, limit)` wrapper around the
    same three `Settings` fields. `settings` is typed `Any` here, not
    `config.Settings`, only to avoid this dependency-free package-root module
    importing from the parent package -- every call site passes a real
    `Settings` instance.
    """
    return clamp_limit(
        limit,
        default_page_size=settings.default_page_size,
        max_page_size=settings.max_page_size,
        max_results=settings.max_results,
    )


def paginate_client(*, offset: int, limit: int, results: list[Any]) -> tuple[list[Any], int, int | None, bool]:
    """Slice an already-fetched, already-filtered in-memory list into one page.

    Returns (page, total, next_offset, truncated). `total` is len(results) --
    the filtered candidate set already held locally, not a server-reported
    total. Same next_offset/truncated relationship as paginate_server.
    """
    total = len(results)
    start = (offset - 1) * limit
    end = start + limit
    page = results[start:end]
    next_offset, truncated = paginate_server(offset=offset, limit=limit, total=total)
    return page, total, next_offset, truncated


_T = TypeVar("_T")


def collection_exhausted(total: Any, fetched: int) -> bool:
    """Whether `fetched` raw elements are all the collection holds, by the server's own `total`.

    A short page does not say so: OpenProject cuts a requested page size to its configured maximum,
    so a page of the maximum is short of the requested size and the next one still holds elements.
    A `total` that is not a number leaves the empty page as the end of the collection.
    """
    return isinstance(total, int) and fetched >= total


def page_is_last(payload: Mapping[str, Any], *, offset: int, requested_page_size: int, total: int) -> bool:
    """Whether the page at `offset` is the last one, by the page size the server reports.

    OpenProject cuts a requested page size to its configured maximum and reports the size it used as
    `pageSize`; `offset * requested_page_size` would call a page the last one while elements remain.
    """
    reported = payload.get("pageSize")
    page_size = reported if isinstance(reported, int) and reported > 0 else requested_page_size
    return offset * page_size >= total


async def fetch_bounded_and_paginate(
    *,
    fetch_page: Callable[[int, int], Awaitable[dict[str, Any]]],
    normalize: Callable[[dict[str, Any]], _T],
    server_page_size: int,
    offset: int,
    limit: int,
    item_allowed: Callable[[dict[str, Any]], Awaitable[bool]] | None = None,
    item_allowed_bulk: Callable[[list[dict[str, Any]]], Awaitable[list[bool | Exception]]] | None = None,
) -> tuple[list[_T], int, int | None, bool]:
    """Scan server pages, normalize + filter the raw elements, and stop as
    soon as `limit + 1` allowed items are confirmed (or the collection is
    genuinely exhausted) -- never walks the full collection first.

    Collects one extra (`limit + 1`) allowed item before deciding
    `truncated`, matching the same shape as `scan_and_paginate`/
    `scan_records_and_paginate`: this confirms "more matches exist" beyond
    the requested window rather than merely "this happened to be the last
    one", so `truncated`/`next_offset` are never set on a false positive --
    a follow-up call using a promised `next_offset` that turned out to be
    wrong would silently return nothing.

    `item_allowed` is async (rather than plain bool) so ACL checks that need
    their own lookups (e.g. relations checking each linked work package's
    project) can use this helper too.

    Some project-scoped sub-collection endpoints (verified live: a project's
    versions endpoint) silently ignore both offset and pageSize and always
    return every element -- without the seen-ids check below, the
    short-page/limit-reached break conditions never trigger and this loops
    forever, re-fetching the same full page. Tracked against the RAW element
    ids (before item_allowed/normalize), so a page that's merely fully
    filtered out doesn't get mistaken for a repeat.

    `item_allowed_bulk` is a page-batching alternative to `item_allowed`:
    given ALL of a fetched page's raw elements at once, it resolves whatever
    concurrent I/O each element's allowlist decision needs (e.g. Relations'
    from/to hrefs) in one batch, before the sequential skip/limit+1-lookahead
    consumption loop below runs -- that loop just reads a pre-resolved
    `bool | Exception` outcome per element instead of awaiting
    `item_allowed(item)` one at a time. Exactly one of
    `item_allowed`/`item_allowed_bulk` may be given (or neither, for an
    unfiltered scan). Deliberately still resolves a whole PAGE at a time,
    never the whole call's collection -- resolving speculatively beyond the
    current page would defeat the early-stopping this helper exists for.

    An `Exception` outcome is only raised if the sequential consumption logic
    would actually have reached that element under the one-at-a-time
    `item_allowed` control flow (i.e. skip-counted or considered for the
    limit+1 lookahead) -- an outcome for an element the loop breaks out of
    the page before reaching is silently discarded, matching what the
    sequential logic would have done (it would never have awaited that
    element's check at all).
    """
    skip_count = (offset - 1) * limit
    skipped = 0
    results: list[_T] = []
    seen_ids: set[Any] = set()
    server_offset = 1
    fetched = 0
    is_first_page = True

    while len(results) <= limit:
        payload = await fetch_page(server_offset, server_page_size)
        raw_elements = [item for item in payload.get("_embedded", {}).get("elements", []) if isinstance(item, dict)]
        if not raw_elements:
            break
        fetched += len(raw_elements)
        page_ids = {item.get("id") for item in raw_elements}
        if not is_first_page and page_ids and page_ids <= seen_ids:
            break
        is_first_page = False
        seen_ids.update(page_ids)

        page_outcomes: list[bool | Exception] | None = None
        if item_allowed_bulk is not None:
            page_outcomes = await item_allowed_bulk(raw_elements)

        for index, item in enumerate(raw_elements):
            if page_outcomes is not None:
                outcome = page_outcomes[index]
                if isinstance(outcome, Exception):
                    raise outcome
                allowed = outcome
            elif item_allowed is not None:
                allowed = await item_allowed(item)
            else:
                allowed = True
            if not allowed:
                continue
            if skipped < skip_count:
                skipped += 1
                continue
            results.append(normalize(item))
            if len(results) > limit:
                # The (limit + 1)-th allowed item proves at least one more
                # match exists beyond the requested page -- stop
                # immediately, without checking the rest of this page or
                # server exhaustion. Any outcome for a later element in
                # page_outcomes (already resolved speculatively) is simply
                # never consulted here, so a deferred Exception past this
                # point is correctly never raised.
                break

        if len(results) > limit:
            break
        if collection_exhausted(payload.get("total"), fetched):
            break
        server_offset += 1

    truncated = len(results) > limit
    if truncated:
        results = results[:limit]
    total = len(results)
    next_offset = offset + 1 if truncated else None
    return results, total, next_offset, truncated


async def scan_and_paginate(
    *,
    fetch_page: Callable[[int, int], Awaitable[dict[str, Any]]],
    item_allowed: Callable[[dict[str, Any]], Awaitable[bool]],
    server_page_size: int,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Sibling of `fetch_bounded_and_paginate`/`scan_records_and_paginate`,
    for callers whose raw HAL page dict has no separate `normalize`/`total`
    concerns of its own (the caller normalizes the returned raw elements
    itself). All three helpers share the same early-stopping shape: scan
    just enough server pages to collect `limit + 1` allowed raw elements
    (one extra, to distinguish "more matches exist" from "this happened to
    be the last one") and stop, skipping the first `(offset - 1) * limit`
    already-seen matches along the way. Some redundant server calls on deep
    pagination (a fresh scan from page 1 on every call, since the two
    offset spaces -- caller units of `limit`, server units of
    `server_page_size` -- can't be conflated into one server-side offset),
    but bounded work per call instead of a full collection walk.

    Returns the raw (unnormalized) allowed elements for the requested page --
    callers normalize/apply any further post-normalize filtering themselves,
    since result and filter shapes differ per caller. `fetch_page` is an
    injected callable rather than a hardwired path, matching
    `fetch_bounded_and_paginate`'s shape.
    """
    skip_count = (offset - 1) * limit
    skipped = 0
    results: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    server_offset = 1
    fetched = 0
    is_first_page = True

    while len(results) <= limit:
        payload = await fetch_page(server_offset, server_page_size)
        raw_elements = [item for item in payload.get("_embedded", {}).get("elements", []) if isinstance(item, dict)]
        if not raw_elements:
            break
        fetched += len(raw_elements)
        # Same repeat-page guard as fetch_bounded_and_paginate/paginate_all:
        # some project-scoped sub-collection endpoints silently ignore
        # offset/pageSize and always return the same full page, which would
        # otherwise loop forever since the elements never reach `total`.
        page_ids = {item.get("id") for item in raw_elements}
        if not is_first_page and page_ids and page_ids <= seen_ids:
            break
        is_first_page = False
        seen_ids.update(page_ids)

        for item in raw_elements:
            if not await item_allowed(item):
                continue
            if skipped < skip_count:
                skipped += 1
                continue
            results.append(item)
            if len(results) > limit:
                # The (limit + 1)-th allowed item proves at least one more
                # match exists beyond the requested page -- stop immediately,
                # without checking the rest of this page or server exhaustion.
                break

        if len(results) > limit:
            break
        if collection_exhausted(payload.get("total"), fetched):
            break
        server_offset += 1

    truncated = len(results) > limit
    if truncated:
        results = results[:limit]
    return results, truncated


async def scan_records_and_paginate(
    fetch_page: Callable[[int, int], Awaitable[tuple[list[_T], int]]],
    *,
    item_allowed: Callable[[_T], bool] | None = None,
    server_page_size: int,
    offset: int,
    limit: int,
    key: Callable[[_T], Any] | None = None,
    item_allowed_bulk: Callable[[list[_T]], Awaitable[list[bool | Exception]]] | None = None,
) -> tuple[list[_T], bool]:
    """Early-stopping counterpart to `paginate_all`, for callers whose
    `fetch_page` already returns normalized records (not raw HAL dicts) --
    e.g. an Adapter's own `list_all(offset, page_size) -> (records, total)`
    method, the same signature `paginate_all` already accepts.

    Same early-stopping shape as `scan_and_paginate`/`fetch_bounded_and_paginate`
    (collects `limit + 1` allowed records before deciding `truncated`, to
    distinguish "more matches exist" from "this happened to be the last
    one"), adapted to `paginate_all`'s already-normalized-record contract
    instead of `fetch_bounded_and_paginate`'s raw-dict-plus-normalize-callback
    contract -- the two input shapes don't share one helper cleanly, hence
    three siblings rather than one.

    `item_allowed` here is SYNCHRONOUS (unlike `scan_and_paginate`'s async
    version): a per-item filter on normalized fields needs no I/O. A filter
    that does needs I/O passes `item_allowed_bulk` instead, with the same
    page-at-a-time contract as `fetch_bounded_and_paginate`'s: outcomes are
    resolved for the whole fetched page, and an `Exception` outcome is raised
    only for an element the loop actually reaches. At most one of the two is
    given; neither scans unfiltered.

    The end of the collection is the server-reported `total` (see `collection_exhausted`), the empty
    page, or a repeated page.
    """
    skip_count = (offset - 1) * limit
    skipped = 0
    results: list[_T] = []
    seen_keys: set[Any] = set()
    server_offset = 1
    fetched = 0
    is_first_page = True

    while len(results) <= limit:
        page_items, total = await fetch_page(server_offset, server_page_size)
        if not page_items:
            break
        fetched += len(page_items)
        if key is not None:
            page_keys = {key(item) for item in page_items}
            if not is_first_page and page_keys and page_keys <= seen_keys:
                break
            seen_keys.update(page_keys)
        is_first_page = False

        page_outcomes = await item_allowed_bulk(page_items) if item_allowed_bulk is not None else None
        for index, item in enumerate(page_items):
            if page_outcomes is not None:
                outcome = page_outcomes[index]
                if isinstance(outcome, Exception):
                    raise outcome
                allowed = outcome
            elif item_allowed is not None:
                allowed = item_allowed(item)
            else:
                allowed = True
            if not allowed:
                continue
            if skipped < skip_count:
                skipped += 1
                continue
            results.append(item)
            if len(results) > limit:
                break

        if len(results) > limit:
            break
        if collection_exhausted(total, fetched):
            break
        server_offset += 1

    truncated = len(results) > limit
    if truncated:
        results = results[:limit]
    return results, truncated


async def paginate_all(
    fetch_page: Callable[[int, int], Awaitable[tuple[list[_T], int]]],
    *,
    page_size: int,
    key: Callable[[_T], Any] | None = None,
) -> list[_T]:
    """Walk a server-paginated fetcher (offset, page_size) -> (items, total) to
    completion, returning every item across all pages.

    For an internal consumer that needs the complete dataset to scan (e.g.
    resolving a name reference by value), not a single page for display.
    `VersionResolver`/`ProjectResolver` each hand-roll an equivalent
    `while True` loop already (see version_resolver.py, project_resolver.py),
    but those are tied to project-scoped fetch signatures with per-page
    allowlist checks -- not extracted here to avoid forcing an unrelated
    refactor of that project-scoped machinery onto this purely-global helper.

    Some sub-collection endpoints (verified live: a project's versions
    endpoint) silently ignore both offset and page size and always return
    every element -- without the seen-keys check below, `truncated` never
    becomes False and this loops forever, re-fetching the same full page.
    `key` extracts a per-item identity (e.g. `lambda r: r.summary.id`) so a
    repeated page is detected and dropped rather than merely capped; when
    omitted, an accumulated-count check against `total` still prevents the
    infinite loop, but a repeated page's items would be duplicated in the
    result.
    """
    items: list[_T] = []
    seen_keys: set[Any] = set()
    offset = 1
    is_first_page = True
    while True:
        page_items, total = await fetch_page(offset, page_size)
        if key is not None:
            page_keys = {key(item) for item in page_items}
            if not is_first_page and page_keys and page_keys <= seen_keys:
                return items
            seen_keys.update(page_keys)
        is_first_page = False
        items.extend(page_items)
        if not page_items or len(items) >= total:
            return items
        offset += 1
