"""Prompt-submit hook adapters: record a human's direct prompt to a worker (slice 7c).

A worker handed to a human (``worker handoff``) is resumed in the harness's
own session. The project-level prompt-submit hook fires in that session too,
so it can tell specy-road what was said: ``specy-road worker hook --format
<harness>`` reads the payload, matches the session id to a worker's
``provider_session_id``, and appends the prompt to
``work/.workers/<id>.interventions.jsonl``. ``worker reclaim`` reads that
file. The hook never blocks and always exits 0: it is a witness, not a gate.

Payloads (verified against the vendors' docs, 2026-10-27): Claude Code and
Codex ``UserPromptSubmit`` carry ``session_id`` and ``prompt``; Cursor
``beforeSubmitPrompt`` carries ``conversation_id`` and ``prompt`` and expects
a JSON answer with ``continue``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HookAdapter:
    harness: str
    session_key: str
    allow_output: str | None
    config: str
    notes: str

    def session_and_prompt(self, payload: dict[str, Any]) -> tuple[str | None, str]:
        sid = payload.get(self.session_key)
        return (str(sid) if sid else None), str(payload.get("prompt") or "")


HOOKS: dict[str, HookAdapter] = {
    "claude-code": HookAdapter(
        "claude-code", "session_id", None,
        """{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": "specy-road worker hook --format claude-code", "timeout": 10}
        ]
      }
    ]
  }
}""",
        "Put the snippet in .claude/settings.json. Plain stdout would be added as context, so the hook prints "
        "nothing. Whether UserPromptSubmit fires for the prompt of a `claude -p` run is unverified; it does "
        "fire for a human's `claude --resume <id>` session, which is the case that matters.",
    ),
    "codex": HookAdapter(
        "codex", "session_id", None,
        """{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": "specy-road worker hook --format codex", "timeout": 10,
           "statusMessage": "specy-road worker witness"}
        ]
      }
    ]
  }
}""",
        "Put the snippet in .codex/hooks.json; the project's .codex/ layer and the hook must be trusted "
        "(`/hooks`, or --dangerously-bypass-hook-trust). Silent on success, as Codex expects.",
    ),
    "cursor": HookAdapter(
        "cursor", "conversation_id", json.dumps({"continue": True}),
        """{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [
      {"command": "specy-road worker hook --format cursor", "timeout": 10}
    ]
  }
}""",
        "Put the snippet in .cursor/hooks.json. The hook answers {\"continue\": true} so the prompt always "
        "goes through. Cursor's conversation_id is what `agent --resume` names, so it matches the worker's "
        "session id.",
    ),
}
