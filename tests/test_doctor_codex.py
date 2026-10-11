"""Codex in the doctor: effective entries from ``codex mcp list``, fragments from readable files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from _doctor_test_helpers import BASE_URL, TOKEN, VALID_ENV, FakeCodex, Sandbox, listed, listing

from openproject_ce_mcp.doctor.checks import evaluate
from openproject_ce_mcp.doctor.codex import (
    CUSTOM_CA_ENV_KEYS,
    DEFAULT_ENV_VARS_UNIX,
    NON_INHERITABLE_ENV_VARS,
    WINDOWS_CORE_ENV_VARS,
    CodexCli,
    CodexHost,
    CodexServer,
    EnvVarRef,
    ProcessResult,
    parse_listing,
    project_config_files,
)
from openproject_ce_mcp.doctor.hosts import Subject
from openproject_ce_mcp.doctor.run import EXIT_FAILURE, EXIT_SUCCESS

SENTINEL = "sentinel-token-546"
THIS_DIR = "Codex openproject (this directory)"
USER_LEVEL = "Codex openproject (user level)"
BOTH = "Codex openproject (this directory and user level)"

# Recorded from `codex mcp list --json` (codex-cli 0.161.0) against a temporary
# CODEX_HOME with fake values.
RECORDED_0_161_0 = """[
  {
    "name": "openproject",
    "enabled": true,
    "disabled_reason": null,
    "transport": {
      "type": "stdio",
      "command": "openproject-ce-mcp",
      "args": [
        "--flag"
      ],
      "env": {
        "OPENPROJECT_BASE_URL": "https://op.example.invalid"
      },
      "env_vars": [
        "OPENPROJECT_API_TOKEN",
        {
          "name": "OPENPROJECT_TIMEOUT",
          "source": "local"
        }
      ],
      "cwd": null
    },
    "startup_timeout_sec": null,
    "tool_timeout_sec": null,
    "auth_status": "unsupported"
  },
  {
    "name": "other",
    "enabled": false,
    "disabled_reason": null,
    "transport": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "openproject-ce-mcp@0.4.2"
      ],
      "env": null,
      "env_vars": [],
      "cwd": null
    },
    "startup_timeout_sec": null,
    "tool_timeout_sec": null,
    "auth_status": "unsupported"
  }
]
"""


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    return Sandbox(tmp_path, monkeypatch)


def _user_config(box: Sandbox, text: str) -> None:
    box.write(box.codex_config, text)


def test_codex_lists_are_pinned_to_the_codex_sources():
    assert DEFAULT_ENV_VARS_UNIX == (
        "HOME", "LOGNAME", "PATH", "SHELL", "USER", "__CF_USER_TEXT_ENCODING", "LANG", "LC_ALL", "TERM", "TMPDIR", "TZ",
    )  # fmt: skip
    assert WINDOWS_CORE_ENV_VARS == (
        "PATH", "PATHEXT", "SHELL", "COMSPEC", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "USERNAME", "USERDOMAIN",
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "PROGRAMDATA",
        "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "TMPDIR", "POWERSHELL", "PWSH",
    )  # fmt: skip
    assert CUSTOM_CA_ENV_KEYS == (
        "CODEX_CA_CERTIFICATE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
        "GIT_SSL_CAINFO", "CARGO_HTTP_CAINFO", "PIP_CERT", "BUNDLE_SSL_CA_CERT", "npm_config_cafile",
        "NPM_CONFIG_CAFILE",
    )  # fmt: skip
    assert NON_INHERITABLE_ENV_VARS == (
        "CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN", "NODE_REPL_AUTH_TOKEN", "CODEX_GUARDIAN_DECISIONS_API_KEY",
        "OPENAI_FEDERATION_RULE_ID", "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT",
    )  # fmt: skip


def test_recorded_listing_parses():
    servers = parse_listing(RECORDED_0_161_0)

    assert servers[0] == CodexServer(
        "openproject",
        True,
        None,
        "openproject-ce-mcp",
        ("--flag",),
        (("OPENPROJECT_BASE_URL", "https://op.example.invalid"),),
        (EnvVarRef("OPENPROJECT_API_TOKEN"), EnvVarRef("OPENPROJECT_TIMEOUT", "local")),
    )
    assert servers[1].enabled is False and servers[1].env == ()


# ── effective environment ───────────────────────────────────────────────────────


def test_codex_environment_base_set_env_vars_ca_keys_env_and_non_inheritable(box, monkeypatch):
    ctx = box.ctx("darwin")
    ctx.shell_env.clear()
    ctx.shell_env.update(
        {
            "HOME": "/h",
            "TERM": "xterm",
            "OTHER": "not forwarded",
            "OPENPROJECT_TIMEOUT": "9",
            "SSL_CERT_FILE": "certs/ca.pem",
            "NODE_EXTRA_CA_CERTS": "/abs/node.pem",
            "NODE_REPL_AUTH_TOKEN": "secret",
            "OPENPROJECT_MAX_RESULTS": "70",
        }
    )
    server = CodexServer(
        "openproject",
        True,
        None,
        "openproject-ce-mcp",
        env=(("OPENPROJECT_MAX_RESULTS", "80"), ("NODE_REPL_AUTH_TOKEN", "x"), ("ssl_cert_file", "/entry.pem")),
        env_vars=(
            EnvVarRef("OPENPROJECT_TIMEOUT"),
            EnvVarRef("OPENPROJECT_MAX_RESULTS"),
            EnvVarRef("NODE_REPL_AUTH_TOKEN"),
        ),
    )

    effective = CodexHost().codex_env(server, ctx)
    env = effective.env

    assert env.get("HOME") == "/h" and env.get("TERM") == "xterm"
    assert "OTHER" not in env
    assert env.get("OPENPROJECT_TIMEOUT") == "9"
    assert env.get("OPENPROJECT_MAX_RESULTS") == "80"
    assert "NODE_REPL_AUTH_TOKEN" not in env
    assert env.get("NODE_EXTRA_CA_CERTS") == "/abs/node.pem"
    assert "SSL_CERT_FILE" not in env and env.get("ssl_cert_file") == "/entry.pem"
    assert effective.assumed_local is True


@pytest.mark.parametrize(("shell_value", "level"), [(None, "WARN"), ("20", "FAIL")])
def test_codex_contradiction_with_an_env_vars_value_this_shell_lacks_is_not_a_fail(box, shell_value, level):
    ctx = box.ctx("linux")
    ctx.shell_env.pop("OPENPROJECT_MAX_RESULTS", None)
    if shell_value is not None:
        ctx.shell_env["OPENPROJECT_MAX_RESULTS"] = shell_value
    server = CodexServer(
        "openproject",
        True,
        None,
        "cmd",
        env=(*VALID_ENV.items(), ("OPENPROJECT_MAX_PAGE_SIZE", "200")),
        env_vars=(EnvVarRef("OPENPROJECT_MAX_RESULTS"),),
    )
    host = CodexHost()

    evaluation = evaluate(Subject(host, "x", effective=host.codex_env(server, ctx)), ctx)

    (finding,) = [f for f in evaluation.findings if "must not exceed OPENPROJECT_MAX_RESULTS" in f.text]
    assert finding.level.value == level


def test_codex_ca_keys_are_forwarded_as_absolute_paths(box):
    ctx = box.ctx("linux")
    ctx.shell_env.clear()
    ctx.shell_env["REQUESTS_CA_BUNDLE"] = "certs/ca.pem"

    env = CodexHost().codex_env(CodexServer("openproject", True, None, "x"), ctx).env

    assert env.get("REQUESTS_CA_BUNDLE") == str(box.cwd / "certs" / "ca.pem")


def test_views_that_differ_only_in_env_order_are_reported_once(box, capsys):
    env = {**VALID_ENV, "OPENPROJECT_TIMEOUT": "30"}
    codex = FakeCodex(listing(listed(env=env)), listing(listed(env=dict(reversed(env.items())))))

    run = box.run(capsys, codex=codex)

    assert run.lines(BOTH)
    assert not run.lines(THIS_DIR) and not run.lines(USER_LEVEL)
    assert len(box.probe.calls) == 1


def test_token_via_env(box, capsys):
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_SUCCESS
    assert any("API: connected" in line for line in run.lines(BOTH))
    assert box.probe.calls[0].get("OPENPROJECT_API_TOKEN") == TOKEN


def test_token_via_env_vars_from_the_shell(box, capsys, monkeypatch):
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", TOKEN)
    codex = FakeCodex(listing(listed(env={"OPENPROJECT_BASE_URL": BASE_URL}, env_vars=["OPENPROJECT_API_TOKEN"])))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_SUCCESS
    assert box.probe.calls[0].get("OPENPROJECT_API_TOKEN") == TOKEN


def test_env_vars_token_absent_from_the_shell_warns_without_a_probe(box, capsys):
    codex = FakeCodex(listing(listed(env={"OPENPROJECT_BASE_URL": BASE_URL}, env_vars=["OPENPROJECT_API_TOKEN"])))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_SUCCESS
    assert any("Codex passes it from its own environment (env_vars)" in line for line in run.lines(BOTH))
    assert box.probe.calls == []


def test_token_in_neither_env_nor_env_vars_fails_even_if_the_shell_has_it(box, capsys, monkeypatch):
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", TOKEN)
    codex = FakeCodex(listing(listed(env={"OPENPROJECT_BASE_URL": BASE_URL})))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_FAILURE
    assert any("OPENPROJECT_API_TOKEN is not set" in line for line in run.lines(BOTH) if line.startswith("[FAIL]"))


# ── layers and views ────────────────────────────────────────────────────────────


def test_project_fragment_with_one_env_key_is_not_a_failure(box, capsys):
    _user_config(
        box,
        f'[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\n[mcp_servers.openproject.env]\nOPENPROJECT_BASE_URL = "{BASE_URL}"\nOPENPROJECT_API_TOKEN = "{TOKEN}"\n',
    )
    box.write(box.cwd / ".codex" / "config.toml", '[mcp_servers.openproject.env]\nOPENPROJECT_TIMEOUT = "30"\n')
    merged = listed(env={**VALID_ENV, "OPENPROJECT_TIMEOUT": "30"})
    codex = FakeCodex(listing(merged), listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_SUCCESS
    assert "project layer" not in run.out.split("platform minimum", 1)[1]
    assert {call.get("OPENPROJECT_TIMEOUT") for call in box.probe.calls} == {"5"}
    assert len(box.probe.calls) == 1


def test_broken_user_entry_hidden_by_a_project_override_is_found_in_the_user_level_view(box, capsys):
    codex = FakeCodex(
        listing(listed(env={**VALID_ENV, "OPENPROJECT_TIMEOUT": "30"})),
        listing(listed(env={**VALID_ENV, "OPENPROJECT_TIMEOUT": "abc"})),
    )

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_FAILURE
    assert "FAIL" not in run.levels(THIS_DIR)
    assert any(
        "OPENPROJECT_TIMEOUT must be a number" in line for line in run.lines(USER_LEVEL) if line.startswith("[FAIL]")
    )


def test_user_level_view_runs_in_a_fresh_empty_directory_without_project_markers(box, capsys, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(box.home / "codex-home"))
    (box.home / "codex-home").mkdir()
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    box.run(capsys, codex=codex)

    (this_args, this_cwd, this_env, _), (user_args, user_cwd, user_env, user_listing) = codex.calls
    assert this_args == ["mcp", "list", "--json"] and this_cwd == box.cwd
    assert user_args == ["mcp", "list", "--json", "-c", "project_root_markers=[]"]
    assert user_cwd != box.cwd and user_listing == [] and not user_cwd.exists()
    assert this_env.get("CODEX_HOME") == user_env.get("CODEX_HOME") == str(box.home / "codex-home")


def test_ancestor_of_the_temporary_directory_with_codex_config_makes_the_user_view_unverifiable(
    box, capsys, monkeypatch
):
    parent = box.root / "tmpbase"
    box.write(parent / ".codex" / "config.toml", "")
    (parent / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(parent / "tmp"))
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert [call[0] for call in codex.calls] == [["mcp", "list", "--json"]]
    assert any("user-level view is not verified" in line for line in run.lines("Codex (user level)"))
    assert run.exit_code == EXIT_SUCCESS and "could not be fully verified" in run.out


def test_unreadable_ancestor_makes_the_user_view_unverifiable(box, capsys, monkeypatch):
    parent = box.root / "tmpbase"
    (parent / ".codex").mkdir(parents=True)
    (parent / "tmp").mkdir()
    (parent / ".codex").chmod(0)
    monkeypatch.setattr(tempfile, "tempdir", str(parent / "tmp"))
    codex = FakeCodex(listing(listed(env=VALID_ENV)))
    try:
        run = box.run(capsys, codex=codex)
    finally:
        (parent / ".codex").chmod(0o755)

    assert len(codex.calls) == 1
    assert run.lines("Codex (user level)")


def test_project_files_stop_at_the_project_root(tmp_path):
    outer = tmp_path / "outer"
    repo = outer / "repo"
    sub = repo / "sub"
    for directory in (outer / ".codex", repo / ".codex", sub / ".codex", repo / ".git"):
        directory.mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    files = project_config_files(sub, [".git"], tmp_path / "codex-home")

    assert files == [repo / ".codex" / "config.toml", sub / ".codex" / "config.toml"]


def test_without_a_marker_only_the_working_directory_is_read(tmp_path):
    cwd = tmp_path / "a" / "b"
    (tmp_path / "a" / ".codex").mkdir(parents=True)
    (cwd / ".codex").mkdir(parents=True)

    assert project_config_files(cwd, [".git"], tmp_path / "home") == [cwd / ".codex" / "config.toml"]


def test_git_directory_without_head_is_no_marker_and_codex_home_is_no_project_folder(tmp_path):
    root = tmp_path / "r"
    cwd = root / "w"
    (root / ".git").mkdir(parents=True)
    (cwd / ".codex").mkdir(parents=True)

    assert project_config_files(cwd, [".git"], cwd / ".codex") == []


def test_ancestor_codex_config_above_the_project_root_is_not_read(box, capsys):
    (box.cwd / ".git").mkdir()
    (box.cwd / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    box.write(box.root / ".codex" / "config.toml", '[mcp_servers.openproject]\nenv_vars = "broken"\n')
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_SUCCESS
    assert "env_vars" not in run.out


def test_requirements_disabled_server_is_inactive_with_its_reason(box, capsys):
    reason = "requirements (/etc/codex/requirements.toml)"
    codex = FakeCodex(
        listing(listed(env={**VALID_ENV, "OPENPROJECT_API_TOKEN": SENTINEL}, enabled=False, disabled_reason=reason))
    )

    run = box.run(capsys, codex=codex)

    assert any(f"inactive (disabled: {reason})" in line for line in run.lines(BOTH))
    assert run.exit_code == EXIT_SUCCESS and "no active OpenProject entry" in run.out
    assert SENTINEL not in run.out
    assert box.probe.calls == []


def test_environment_id_other_than_local_may_run_remotely(box, capsys):
    _user_config(box, '[mcp_servers.openproject]\nenvironment_id = "devbox"\n')
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert any("may run remotely" in line for line in run.lines(BOTH))
    assert box.probe.calls == []
    assert run.exit_code == EXIT_SUCCESS and "no active OpenProject entry" in run.out


def test_user_devbox_is_not_re_enabled_by_a_project_local(box, capsys):
    _user_config(box, '[mcp_servers.openproject]\nenvironment_id = "devbox"\n')
    box.write(box.cwd / ".codex" / "config.toml", '[mcp_servers.openproject]\nenvironment_id = "local"\n')
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert any("may run remotely" in line for line in run.lines(BOTH))
    assert box.probe.calls == []


def test_project_devbox_with_a_user_local_is_remote_here_and_probed_at_user_level(box, capsys):
    _user_config(box, '[mcp_servers.openproject]\nenvironment_id = "local"\n')
    box.write(box.cwd / ".codex" / "config.toml", '[mcp_servers.openproject]\nenvironment_id = "devbox"\n')
    codex = FakeCodex(listing(listed(env=VALID_ENV)))

    run = box.run(capsys, codex=codex)

    assert any("may run remotely" in line for line in run.lines(THIS_DIR))
    assert any("API: connected" in line for line in run.lines(USER_LEVEL))
    assert len(box.probe.calls) == 1


def test_remote_source_env_var_on_a_local_server_warns(box, capsys):
    codex = FakeCodex(listing(listed(env=VALID_ENV, env_vars=[{"name": "OPENPROJECT_TIMEOUT", "source": "remote"}])))

    run = box.run(capsys, codex=codex)

    assert any(
        'uses source = "remote": Codex refuses to start this server unless a managed layer sets `environment_id`'
        in line
        for line in run.lines(BOTH)
        if line.startswith("[WARN]")
    )


def test_assumption_heads_the_entry_and_covers_a_settings_failure(box, capsys):
    codex = FakeCodex(listing(listed(env={**VALID_ENV, "OPENPROJECT_TIMEOUT": "abc"})))

    run = box.run(capsys, codex=codex)

    lines = run.lines(BOTH)
    assert lines[0] == (
        f"[INFO] {BOTH}: assuming Codex runs it locally; managed configuration this doctor cannot read could change that"
    )
    assert any(line.startswith("[FAIL]") and "OPENPROJECT_TIMEOUT" in line for line in lines[1:])
    assert run.exit_code == EXIT_FAILURE


# ── running Codex ───────────────────────────────────────────────────────────────


def test_configuration_load_error_is_the_fixed_failure(box, capsys):
    stderr = f'Error: failed to load bootstrap configuration\n\nCaused by:\n    OPENPROJECT_API_TOKEN = "{SENTINEL}"\n'
    codex = FakeCodex(ProcessResult(1, "", stderr))

    run = box.run(capsys, codex=codex)

    assert run.exit_code == EXIT_FAILURE
    assert "Codex could not load its configuration; run `codex mcp list` to see why" in run.out
    assert SENTINEL not in run.out


@pytest.mark.parametrize(
    "result",
    [ProcessResult(1, "", f"Error: auth store {SENTINEL}"), ProcessResult(2, "", "error: unexpected argument")],
)
def test_other_codex_failures_are_a_fixed_warning(box, capsys, result):
    run = box.run(capsys, codex=FakeCodex(result))

    assert run.exit_code == EXIT_SUCCESS
    assert f"`codex mcp list` failed with exit status {result.returncode}" in run.out
    assert "could not be fully verified" in run.out
    assert SENTINEL not in run.out


@pytest.mark.parametrize(
    "result",
    [
        ProcessResult(None, f'[{{"name": "openproject", "transport": {{"env": {{"T": "{SENTINEL}"', ""),
        ProcessResult(0, f'{{"unexpected": "{SENTINEL}"}}', ""),
        ProcessResult(0, f"not json {SENTINEL}", ""),
    ],
)
def test_timeout_and_unknown_shape_are_a_fixed_warning(box, capsys, result):
    _user_config(
        box,
        f'[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\n[mcp_servers.openproject.env]\nOPENPROJECT_API_TOKEN = "{SENTINEL}"\n',
    )

    run = box.run(capsys, codex=FakeCodex(result))

    assert run.exit_code == EXIT_SUCCESS
    assert "[FAIL]" not in run.out
    assert SENTINEL not in run.out
    assert "could not be fully verified" in run.out


def test_codex_home_that_is_not_a_directory_fails_before_codex_runs(box, capsys, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(box.root / "missing"))
    codex = FakeCodex(listing())

    run = box.run(capsys, codex=codex)

    assert codex.calls == []
    assert run.exit_code == EXIT_FAILURE
    assert "CODEX_HOME is set to" in run.out and "which is not a directory" in run.out


def test_codex_home_is_where_the_user_layer_is_read(box, capsys, monkeypatch):
    home = box.root / "codex-home"
    box.write(home / "config.toml", '[mcp_servers.openproject]\nenv_vars = [{ name = "X", source = "bogus" }]\n')
    monkeypatch.setenv("CODEX_HOME", str(home))

    run = box.run(capsys, codex=CodexCli(None))

    assert "codex-home/config.toml, user layer" in run.out


def test_malformed_env_vars_in_a_readable_file_fails(box, capsys):
    _user_config(
        box,
        '[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\nenv_vars = [{ name = "X", source = "bogus" }]\n',
    )

    run = box.run(capsys, codex=CodexCli(None))

    assert run.exit_code == EXIT_FAILURE
    assert any("`env_vars` must list names" in line for line in run.out.splitlines() if line.startswith("[FAIL]"))


def test_invalid_value_in_a_user_fragment_fails_but_a_cross_value_rule_does_not(box, capsys):
    _user_config(
        box, '[mcp_servers.openproject.env]\nOPENPROJECT_VERIFY_SSL = "maybe"\nOPENPROJECT_DEFAULT_PAGE_SIZE = "60"\n'
    )

    run = box.run(capsys, codex=CodexCli(None))

    fails = [line for line in run.out.splitlines() if line.startswith("[FAIL]")]
    assert any("OPENPROJECT_VERIFY_SSL must be a boolean value" in line for line in fails)
    assert not any("DEFAULT_PAGE_SIZE" in line for line in fails)


def test_contradiction_set_entirely_in_one_applied_fragment_fails(box, capsys):
    _user_config(
        box,
        '[mcp_servers.openproject.env]\nOPENPROJECT_RETRY_BASE_DELAY = "90"\n'
        'OPENPROJECT_DEFAULT_PAGE_SIZE = "60"\nOPENPROJECT_MAX_PAGE_SIZE = "50"\n',
    )

    run = box.run(capsys, codex=CodexCli(None))

    fails = [line for line in run.out.splitlines() if line.startswith("[FAIL]")]
    assert any("OPENPROJECT_DEFAULT_PAGE_SIZE must not exceed OPENPROJECT_MAX_PAGE_SIZE" in line for line in fails)
    assert not any("RETRY" in line for line in fails)
    assert run.exit_code == EXIT_FAILURE


def test_cross_value_rule_alone_in_a_fragment_is_not_reported(box, capsys):
    _user_config(box, '[mcp_servers.openproject.env]\nOPENPROJECT_DEFAULT_PAGE_SIZE = "60"\n')

    run = box.run(capsys, codex=CodexCli(None))

    assert "[FAIL]" not in run.out


def test_invalid_value_in_a_project_fragment_warns_unless_it_reaches_the_effective_entry(box, capsys):
    box.write(box.cwd / ".codex" / "config.toml", '[mcp_servers.openproject.env]\nOPENPROJECT_TIMEOUT = "abc"\n')

    untrusted = box.run(capsys, codex=FakeCodex(listing(listed(env=VALID_ENV))))
    trusted = box.run(
        capsys,
        codex=FakeCodex(
            listing(listed(env={**VALID_ENV, "OPENPROJECT_TIMEOUT": "abc"})), listing(listed(env=VALID_ENV))
        ),
    )

    fragment = "Codex openproject (.codex/config.toml, project layer)"
    assert untrusted.levels(fragment) == {"WARN"} and untrusted.exit_code == EXIT_SUCCESS
    assert trusted.levels(fragment) == {"FAIL"}


def test_codex_not_found_reports_the_entry_as_unverifiable(box, capsys):
    _user_config(
        box,
        f'[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\n[mcp_servers.openproject.env]\nOPENPROJECT_BASE_URL = "{BASE_URL}"\n',
    )

    run = box.run(capsys, codex=CodexCli(None))

    assert any("Codex CLI not found" in line for line in run.lines("Codex openproject"))
    assert run.exit_code == EXIT_SUCCESS


def test_codex_without_openproject_entries_leaves_the_fallback(box, capsys, monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", BASE_URL)
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", TOKEN)
    codex = FakeCodex(listing(listed("github", command="github-mcp")))

    run = box.run(capsys, codex=codex)

    assert any("API: connected" in line for line in run.lines("process environment"))


def test_plugin_server_detected_by_command_counts_as_openproject(box, capsys):
    codex = FakeCodex(listing(listed("tracker", command="uvx", args=["openproject-ce-mcp@0.4.2"], env=VALID_ENV)))
    box.executable("uvx")

    run = box.run(capsys, codex=codex)

    assert any(
        "uvx runs openproject-ce-mcp@0.4.2" in line
        for line in run.lines("Codex tracker (this directory and user level)")
    )


def test_http_server_is_reported_and_skipped(box, capsys):
    server = listed()
    server["transport"] = {"type": "streamable_http", "url": "https://x.invalid", "bearer_token_env_var": None}
    run = box.run(capsys, codex=FakeCodex(listing(server)))

    assert any("HTTP server; not checked" in line for line in run.lines(BOTH))


def test_runtime_flags_are_named_once_as_not_covered(box, capsys):
    run = box.run(capsys, codex=FakeCodex(listing(listed(env=VALID_ENV))))

    assert run.out.count("--config and --profile flags of a particular Codex launch are not covered") == 1


def test_sentinel_token_in_stdout_never_reaches_the_output(box, capsys):
    codex = FakeCodex(listing(listed(env={**VALID_ENV, "OPENPROJECT_API_TOKEN": SENTINEL})))

    run = box.run(capsys, codex=codex)

    assert box.probe.calls[0].get("OPENPROJECT_API_TOKEN") == SENTINEL
    assert SENTINEL not in run.out


# ── the real binary ─────────────────────────────────────────────────────────────


def _real_codex() -> str:
    import shutil

    path = shutil.which("codex")
    if path is None:
        pytest.skip("codex is not installed")
    return path


@pytest.mark.integration
def test_real_codex_user_level_view_does_not_read_a_marked_ancestor(tmp_path):
    codex = _real_codex()
    home, codex_home, repo = tmp_path / "home", tmp_path / "codex-home", tmp_path / "repo"
    for directory in (home, codex_home, repo / ".git", repo / ".codex", repo / "empty"):
        directory.mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (repo / ".codex" / "config.toml").write_text('[mcp_servers.leak]\ncommand = "leak"\n')
    (codex_home / "config.toml").write_text(
        f'[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\n[mcp_servers.openproject.env]\n'
        f'OPENPROJECT_API_TOKEN = "{SENTINEL}"\n'
        f'[projects."{repo}"]\ntrust_level = "trusted"\n'
    )
    env = {"HOME": str(home), "CODEX_HOME": str(codex_home), "PATH": os.environ.get("PATH", "")}
    cli = CodexCli(codex)

    marked = cli.run(["mcp", "list", "--json"], repo / "empty", env)
    user_level = cli.run(["mcp", "list", "--json", "-c", "project_root_markers=[]"], repo / "empty", env)

    assert marked.returncode == 0 and user_level.returncode == 0
    assert {s.name for s in parse_listing(marked.stdout)} == {"leak", "openproject"}
    servers = parse_listing(user_level.stdout)
    assert [s.name for s in servers] == ["openproject"]
    assert dict(servers[0].env)["OPENPROJECT_API_TOKEN"] == SENTINEL
    assert json.loads(user_level.stdout)[0]["transport"]["type"] == "stdio"


def test_unlisted_project_fragment_is_inactive_not_the_fallback(box, capsys, monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", BASE_URL)
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", TOKEN)
    box.write(box.cwd / ".codex" / "config.toml", '[mcp_servers.openproject]\ncommand = "openproject-ce-mcp"\n')

    run = box.run(capsys, codex=FakeCodex(listing()))

    assert any("inactive (not loaded by Codex here" in line for line in run.lines("Codex openproject"))
    assert "checking the process environment instead" not in run.out
    assert "no active OpenProject entry" in run.out
    assert box.probe.calls == []


def test_codex_and_claude_code_entries_with_equal_values_are_checked_separately(box, capsys, monkeypatch):
    from openproject_ce_mcp.doctor import checks

    previews = []
    original = checks.tool_names
    monkeypatch.setattr(checks, "tool_names", lambda settings: previews.append(settings) or original(settings))
    box.write(box.claude_state, {"mcpServers": {"openproject": {"command": "openproject-ce-mcp", "env": VALID_ENV}}})

    run = box.run(capsys, codex=FakeCodex(listing(listed(env=VALID_ENV))))

    assert run.exit_code == EXIT_SUCCESS
    assert len(box.probe.calls) == 2
    assert len(previews) == 2


@pytest.mark.skipif(os.name == "nt", reason="the POSIX process-group path")
def test_timeout_kills_the_whole_process_tree(tmp_path):
    import signal
    import time

    pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "codex"
    script.write_text(f"#!/bin/sh\nsleep 60 &\necho $! > {pid_file}\nwait\n")
    script.chmod(0o755)
    started = time.monotonic()

    result = CodexCli(str(script)).run(["mcp", "list", "--json"], tmp_path, dict(os.environ), timeout=1.0)

    assert result == ProcessResult(None, "", "")
    assert time.monotonic() - started < 10
    grandchild = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(grandchild, signal.SIGKILL)
        pytest.fail("the grandchild survived the timeout")
