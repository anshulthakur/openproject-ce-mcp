"""Which files each host reads, and the entries in them that run OpenProject."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

from .codex import CodexCli, codex_subjects
from .environment import HostContext, Syntax, resolve
from .files import ConfigFile, read_json_file
from .hosts import (
    ClaudeCodeHost,
    ClaudeDesktopHost,
    CursorHost,
    Host,
    RawEntry,
    Source,
    Subject,
    VsCodeAgentHost,
    VsCodeHost,
    claude_project_keys,
    is_openproject_server,
    is_remote,
    parse_server,
)
from .report import Finding, State, fail, info, unverified


@dataclass
class Discovery:
    subjects: list[Subject] = field(default_factory=list)
    # What was found where, for the overview at the top of the report.
    overview: list[str] = field(default_factory=list)


def display(path: Path, ctx: HostContext) -> str:
    """Paths in this directory relative to it, paths in the home directory with ``~``."""
    for base, prefix in ((ctx.cwd, ""), (ctx.home, "~/")):
        try:
            return prefix + path.relative_to(base).as_posix()
        except ValueError:
            continue
    return str(path)


@dataclass
class _Files:
    """Each configuration file is read once per syntax, whichever hosts load it."""

    ctx: HostContext
    overview: list[str]
    cache: dict[tuple[Path, bool], ConfigFile | None] = field(default_factory=dict)
    reported: set[Path] = field(default_factory=set)
    with_entries: set[Path] = field(default_factory=set)

    def read(self, path: Path, *, jsonc: bool = False) -> ConfigFile | None:
        if (path, jsonc) not in self.cache:
            self.cache[(path, jsonc)] = read_json_file(path, jsonc=jsonc)
        return self.cache[(path, jsonc)]

    def problem(self, host: Host, path: Path, problem: str) -> list[Subject]:
        """A file that cannot be used may hold an entry: one FAIL, however many hosts read it."""
        if path in self.reported:
            return []
        self.reported.add(path)
        shown = display(path, self.ctx)
        return [Subject(host, f"({shown})", findings=[fail(f"{shown} {problem}")])]


def discover(ctx: HostContext, codex: CodexCli) -> Discovery:
    from ..setup_cli import _clients

    clients = {client.key: client for client in _clients()}
    files = _Files(ctx, [])
    claude_project = clients["claude-code"].project_target
    vscode_workspace = clients["vscode"].project_target
    cursor_workspace = clients["cursor"].project_target
    assert claude_project is not None and vscode_workspace is not None and cursor_workspace is not None

    subjects = _claude_code_subjects(ctx, files, clients["claude-code"].target, claude_project)
    subjects += _source_subjects(
        ClaudeDesktopHost(), Source(clients["claude-desktop"].target, "mcpServers", Syntax.UNKNOWN, "user"), files
    )

    vscode, agent = VsCodeHost(), VsCodeAgentHost()
    for path, scope, workspace in (
        (clients["vscode"].target, "user profile", None),
        (vscode_workspace, "workspace", ctx.cwd),
    ):
        source = Source(
            path,
            "servers",
            Syntax.VSCODE,
            scope,
            workspace,
            jsonc=True,
            forwarded_to_agent_host=True,
            reads_env_file=True,
        )
        subjects += _source_subjects(vscode, source, files)
        subjects += _source_subjects(agent, source, files)
    if clients["vscode"].detected():
        discovery = _discovery_setting(files, clients["vscode"].target.parent / "settings.json")
        copilot_home = ctx.shell_env.get("COPILOT_HOME")
        copilot = (Path(copilot_home) if copilot_home else ctx.home / ".copilot") / "mcp-config.json"
        portable = Source(
            claude_project, "mcpServers", Syntax.COPILOT, "workspace", ctx.cwd, jsonc=True, root_key_optional=True
        )
        subjects += _source_subjects(vscode, portable, files)
        subjects += _source_subjects(agent, _for_agent_host(portable), files)
        copilot_source = Source(copilot, "mcpServers", Syntax.COPILOT, "Copilot user")
        if _discovery_enabled(discovery, "copilot"):
            subjects += _source_subjects(vscode, copilot_source, files)
        # The Agent Host reads the Copilot file itself; the discovery setting does not apply.
        subjects += _source_subjects(agent, _for_agent_host(copilot_source), files)
        discovered = {
            "claude-desktop": (clients["claude-desktop"].target, None),
            "cursor-global": (clients["cursor"].target, None),
            "cursor-workspace": (cursor_workspace, ctx.cwd),
            "windsurf": (ctx.home / ".codeium" / "windsurf" / "mcp_config.json", None),
        }
        for key, (path, workspace) in discovered.items():
            if _discovery_enabled(discovery, key):
                source = Source(
                    path, "mcpServers", Syntax.LITERAL, f"{_DISCOVERY_LABELS[key]} via discovery", workspace
                )
                subjects += _source_subjects(vscode, source, files)

    cursor = CursorHost()
    for path, scope in ((clients["cursor"].target, "user"), (cursor_workspace, "workspace")):
        subjects += _source_subjects(cursor, Source(path, "mcpServers", Syntax.UNKNOWN, scope), files)

    report = codex_subjects(ctx, codex, lambda p: display(p, ctx))
    files.overview += [f"  - Codex ({layer.layer} layer): {display(layer.path, ctx)}" for layer in report.files]
    files.overview += [f"[{note.level.value}] Codex: {note.text}" for note in report.notes]
    subjects += report.subjects
    files.overview += permission_notes(files.with_entries | report.entry_files, ctx)
    return Discovery(subjects, files.overview)


def permission_notes(paths: Iterable[Path], ctx: HostContext) -> list[str]:
    """Files with an OpenProject entry usually hold its token, so group or other access exposes it.

    Only the mode is read, never the contents.
    """
    ordered = sorted(set(paths))
    if not ordered:
        return []
    if ctx.platform == "win32":
        return ["[INFO] Permissions: not checked on Windows (POSIX mode bits do not apply)"]
    notes = []
    for path in ordered:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            continue
        if mode & 0o077:
            notes.append(
                f"[WARN] Permissions: {display(path, ctx)} is readable or writable by group or others "
                f"(mode {oct(mode)}); `chmod 600 {path}` restricts it to you"
            )
    return notes


def _for_agent_host(source: Source) -> Source:
    """The Agent Host reads portable files itself; whether its harness substitutes ``${...}`` is not known."""
    return Source(
        source.path,
        source.root_key,
        Syntax.UNKNOWN,
        source.scope,
        source.workspace,
        jsonc=source.jsonc,
        root_key_optional=source.root_key_optional,
    )


_DISCOVERY_LABELS = {
    "claude-desktop": "Claude Desktop",
    "cursor-global": "Cursor user",
    "cursor-workspace": "Cursor workspace",
    "windsurf": "Windsurf",
}
# VS Code's defaultDiscoverySourceEnablement (mcpConfiguration.ts).
_DISCOVERY_DEFAULTS = {
    "claude-desktop": False,
    "copilot": True,
    "cursor-global": False,
    "cursor-workspace": False,
    "windsurf": False,
}


def _discovery_setting(files: _Files, settings_path: Path) -> object:
    settings = files.read(settings_path, jsonc=True)
    if settings is None or not isinstance(settings.data, dict):
        return None
    return settings.data.get("chat.mcp.discovery.enabled")


def _discovery_enabled(setting: object, source: str) -> bool:
    """Port of VS Code's ``isDiscoverySourceEnabled``: a boolean applies to every source."""
    if isinstance(setting, bool):
        return setting
    enabled = setting.get(source) if isinstance(setting, dict) else None
    return enabled if isinstance(enabled, bool) else _DISCOVERY_DEFAULTS[source]


