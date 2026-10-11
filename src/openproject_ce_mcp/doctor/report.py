"""What the doctor reports: findings and the state of an entry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(Enum):
    OK = "OK"
    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Finding:
    level: Level
    text: str
    # True when the doctor could not establish the fact, as opposed to a known problem.
    unverified: bool = False


def ok(text: str) -> Finding:
    return Finding(Level.OK, text)


def info(text: str) -> Finding:
    return Finding(Level.INFO, text)


def warn(text: str) -> Finding:
    return Finding(Level.WARN, text)


def unverified(text: str) -> Finding:
    return Finding(Level.WARN, text, unverified=True)


def fail(text: str) -> Finding:
    return Finding(Level.FAIL, text)


class State(Enum):
    ACTIVE = "active"
    # Validated and reported, but excluded from the exit status.
    INACTIVE = "inactive"
    # Not started on this machine; not validated here.
    REMOTE = "remote"
    # Active elsewhere or for teammates, so it counts.
    SHADOWED = "shadowed"
