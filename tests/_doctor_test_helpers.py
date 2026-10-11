"""A sandboxed machine for doctor tests: temporary home, project, system paths, and fakes."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from openproject_ce_mcp import setup_cli
from openproject_ce_mcp.doctor.codex import CodexCli, ProcessResult
from openproject_ce_mcp.doctor.environment import EnvMap, HostContext, SystemPaths
from openproject_ce_mcp.doctor.hosts import Subject
from openproject_ce_mcp.doctor.probe import ProbeResult
from openproject_ce_mcp.doctor.run import _run_doctor

BASE_URL = "https://op.example.invalid"
TOKEN = "fake-token-1"
VALID_ENV = {"OPENPROJECT_BASE_URL": BASE_URL, "OPENPROJECT_API_TOKEN": TOKEN}

_CLEARED_PREFIXES = ("OPENPROJECT_", "CLAUDE_CODE_", "CODEX_", "COPILOT_", "VSCODE_")
_CLEARED_NAMES = {
    name for base in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY") for name in (base, base.lower())
}


class FakeProbe:
    def __init__(self, result: ProbeResult | None = None) -> None:
        self.result = result or ProbeResult(True, user="Probe User")
        self.calls: list[dict[str, str]] = []

    def __call__(self, env: Mapping[str, str], **_kwargs: object) -> ProbeResult:
        self.calls.append(dict(env))
        return self.result


class FakeCodex(CodexCli):
    """Answers ``codex mcp list`` with recorded output, per view."""

    def __init__(
        self,
        this_directory: ProcessResult,
        user_level: ProcessResult | None = None,
        *,
        path: str = "/fake/bin/codex",
    ) -> None:
        super().__init__(path)
        self.this_directory = this_directory
        self.user_level = user_level if user_level is not None else this_directory
        self.calls: list[tuple[list[str], Path, dict[str, str], list[str]]] = []

    def run(self, args: Sequence[str], cwd: Path, env: Mapping[str, str], **_kwargs: object) -> ProcessResult:
        self.calls.append((list(args), cwd, dict(env), sorted(p.name for p in cwd.iterdir())))
        return self.user_level if "project_root_markers=[]" in args else self.this_directory


def listed(
    name: str = "openproject",
    *,
    command: str = "openproject-ce-mcp",
    args: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    env_vars: Sequence[object] = (),
    enabled: bool = True,
    disabled_reason: str | None = None,
) -> dict[str, object]:
    """One server in the shape ``codex mcp list --json`` prints (Codex 0.161.0)."""
    return {
        "name": name,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
        "transport": {
            "type": "stdio",
            "command": command,
            "args": list(args),
            "env": dict(env) if env is not None else None,
            "env_vars": list(env_vars),
            "cwd": None,
        },
        "startup_timeout_sec": None,
        "tool_timeout_sec": None,
        "auth_status": "unsupported",
    }


def listing(*servers: dict[str, object]) -> ProcessResult:
    return ProcessResult(0, json.dumps(list(servers), indent=2), "")


_HOST_LABELS = sorted(
    ("VS Code Agent Host", "VS Code", "Claude Code", "Claude Desktop", "Cursor", "Codex", "process environment"),
    key=len,
    reverse=True,
)


def _about(line: str, identity: str) -> bool:
    if not line.startswith("[") or "] " not in line:
        return False
    head = line.split("] ", 1)[1].split(": ", 1)[0]
    if head == identity:
        return True
    host = next((h for h in _HOST_LABELS if identity == h or identity.startswith(h + " ")), None)
    if host is None:
        return False
    label = identity[len(host) :].strip()
    hosts = head[: len(head) - len(label)].strip() if head.endswith(label) else None
    return hosts is not None and host in hosts.split(", ")


@dataclass
class Run:
    exit_code: int
    out: str

    def lines(self, identity: str) -> list[str]:
        """Lines about ``identity``, also inside a block that lists several hosts."""
        return [line for line in self.out.splitlines() if _about(line, identity)]

    def levels(self, identity: str) -> set[str]:
        return {line.split("]", 1)[0].lstrip("[") for line in self.lines(identity)}


@dataclass
class Sandbox:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    platform: str = sys.platform
    probe: FakeProbe = field(default_factory=FakeProbe)

    def __post_init__(self) -> None:
        self.original_path = os.environ.get("PATH", "")
        self.home = self.root / "home"
        self.cwd = self.root / "project"
        self.system = self.root / "system"
        self.bin = self.root / "bin"
        for directory in (self.home, self.cwd, self.system, self.bin):
            directory.mkdir(parents=True, exist_ok=True)
        for name in list(os.environ):
            if name.startswith(_CLEARED_PREFIXES) or name in _CLEARED_NAMES:
                self.monkeypatch.delenv(name)
        self.monkeypatch.setenv("HOME", str(self.home))
        self.monkeypatch.setenv("USERPROFILE", str(self.home))
        self.monkeypatch.setenv("APPDATA", str(self.home / "AppData" / "Roaming"))
        self.monkeypatch.setenv("PWD", str(self.cwd))
        self.monkeypatch.setenv("PATH", str(self.bin))
        self.monkeypatch.chdir(self.cwd)

    # files

    def write(self, path: Path, content: str | Mapping[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    @property
    def claude_state(self) -> Path:
        return self.home / ".claude.json"

    @property
    def mcp_json(self) -> Path:
        return self.cwd / ".mcp.json"

    @property
    def desktop_config(self) -> Path:
        return setup_cli._claude_desktop_path()

    @property
    def vscode_user_mcp(self) -> Path:
        return setup_cli._vscode_user_mcp_path()

    @property
    def vscode_workspace_mcp(self) -> Path:
        return self.cwd / ".vscode" / "mcp.json"

    @property
    def codex_config(self) -> Path:
        return self.home / ".codex" / "config.toml"

    def detect_vscode(self) -> None:
        self.vscode_user_mcp.parent.mkdir(parents=True, exist_ok=True)

    def executable(self, name: str, directory: Path | None = None) -> Path:
        path = (directory or self.bin) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    # running

    def system_paths(self) -> SystemPaths:
        return SystemPaths(
            claude_managed_settings=self.system / "managed-settings.json",
            codex_system_config=self.system / "codex" / "config.toml",
            codex_managed_config=self.system / "codex" / "managed_config.toml",
        )

    def ctx(self, platform: str | None = None) -> HostContext:
        platform = platform or self.platform
        return HostContext(
            shell_env=EnvMap(os.environ, case_insensitive=platform == "win32"),
            cwd=self.cwd,
            home=self.home,
            platform=platform,
            system=self.system_paths(),
        )

    def run(
        self,
        capsys: pytest.CaptureFixture[str],
        *,
        codex: CodexCli | None = None,
        entries: Sequence[Subject] | None = None,
        platform: str | None = None,
    ) -> Run:
        capsys.readouterr()
        exit_code = _run_doctor(
            entries=entries, probe=self.probe, ctx=self.ctx(platform), codex=codex or CodexCli(None)
        )
        captured = capsys.readouterr()
        return Run(exit_code, captured.out + captured.err)


def server(env: Mapping[str, object] | None = None, command: str = "openproject-ce-mcp", **extra: object) -> dict:
    entry: dict[str, object] = {"command": command, "env": dict(env if env is not None else VALID_ENV)}
    entry.update(extra)
    return entry