def _openproject_entries(config: ConfigFile, source: Source) -> tuple[list[RawEntry], str | None]:
    data = config.data
    if not isinstance(data, dict):
        return [], "has no JSON object at the top level"
    servers = data.get(source.root_key)
    if servers is None and source.root_key_optional:
        servers = data
    if servers is None:
        return [], None
    if not isinstance(servers, dict):
        return [], f"has a `{source.root_key}` that is not an object"
    entries = [RawEntry(config.path, name, server, source.scope) for name, server in servers.items()]
    return [e for e in entries if is_openproject_server(e.name, e.server)], None


def _source_subjects(host: Host, source: Source, files: _Files) -> list[Subject]:
    config = files.read(source.path, jsonc=source.jsonc)
    if config is None:
        return []
    if config.error:
        return files.problem(host, source.path, config.error)
    entries, problem = _openproject_entries(config, source)
    if problem:
        return files.problem(host, source.path, problem)
    shown = display(source.path, files.ctx)
    files.overview.append(f"  - {host.label} ({source.scope}): {shown}, {_count(entries)}")
    if entries:
        files.with_entries.add(source.path)
    subjects = []
    for entry in entries:
        if (
            isinstance(host, VsCodeAgentHost)
            and source.forwarded_to_agent_host
            and "${input:" in json.dumps(entry.server)
        ):
            files.overview.append(
                f"[INFO] {entry.name} ({shown}) needs interactive input, so VS Code does not forward it to the Agent Host"
            )
            continue
        subjects.append(_entry_subject(host, source, entry, files.ctx))
    return subjects


