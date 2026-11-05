"""Claude Code reviewer launch mode (M15.2).

Bare only when the reviewer's environment has ``ANTHROPIC_API_KEY`` or the user
settings bare mode reads define ``apiKeyHelper``. Otherwise explicit:
``--setting-sources user`` and ``--strict-mcp-config``, with no ``--mcp-config``,
so no repository hooks, project settings or MCP servers load, and the
subscription login is read. Flags are the ones in
``model-profiles/harness-captures/claude-code/help.txt``. A roster entry or a
profile ``access.launch_mode: bare`` forces bare; with neither credential that
is a refusal, and the key's value is never put in a message.

Workers (M15.36) take the same check: bare is forced by the same entry or profile setting and refused with
neither credential, before any worker state is written; otherwise a worker names its setting sources
explicitly (:data:`WORKER_FULL_FLAGS`) instead of relying on ``claude -p``'s default mode.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from specy_road.claude_config import claude_config_dir
from specy_road.orchestration_role_env import harness_env

API_KEY_ENV = "ANTHROPIC_API_KEY"
#: The refusal and the plan notices start with this.
AUTH_REFUSAL_PREFIX = "reviewer auth:"
FIXES = "export ANTHROPIC_API_KEY, configure apiKeyHelper, or let specy-road choose explicit mode"
BARE_NOTE = (
    "note: the reviewer runs with --bare (no repository hooks, MCP servers or CLAUDE.md), and bare mode "
    "never reads your subscription login: it needs ANTHROPIC_API_KEY (or an apiKeyHelper)"
)
EXPLICIT_NOTE = (
    "note: the reviewer runs in explicit mode (--setting-sources user --strict-mcp-config, no --mcp-config), "
    "so no repository hooks, project settings or MCP servers load, and the subscription login is read. "
    "Bare mode never reads that login: it needs ANTHROPIC_API_KEY (or an apiKeyHelper)"
)


#: A worker's non-bare mode, stated rather than left to ``claude -p``'s default (which may become ``--bare``):
#: every setting source an interactive session loads, so its hooks, project settings and login are the same.
WORKER_FULL_FLAGS = ("--setting-sources", "user,project,local")
WORKER_FIXES = "export ANTHROPIC_API_KEY, configure apiKeyHelper, or drop launch_mode: bare to use the subscription login"


def reviewer_environment() -> dict[str, str]:
    """The environment a Claude Code reviewer process is given (role and avoid-list included)."""
    return harness_env(os.environ, "reviewer", harness="claude-code")


def worker_environment() -> dict[str, str]:
    """The environment a Claude Code executor (worker) process is given."""
    return harness_env(os.environ, "executor", harness="claude-code")


def user_settings_path(env: Mapping[str, str]) -> Path:
    """``<config>/settings.json``: the user settings bare mode's ``apiKeyHelper`` is read from.

    ``CLAUDE_CONFIG_DIR`` in ``env`` selects the account, else ``HOME/.claude``, else the process home.
    Both values are taken literally, as :func:`claude_config_dir` and the launched environment do.
    """
    configured = env.get("CLAUDE_CONFIG_DIR")
    if configured:
        return Path(configured) / "settings.json"
    home = env.get("HOME")
    if home:
        return Path(home) / ".claude" / "settings.json"
    return claude_config_dir() / "settings.json"


def load_user_settings(env: Mapping[str, str]) -> dict[str, Any]:
    """Those user settings, or ``{}`` when the file is missing or not a JSON object. Never logged."""
    try:
        data = json.loads(user_settings_path(env).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def has_api_key(env: Mapping[str, str]) -> bool:
    """True when ``ANTHROPIC_API_KEY`` is set to something other than whitespace. The value is not returned."""
    return bool((env.get(API_KEY_ENV) or "").strip())


def has_api_key_helper(user_settings: Mapping[str, Any] | None) -> bool:
    """True when user settings define a non-empty ``apiKeyHelper`` string. The command is not returned."""
    if not isinstance(user_settings, Mapping):
        return False
    helper = user_settings.get("apiKeyHelper")
    return isinstance(helper, str) and bool(helper.strip())


def bare_settings_argv(env: Mapping[str, str] | None = None) -> list[str]:
    """``--settings <path>`` when bare auth is an ``apiKeyHelper`` and not a key. The path only.

    ``--settings`` also accepts a JSON string (help.txt). That string would put the helper command on the
    argv and in the log, so the launch passes the user-settings file bare mode reads the helper from.
    """
    env = reviewer_environment() if env is None else env
    if has_api_key(env) or not has_api_key_helper(load_user_settings(env)):
        return []
    return ["--settings", str(user_settings_path(env))]


def claude_reviewer_mode(env: Mapping[str, str], user_settings: Mapping[str, Any] | None) -> str:
    """``bare`` only with a key or ``apiKeyHelper``; otherwise ``explicit``."""
    if has_api_key(env) or has_api_key_helper(user_settings):
        return "bare"
    return "explicit"


def auth_problem(mode: str, env: Mapping[str, str], settings: Mapping[str, Any] | None) -> str | None:
    """Why forced ``bare`` cannot launch, or ``None``. The key's value is never included."""
    if mode != "bare" or has_api_key(env) or has_api_key_helper(settings):
        return None
    return f"{AUTH_REFUSAL_PREFIX} bare mode was forced and no ANTHROPIC_API_KEY or apiKeyHelper is available: {FIXES}"


