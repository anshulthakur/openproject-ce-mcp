"""Which tool call the running code serves.

Something read from OpenProject once per call, not once per response, needs a name for the call.
The tool boundary opens a scope; outside one (a script, a test of a lower layer) there is no call,
and callers treat that as "never seen before".
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_CURRENT: ContextVar[int | None] = ContextVar("tool_call", default=None)
_NEXT_ID = itertools.count(1)


def current_tool_call() -> int | None:
    return _CURRENT.get()


@contextmanager
def tool_call() -> Iterator[int]:
    call_id = next(_NEXT_ID)
    token = _CURRENT.set(call_id)
    try:
        yield call_id
    finally:
        _CURRENT.reset(token)