def _entry_subject(host: Host, source: Source, entry: RawEntry, ctx: HostContext) -> Subject:
    label = f"{entry.name} ({display(entry.file, ctx)}, {entry.scope or source.scope})"
    if is_remote(entry.server):
        return Subject(host, label, State.REMOTE, findings=[info("HTTP server; not checked")])
    spec, errors = parse_server(entry.server, vscode_values=host.vscode_values)
    if spec is None:
        return Subject(host, label, findings=[fail(error) for error in errors])
    subject = Subject(host, label, effective=host.effective_env(spec, source, ctx))
    lookup = host.placeholder_env(ctx)
    command = resolve(spec.command, source.syntax, lookup, workspace=source.workspace, home=ctx.home)
    if command is None:
        subject.findings.append(unverified(f"command {spec.command} uses a placeholder this doctor cannot resolve"))
    subject.command = command
    subject.args = tuple(
        resolve(arg, source.syntax, lookup, workspace=source.workspace, home=ctx.home) or arg for arg in spec.args
    )
    return subject


def _count(entries: Sequence[object]) -> str:
    return f"{len(entries)} OpenProject entr{'y' if len(entries) == 1 else 'ies'}"


# ── Claude Code ─────────────────────────────────────────────────────────────────


@dataclass
class _ClaudeSettings:
    env_layers: list[tuple[Path, Mapping[str, str]]] = field(default_factory=list)
    notes: list[Finding] = field(default_factory=list)
    # From the settings files and the project entry: applies to `.mcp.json` servers only.
    disabled_mcpjson: set[str] = field(default_factory=set)
    # From the project entry in ~/.claude.json only (isServerDisabled): applies to every scope.
    disabled: set[str] = field(default_factory=set)


def _read_claude_settings(ctx: HostContext, files: _Files) -> _ClaudeSettings:
    """``env`` and ``disabledMcpjsonServers`` from Claude Code's settings, lowest precedence first."""
    result = _ClaudeSettings()
    paths = (
        ctx.home / ".claude" / "settings.json",
        ctx.cwd / ".claude" / "settings.json",
        ctx.cwd / ".claude" / "settings.local.json",
        ctx.system.claude_managed_settings,
    )
    for path in paths:
        config = files.read(path)
        if config is None:
            continue
        shown = display(path, ctx)
        if config.error or not isinstance(config.data, dict):
            result.notes.append(
                unverified(f"settings {shown} {config.error or 'is not an object'}; its env is not known")
            )
            continue
        env = config.data.get("env") or {}
        if not isinstance(env, dict):
            result.notes.append(
                unverified(f"settings {shown} has an `env` that is not an object; it is not applied here")
            )
            env = {}
        values = {}
        for key, value in env.items():
            if isinstance(value, str):
                values[key] = value
            else:
                result.notes.append(unverified(f"settings {shown}: `env.{key}` is not a string; not applied here"))
        result.env_layers.append((path, values))
        result.disabled_mcpjson |= _names(config.data, "disabledMcpjsonServers")
    return result


def _names(data: Mapping, key: str) -> set[str]:
    names = data.get(key)
    return {name for name in names if isinstance(name, str)} if isinstance(names, list) else set()


_CLAUDE_SCOPE_RANK = {"local": 2, "project": 1, "user": 0}