def forces_bare(entry: Mapping[str, Any], profile_mode: str | None) -> bool:
    """A roster ``launch_mode: bare`` or the profile flag ``access.launch_mode: bare``."""
    return entry.get("launch_mode") == "bare" or profile_mode == "bare"


def claude_launch_decision(entry: Mapping[str, Any] | None, profile_mode: str | None) -> tuple[str, str | None]:
    """``(mode, refusal)`` for one claude-code reviewer. Refusal is set only when bare is forced and unauthenticated."""
    env = reviewer_environment()
    settings = load_user_settings(env)
    if forces_bare(entry or {}, profile_mode):
        return "bare", auth_problem("bare", env, settings)
    return claude_reviewer_mode(env, settings), None


def claude_default_reviewer(entry: Mapping[str, Any], profile_mode: str | None) -> tuple[str, str | None, str]:
    """``(mode, refusal, note)`` for a default claude-code reviewer (no ``channels.cli``)."""
    mode, problem = claude_launch_decision(entry, profile_mode)
    return mode, problem, launch_note(mode)


def launch_note(mode: str) -> str:
    """The bare-mode and subscription-login note ``review delegate`` and ``prompt`` both print."""
    return BARE_NOTE if mode == "bare" else EXPLICIT_NOTE


def claude_reviewer_auth_notices(rows: list[tuple[str, Mapping[str, Any], str | None]]) -> list[str]:
    """One ``reviewer auth:`` line per claude-code reviewer entry that forces bare with no key.

    ``rows`` is ``(id, entry, profile launch_mode or None)``. An entry with ``channels.cli`` runs that
    command, not this launcher, so it is not noticed here. Nothing is returned when a key or helper exists.
    """
    env = reviewer_environment()
    settings = load_user_settings(env)
    if auth_problem("bare", env, settings) is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for eid, entry, profile_mode in rows:
        if eid in seen or entry.get("harness") != "claude-code" or "reviewer" not in (entry.get("roles") or []):
            continue
        channels = entry.get("channels") or {}
        if (isinstance(channels, dict) and channels.get("cli")) or not forces_bare(entry, profile_mode):
            continue
        seen.add(eid)
        out.append(f"{AUTH_REFUSAL_PREFIX} {eid} forces bare and has no ANTHROPIC_API_KEY or apiKeyHelper: {FIXES}")
    return out


def claude_worker_refusal(entry: Mapping[str, Any], profile_mode: str | None) -> str | None:
    """One line refusing a claude-code worker launch or resume that forces bare with no key or helper, or ``None``."""
    if not forces_bare(entry, profile_mode):
        return None
    env = worker_environment()
    if has_api_key(env) or has_api_key_helper(load_user_settings(env)):
        return None
    return (f"worker auth: {entry.get('id')} forces bare mode and no ANTHROPIC_API_KEY or apiKeyHelper is "
            f"available, so nothing was launched: {WORKER_FIXES}")
