"""A version or sprint a work package result may name.

Both are shared into projects other than the one that defines them, and the link a work package
carries names the resource without its defining project. A result names one only when it is in the
`VisibleReferences` the service decided on, so a reference the adapter does not recognize loses its
title instead of leaking it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

ReferenceKind = Literal["version", "sprint"]


@dataclass(frozen=True)
class ScopedReference:
    kind: ReferenceKind
    id: int


class VisibleReferences:
    """The references a result may name. Built only by `_work_package_references`, which makes the
    decision; the adapters receive it and keep a title only if it contains the reference."""

    __slots__ = ("_visible",)

    def __init__(self, visible: frozenset[ScopedReference] | None) -> None:
        self._visible = visible

    @classmethod
    def everything(cls) -> VisibleReferences:
        return cls(None)

    @classmethod
    def only(cls, references: Iterable[ScopedReference]) -> VisibleReferences:
        return cls(frozenset(references))

    def contains(self, reference: ScopedReference) -> bool:
        return self._visible is None or reference in self._visible


class ScopedReferencesAllowedBulkCheck(Protocol):
    """Narrow seam onto `ScopedReferenceResolver.references_allowed`.

    `seeds` are the resources the server embedded in the response, which carry the defining project
    and need no request. Returns `bool | Exception` per reference, so the caller re-raises the first
    failure only for a reference it needs.
    """

    def __call__(
        self, references: Iterable[ScopedReference], *, seeds: Mapping[ScopedReference, Mapping[str, Any]]
    ) -> Awaitable[dict[ScopedReference, bool | Exception]]: ...