def _claude_code_subjects(ctx: HostContext, files: _Files, state_path: Path, project_path: Path) -> list[Subject]:
    settings = _read_claude_settings(ctx, files)
    host = ClaudeCodeHost(settings.env_layers, settings.notes)
    subjects: list[Subject] = []
    scoped: list[tuple[str, Subject, str]] = []

    state = files.read(state_path)
    if state is not None and (state.error or not isinstance(state.data, dict)):
        subjects += files.problem(host, state_path, state.error or "has no JSON object at the top level")
    elif state is not None:
        assert isinstance(state.data, dict)
        user = Source(state_path, "mcpServers", Syntax.CLAUDE_CODE, "user scope")
        scoped += [("user", s, n) for s, n in _scope_subjects(host, user, state, files, subjects)]
        keys = claude_project_keys(ctx.cwd)
        labels = ("worktree root", "main repository root") if len(keys) == 2 else ("project root",)
        checked = ", ".join(f"{key} ({label})" for key, label in zip(keys, labels, strict=True))
        files.overview.append(f"  - Claude Code local scope checked under: {checked}")
        projects = state.data.get("projects")
        for key in keys:
            found = claude_project(projects, key) if isinstance(projects, dict) else None
            if found is None:
                continue
            stored_key, project = found
            settings.disabled_mcpjson |= _names(project, "disabledMcpjsonServers")
            settings.disabled |= _names(project, "disabledMcpServers")
            local = Source(state_path, "mcpServers", Syntax.CLAUDE_CODE, f"local scope, projects[{stored_key}]")
            scoped_project = ConfigFile(state_path, data=project)
            scoped += [("local", s, n) for s, n in _scope_subjects(host, local, scoped_project, files, subjects)]

    mcp_json = files.read(project_path)
    if mcp_json is not None:
        project_source = Source(project_path, "mcpServers", Syntax.CLAUDE_CODE, "project scope")
        scoped += [("project", s, n) for s, n in _scope_subjects(host, project_source, mcp_json, files, subjects)]

    for scope, subject, name in scoped:
        if name in settings.disabled:
            subject.state = State.INACTIVE
            subject.state_reason = "disabled in Claude Code (disabledMcpServers)"
        elif scope == "project" and name in settings.disabled_mcpjson:
            subject.state = State.INACTIVE
            subject.state_reason = "disabled in Claude Code (disabledMcpjsonServers)"
    for scope, subject, name in scoped:
        if subject.state is not State.ACTIVE:
            continue
        stronger = [
            (_CLAUDE_SCOPE_RANK[other_scope], other.identity)
            for other_scope, other, other_name in scoped
            if other_name == name
            and other.state is not State.INACTIVE
            and _CLAUDE_SCOPE_RANK[other_scope] > _CLAUDE_SCOPE_RANK[scope]
        ]
        if stronger:
            subject.state = State.SHADOWED
            subject.state_reason = f"shadowed here by {max(stronger)[1]}"
    return subjects + [subject for _, subject, _ in scoped]


def claude_project(projects: dict[str, Any], key: PurePath) -> tuple[str, dict[str, Any]] | None:
    """The key and ``projects`` entry of ``~/.claude.json`` for a directory. On Windows Claude Code may key it
    with forward slashes, as ``git`` prints the path, or with the native backslashes."""
    for name in dict.fromkeys((str(key), key.as_posix())):
        project = projects.get(name)
        if isinstance(project, dict):
            return name, project
    return None


def _scope_subjects(
    host: ClaudeCodeHost, source: Source, config: ConfigFile, files: _Files, problems: list[Subject]
) -> list[tuple[Subject, str]]:
    if config.error:
        problems += files.problem(host, source.path, config.error)
        return []
    entries, problem = _openproject_entries(config, source)
    if problem:
        problems.append(Subject(host, f"({source.scope})", findings=[fail(f"{source.scope} {problem}")]))
        return []
    shown = display(source.path, files.ctx)
    files.overview.append(f"  - Claude Code ({source.scope}): {shown}, {_count(entries)}")
    if entries:
        files.with_entries.add(source.path)
    return [(_entry_subject(host, source, entry, files.ctx), entry.name) for entry in entries]
