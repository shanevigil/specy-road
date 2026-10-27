"""Harness adapters: how a worker is launched, resumed, read, and handed to a human (slice 7b).

One adapter per harness the roster may name (``claude-code``, ``codex``,
``cursor``, ``generic``). Each builds the documented one-shot command of its
CLI (verified against the vendors' docs on 2026-10-27, see
``docs/design-notes/v0-3-1-worker-orchestration.md`` D2), turns the CLI's
JSON output lines into worker events, and says which of the lifecycle
operations it supports. What it does not support is declared, never
emulated: a one-shot CLI has no interrupt short of killing the process, so
``interrupt`` is ``False`` and the command says so, rather than a kill being
dressed up as one. The long-lived protocols (Codex app-server, Cursor ACP)
are the later adapters that turn those flags on.

A roster entry's ``channels.cli`` (``{prompt}`` = prompt file path) replaces
the built command for any harness while its output is still parsed as that
harness's; that is how an adopter widens or narrows permissions, pins flags,
or points at a wrapper. Claude Code's default asks for the narrowest
unattended mode it documents (``acceptEdits``), so a first run may stop at a
shell permission; Cursor's ``agent -p`` applies no change without ``--force``,
which is its full auto-run, so that default is the widest — read the table
in ``docs/orchestration-workers.md`` before trusting either on a new repo.
"""

from __future__ import annotations

import json
import re
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.worker_state import HARNESSES


@dataclass(frozen=True)
class Capabilities:
    resume: bool
    interrupt: bool
    steer: bool
    handoff: bool
    events: bool
    notes: str


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    stdin: str | None = None        # prompt text piped in, when the CLI reads it that way
    session_id: str | None = None   # chosen up front, when the harness lets the caller pick


@dataclass(frozen=True)
class Parsed:
    """One output line turned into an event: ``type`` is a worker-event type."""
    type: str
    summary: str
    session_id: str | None = None
    detail: dict[str, Any] | None = None


class Unsupported(Exception):
    """The adapter declares this operation unsupported for its harness."""


