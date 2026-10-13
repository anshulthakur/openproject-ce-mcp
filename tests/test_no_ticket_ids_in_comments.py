"""Code comments and docstrings carry the reason, not a tracker id: an id
says nothing to a reader without tracker access and goes stale when the
ticket is closed or renumbered. String literals are data and stay allowed."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TICKET_ID = re.compile(r"\bOPM-\d+")


def _python_files() -> list[Path]:
    return sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")])


def _comments_and_docstrings(source: str) -> list[tuple[int, str]]:
    found = [
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None:
                found.append((node.body[0].lineno, docstring))
    return found


def test_no_tracker_ids_in_comments_or_docstrings() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in _python_files()
        for line, text in _comments_and_docstrings(path.read_text())
        if _TICKET_ID.search(text)
    ]
    assert offenders == []


def test_the_check_sees_comments_and_docstrings() -> None:
    sample = '"""Module OPM-1."""\n\n\ndef f():\n    """Doc OPM-2."""\n    return "OPM-3"  # note OPM-4\n'
    texts = [text for _, text in _comments_and_docstrings(sample)]
    assert sum(bool(_TICKET_ID.search(text)) for text in texts) == 3
