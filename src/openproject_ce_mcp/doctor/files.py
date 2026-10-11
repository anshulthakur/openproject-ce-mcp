"""Reading client configuration files: JSON, VS Code's JSONC, and ``envFile`` dotenv files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigFile:
    path: Path
    data: object = None
    error: str | None = None


def read_json_file(path: Path, *, jsonc: bool) -> ConfigFile | None:
    """Parse a client configuration file; None when it does not exist.

    Errors carry positions only: the file can hold tokens.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        return ConfigFile(path, error=f"cannot be read ({exc.strerror or type(exc).__name__})")
    except UnicodeDecodeError:
        return ConfigFile(path, error="is not UTF-8 text")
    try:
        return ConfigFile(path, data=json.loads(strip_jsonc(text) if jsonc else text))
    except json.JSONDecodeError as exc:
        return ConfigFile(path, error=f"is not valid JSON (line {exc.lineno}, column {exc.colno})")


def strip_jsonc(text: str) -> str:
    """Remove comments, then trailing commas: VS Code accepts both in its own files.

    Comments go first, so a comma followed by a comment and then a closing bracket is
    still recognized as trailing.
    """
    return _remove_trailing_commas(_remove_comments(text))


def _remove_comments(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            stop = n if end == -1 else end + 2
            out.append(" " + "\n" * text.count("\n", i, stop))
            i = stop
            continue
        else:
            out.append(char)
        i += 1
    return "".join(out)


def _remove_trailing_commas(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif char == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j >= n or text[j] not in "}]":
                out.append(char)
        else:
            out.append(char)
        i += 1
    return "".join(out)


def parse_env_file(src: str) -> dict[str, str]:
    """Port of VS Code's ``parseEnvFile`` (``src/vs/base/common/envfile.ts``), which reads ``envFile``."""
    result: dict[str, str] = {}
    for raw in src.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_env_line(line)
        if parsed is not None and parsed[0]:
            result[parsed[0]] = parsed[1]
    return result


def _parse_env_line(line: str) -> tuple[str, str] | None:
    if line.startswith("export "):
        line = line[7:].strip()
    separator = _index_outside_quotes(line, "=:")
    if separator == -1:
        return None
    key = line[:separator].strip()
    value = line[separator + 1 :].strip()
    comment = _index_outside_quotes(value, "#")
    if comment != -1:
        value = value[:comment].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        quote, value = value[0], value[1:-1]
        if quote == '"':
            value = value.replace("\\n", "\n").replace("\\r", "\r")
    return key, value


def _index_outside_quotes(text: str, targets: str) -> int:
    quote = ""
    for i, char in enumerate(text):
        if quote:
            if char == quote and (i == 0 or text[i - 1] != "\\"):
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char in targets:
            return i
    return -1