def _text(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


#: What a harness is told when the prompt itself travels on stdin: an argv
#: string is capped at 128 KiB on Linux, and a brief can be longer.
STDIN_INSTRUCTION = "The task is the text on standard input. Follow it exactly; it is the whole prompt."


#: A placeholder must be a whole shell word (optionally quoted as one): inside
#: a larger word (``"prefix <prompt>"``, ``--prompt=<prompt>``) the quoting
#: ``shlex.quote`` adds lands inside still-open quotes, where ``$(…)`` runs.
_PLACEHOLDER = re.compile(r'(?<!\S)(["\']?)(<prompt>|\{prompt\}|\{session\})\1(?!\S)')
_ANY_PROMPT = re.compile(r"<prompt>|\{prompt\}")


def substitute_prompt(cli: str, prompt_path: Path, session: str | None = None) -> str:
    """``{prompt}`` → the quoted file path; ``<prompt>`` (the profiles' form) → the quoted text.

    One pass over the template, whole words only: substituted text is never
    rescanned, and a placeholder embedded in a larger word is refused by
    :func:`placeholder_problem` before this runs.
    """
    def repl(m: re.Match[str]) -> str:
        tok = m.group(2)
        if tok == "{session}":
            return shlex.quote(session or "")
        if tok == "{prompt}":
            return shlex.quote(str(prompt_path))
        return shlex.quote(_text(prompt_path))
    return _PLACEHOLDER.sub(repl, cli)


def placeholder_problem(cli: str | None) -> str | None:
    """Why ``cli`` cannot be run: no prompt placeholder, or one that is not a whole word."""
    if not cli or not _ANY_PROMPT.search(cli):
        return "no {prompt} (the prompt file path) or <prompt> (the prompt text) placeholder"
    found = {m.group(2) for m in _PLACEHOLDER.finditer(cli)}
    if not found & {"<prompt>", "{prompt}"}:
        return ('the prompt placeholder must be a whole argument ("<prompt>" or {prompt}), '
                "not part of a larger word")
    stray = [m.group(0) for m in _ANY_PROMPT.finditer(cli)] 
    if len(stray) != sum(1 for m in _PLACEHOLDER.finditer(cli) if m.group(2) != "{session}"):
        return "every prompt placeholder must be a whole argument, not part of a larger word"
    return None


def has_prompt_placeholder(cli: str | None) -> bool:
    return placeholder_problem(cli) is None


def _snip(s: str, n: int = 200) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


class Adapter:
    harness = "generic"
    caps = Capabilities(resume=False, interrupt=False, steer=False, handoff=False, events=False,
                        notes="runs the roster/profile cli; output lines become events, nothing else is known")

    def launch(self, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        why = placeholder_problem(cli)
        if why:
            raise Unsupported(f"generic harness needs a roster channels.cli or profile access.cli: {why}")
        return Launch(["sh", "-c", substitute_prompt(cli, prompt_path)])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        raise Unsupported(f"{self.harness}: resume is not supported")

    def parse(self, line: str) -> Parsed | None:
        return Parsed("output", _snip(line)) if line.strip() else None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        raise Unsupported(f"{self.harness}: no native session to hand off")

    def _custom(self, cli: str | None, prompt_path: Path, session_id: str | None = None) -> Launch | None:
        """The roster's own command, when it has the placeholders this call needs.

        ``{prompt}`` is the prompt file path; ``{session}`` (optional) is the
        native session id, and a resume uses the custom command only when it
        names it, since the default command is the only one that knows the
        harness's resume flag.
        """
        if not has_prompt_placeholder(cli):
            return None
        if session_id is not None and "{session}" not in cli:
            return None
        # On launch a command that names {session} gets a fresh id, and the
        # record keeps it, so the same command serves `message` / `resume`.
        sid = session_id if session_id is not None else (str(uuid.uuid4()) if "{session}" in cli else None)
        text = substitute_prompt(cli, prompt_path, sid)
        return Launch(["sh", "-c", text], session_id=sid)


class ClaudeCode(Adapter):
    harness = "claude-code"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="claude -p stream-json; session id chosen up front; resume = `claude -p --resume`; "
                              "no interrupt short of SIGTERM (turn is lost); hand off with `claude --resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        sid = str(uuid.uuid4())
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["claude", "-p", "--output-format", "stream-json", "--verbose", "--session-id", sid,
                       "--model", model, "--permission-mode", "acceptEdits", STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=sid)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        return Launch(["claude", "-p", "--resume", session_id, "--output-format", "stream-json", "--verbose",
                       "--permission-mode", "acceptEdits", STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"claude session {sid} ({d.get('model', '?')})", sid)
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
            return Parsed("output", _snip(text) or "(tool use)", sid)
        if t == "result":
            ok = not d.get("is_error") and d.get("subtype") == "success"
            cost = d.get("total_cost_usd")
            return Parsed("turn_completed" if ok else "error",
                          f"{d.get('subtype')}: {_snip(d.get('result') or '')}", sid,
                          {"cost_usd": cost} if cost is not None else None)
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["claude", "--resume", session_id]


class Codex(Adapter):
    harness = "codex"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="codex exec --json (prompt on stdin); thread id from thread.started; "
                              "resume = `codex exec resume <id> -` (prompt on stdin); hand off with `codex resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["codex", "exec", "--json", "-m", model, "--sandbox", "workspace-write",
                       "--ask-for-approval", "never", "-C", str(worktree), "-"], stdin=_text(prompt_path))

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        # Same sandbox and approval flags as the launch, and the prompt on
        # stdin again: an argv string is capped at 128 KiB on Linux.
        return Launch(["codex", "exec", "resume", "--json", "--sandbox", "workspace-write",
                       "--ask-for-approval", "never", "-C", str(worktree), session_id, "-"],
                      stdin=_text(prompt_path), session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        t = d.get("type")
        if t == "thread.started":
            return Parsed("started", f"codex thread {d.get('thread_id')}", d.get("thread_id"))
        if t == "item.completed":
            item = d.get("item") or {}
            if item.get("type") == "agent_message":
                return Parsed("output", _snip(item.get("text") or "") or "(empty message)")
            return Parsed("output", f"{item.get('type', 'item')} done")
        if t == "turn.completed":
            return Parsed("turn_completed", "turn completed", detail={"usage": d.get("usage")})
        if t in ("turn.failed", "error"):
            return Parsed("error", _snip(json.dumps(d.get("error") or d.get("message") or d)))
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["codex", "resume", session_id]


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent -p --force stream-json (--force is Cursor's full auto-run; without it changes "
                              "are only proposed); session id from the first event; resume = `agent -p --resume` "
                              "(print-mode resume with a new prompt is undocumented: verify on your install)")

    def launch(self, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["agent", "-p", "--output-format", "stream-json", "--force", "--model", model,
                       "--workspace", str(worktree), _text(prompt_path)])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        return Launch(["agent", "-p", "--resume", session_id, "--output-format", "stream-json", "--force",
                       "--workspace", str(worktree), _text(prompt_path)], session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"cursor session {sid} ({d.get('model', '?')})", sid)
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
            return Parsed("output", _snip(text) or "(assistant)", sid)
        if t == "tool_call":
            return Parsed("output", f"tool call {d.get('subtype', '')}".strip(), sid)
        if t == "result":
            ok = not d.get("is_error")
            return Parsed("turn_completed" if ok else "error", f"{d.get('subtype')}: {_snip(d.get('result') or '')}", sid)
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]


ADAPTERS: dict[str, Adapter] = {a.harness: a for a in (Adapter(), ClaudeCode(), Codex(), Cursor())}
assert set(ADAPTERS) == set(HARNESSES)


def adapter_for(harness: str) -> Adapter:
    try:
        return ADAPTERS[harness]
    except KeyError:
        raise Unsupported(f"unknown harness {harness!r}; expected one of {', '.join(HARNESSES)}") from None
