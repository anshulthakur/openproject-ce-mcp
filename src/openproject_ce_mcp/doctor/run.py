"""Running the doctor: discover entries, check each on its own terms, report, and set the exit status."""

from __future__ import annotations

import platform
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from .. import __version__
from ..config import Settings
from .checks import SERVER_BIN, Evaluation, ProbeRunner, check_dispatch, evaluate, preview_tools, run_probes
from .codex import ASSUMED_LOCAL, CodexCli
from .discovery import discover
from .environment import EffectiveEnv, HostContext, base_keys
from .hosts import Host, ProcessEnvHost, Subject
from .probe import run_connectivity_probe
from .report import State

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def run_doctor() -> int:
    """CLI entry point for doctor command."""
    return _run_doctor()


def _run_doctor(
    *,
    entries: Sequence[Subject] | None = None,
    probe: ProbeRunner = run_connectivity_probe,
    ctx: HostContext | None = None,
    codex: CodexCli | None = None,
) -> int:
    """Run all checks; ``entries`` replaces discovery and ``probe`` the connection-check child."""
    from ..setup_cli import _project_cwd

    ctx = ctx or HostContext.current(_project_cwd())
    print("Running OpenProject MCP diagnostics...\n")
    _check_binary()

    if entries is None:
        found = discover(ctx, codex or CodexCli.installed(ctx))
        print("Config files:")
        print("\n".join(found.overview) if found.overview else "  (none)")
        subjects = found.subjects
    else:
        subjects = list(entries)
    if not subjects:
        print("[INFO] No client configures an OpenProject server; checking the process environment instead.")
        subjects = [Subject(ProcessEnvHost(), "", effective=EffectiveEnv(env=ctx.shell_env.copy()))]

    print(
        "\nConnection checks run with each entry's environment plus this shell's "
        f"{', '.join(base_keys(ctx.platform))} (platform minimum), with OPENPROJECT_MAX_RETRIES=0 "
        "and OPENPROJECT_TIMEOUT=5."
    )
    _print_host_notes(subjects, ctx)
    evaluations = [evaluate(subject, ctx) for subject in subjects]
    run_probes(evaluations, probe)
    preview_tools(evaluations)
    check_dispatch(evaluations)
    _print_blocks(evaluations)

    _print_restart_hints(subjects)
    return _summarize(evaluations)


def _check_binary() -> None:
    """Report binary path, package version, and the Python running it."""
    path = shutil.which(SERVER_BIN) or sys.argv[0]
    print(f"[OK] Binary: {path} (v{__version__})")
    print(f"[OK] Python: {platform.python_version()} ({sys.executable})")


def _print_host_notes(subjects: Sequence[Subject], ctx: HostContext) -> None:
    seen: dict[str, Host] = {}
    for subject in subjects:
        seen.setdefault(subject.host.key, subject.host)
    for host in seen.values():
        for note in host.notes(ctx):
            print(f"[{note.level.value}] {host.label}: {note.text}")


@dataclass
class _Block:
    """Evaluations that differ only in the host, printed once."""

    evaluations: list[Evaluation]

    @property
    def first(self) -> Evaluation:
        return self.evaluations[0]

    @property
    def identity(self) -> str:
        labels = ", ".join(e.subject.host.label for e in self.evaluations)
        return " ".join(part for part in (labels, self.first.subject.label) if part)


def _same_apart_from_host(a: Evaluation, b: Evaluation) -> bool:
    return (
        a.subject.label == b.subject.label
        and a.subject.state == b.subject.state
        and a.subject.state_reason == b.subject.state_reason
        and a.assumed_local == b.assumed_local
        and a.findings == b.findings
        and a.settings == b.settings
    )


def _blocks(evaluations: Sequence[Evaluation]) -> list[_Block]:
    blocks: list[_Block] = []
    for evaluation in evaluations:
        block = next((b for b in blocks if _same_apart_from_host(b.first, evaluation)), None)
        if block is None:
            blocks.append(_Block([evaluation]))
        else:
            block.evaluations.append(evaluation)
    return blocks


def _print_blocks(evaluations: Sequence[Evaluation]) -> None:
    summarized: list[tuple[Settings, str]] = []
    for block in _blocks(evaluations):
        first, identity = block.first, block.identity
        subject = first.subject
        print()
        if first.assumed_local:
            print(f"[INFO] {identity}: {ASSUMED_LOCAL}")
        if subject.state is State.INACTIVE:
            print(f"[INFO] {identity}: inactive ({subject.state_reason}); checked, not counted")
        elif subject.state is State.SHADOWED:
            print(f"[INFO] {identity}: {subject.state_reason}; still counted, it applies elsewhere")
        for finding in first.findings:
            print(f"[{finding.level.value}] {identity}: {finding.text}")
            if finding is first.settings_finding:
                _print_scope_summary(first, identity, summarized)


def _print_scope_summary(evaluation: Evaluation, identity: str, summarized: list[tuple[Settings, str]]) -> None:
    earlier = next((name for settings, name in summarized if settings == evaluation.settings), None)
    if earlier is not None:
        print(f"    scope as for {earlier}")
        return
    assert evaluation.settings is not None
    summarized.append((evaluation.settings, identity))
    for line in evaluation.scope_summary:
        print(f"    {line}")


_RESTART_CLIENT_KEY = {"vscode-agent-host": "vscode"}


def _print_restart_hints(subjects: Sequence[Subject]) -> None:
    """Show how to restart each client that has a counting entry."""
    from ..setup_cli import _clients

    keys = {_RESTART_CLIENT_KEY.get(s.host.key, s.host.key) for s in subjects if s.counts}
    hints = [client for client in _clients() if client.key in keys and client.restart_hint]
    if hints:
        print("\nRestart needed for:")
        for client in hints:
            print(f"  - {client.label}: {client.restart_hint}")


def _summarize(evaluations: Sequence[Evaluation]) -> int:
    counting = [e for e in evaluations if e.subject.counts]
    failed = [e for e in counting if e.failed]
    if failed:
        _print_entry_list("failed; see the [FAIL] lines above", failed)
        return EXIT_FAILURE
    if not counting:
        print("\n[WARN] no active OpenProject entry")
        return EXIT_SUCCESS
    not_verified = [e for e in evaluations if e.unverified and (e.subject.counts or e.subject.state is State.REMOTE)]
    if not_verified:
        _print_entry_list("could not be fully verified; see the [WARN] lines above", not_verified)
        return EXIT_SUCCESS
    print("\nAll checks passed.")
    return EXIT_SUCCESS


def _print_entry_list(outcome: str, evaluations: Sequence[Evaluation]) -> None:
    """Counted as printed: one line per output block, not per host."""
    identities = [block.identity for block in _blocks(evaluations)]
    count = len(identities)
    print(f"\n{count} entr{'y' if count == 1 else 'ies'} {outcome}:")
    for identity in identities:
        print(f"  - {identity}")
