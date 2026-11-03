"""Harness hook adapters for ``specy-road orchestration guard`` (M8.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from specy_road.tool_call_guard_adapters import _bash_command, _cursor_command, _string_command


@dataclass(frozen=True)
class OrchestrationAdapter:
    name: str
    extract: Any
    on_allow: Any
    on_deny: Any
    config_executor: str
    config_reviewer: str
    notes: str


def _claude_hook(role: str) -> str:
    return (
        f'SPECY_ROAD_ORCHESTRATION_ROLE={role} specy-road orchestration guard --format claude-code'
    )


_CLAUDE_JSON = """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "%s", "timeout": 30, "onFailure": "block"}
        ]
      }
    ]
  }
}"""

_CLAUDE_EXEC = OrchestrationAdapter(
    "claude-code",
    _bash_command,
    lambda _note: (None, None, 0),
    lambda reason: (None, reason, 2),
    _CLAUDE_JSON % _claude_hook("executor"),
    _CLAUDE_JSON % _claude_hook("reviewer"),
    "Merge into .claude/settings.json (or settings.local.json). Exit 2 blocks; exit 1 does not. "
    "onFailure block fails closed on timeout or crash. Hooks run under claude -p.",
)

_CODEX_HOOK = 'SPECY_ROAD_ORCHESTRATION_ROLE=%s specy-road orchestration guard --format codex'

_CODEX_JSON = """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "%s", "timeout": 30,
           "statusMessage": "specy-road orchestration guard"}
        ]
      }
    ]
  }
}"""

_CODEX = OrchestrationAdapter(
    "codex",
    _bash_command,
    lambda _note: (None, None, 0),
    lambda reason: (None, reason, 2),
    _CODEX_JSON % (_CODEX_HOOK % "executor"),
    _CODEX_JSON % (_CODEX_HOOK % "reviewer"),
    "Put in .codex/hooks.json. Project hooks load only when .codex/ is trusted, or run once with "
    "--dangerously-bypass-hook-trust for specy-road's own hook files. Exit 2 denies.",
)

_CURSOR_JSON = """{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {"command": "%s", "timeout": 30, "failClosed": true, "matcher": ""}
    ]
  }
}"""

_CURSOR = OrchestrationAdapter(
    "cursor",
    _cursor_command,
    lambda _note: (json.dumps({"permission": "allow"}), None, 0),
    lambda reason: (
        json.dumps(
            {
                "permission": "deny",
                "agent_message": reason,
                "user_message": "specy-road: refused for this orchestration role",
            }
        ),
        None,
        0,
    ),
    _CURSOR_JSON % "SPECY_ROAD_ORCHESTRATION_ROLE=executor specy-road orchestration guard --format cursor",
    _CURSOR_JSON % "SPECY_ROAD_ORCHESTRATION_ROLE=reviewer specy-road orchestration guard --format cursor",
    "Put in .cursor/hooks.json with failClosed true. Cursor also merges .claude/settings.json hooks.",
)

ADAPTERS: dict[str, OrchestrationAdapter] = {
    "generic": OrchestrationAdapter(
        "generic",
        lambda p: _string_command(p.get("command")),
        lambda _note: (None, None, 0),
        lambda reason: (None, reason, 2),
        '{"command": "SPECY_ROAD_ORCHESTRATION_ROLE=executor specy-road orchestration guard --format generic"}',
        '{"command": "SPECY_ROAD_ORCHESTRATION_ROLE=reviewer specy-road orchestration guard --format generic"}',
        "Generic contract: JSON stdin with a command field; exit 2 denies.",
    ),
    "claude-code": _CLAUDE_EXEC,
    "codex": _CODEX,
    "cursor": _CURSOR,
}
