"""The ``cursor`` harness adapter: ``agent -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from specy_road.worker_adapter_base import Adapter, Capabilities, Launch, Parsed, Unsupported, _model_flag
from specy_road.worker_adapter_parsers import _json, _snip, _text, usage_fields
from specy_road.worker_sessions import session_id_problem


def create_chat(worktree: Path) -> str:
    """``agent create-chat`` in the worktree: the chat id, known before the turn starts, as Claude's is."""
    try:
        r = subprocess.run(["agent", "create-chat"], cwd=worktree, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unsupported(f"cursor: `agent create-chat` did not run: {e}") from None
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    chat = lines[-1] if lines else ""
    why = session_id_problem("cursor", chat)
    if r.returncode != 0 or why:
        raise Unsupported(f"cursor: `agent create-chat` exited {r.returncode} without a chat id "
                          f"({why or 'ok'}): {_snip(r.stderr or r.stdout)}")
    return chat


def _no_worktree_flag(cli: str | None) -> None:
    """A custom command must not pass ``-w``/``--worktree``: ``agent`` would make its own worktree under
    ``~/.cursor/worktrees`` and work there, not in the one specy-road created (harness-facts)."""
    try:
        words = shlex.split(cli) if cli else []
    except ValueError:
        return   # an unbalanced quote: the custom-command check refuses it with its own reason
    if any(w in ("-w", "--worktree") or w.startswith("--worktree=") for w in words):
        raise Unsupported(f"channels.cli: cursor workers never pass -w/--worktree; specy-road creates the worktree: {cli}")


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent create-chat, then agent -p --resume <chat> --force --trust stream-json (--force "
                              "force-allows every command not denied; --trust skips a new worktree's trust prompt; print "
                              "mode can write and run shell; never -w); resume = `agent -p --resume` (undocumented with a "
                              "new prompt: verify)")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        chat = create_chat(worktree)   # the chat first: a turn that dies before its first event still has its id
        return Launch(["agent", "-p", "--resume", chat, "--output-format", "stream-json", "--force", "--trust",   # new worktree: untrusted
                       *_model_flag("--model", model), "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id),
                       _text(prompt_path)], session_id=chat)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch(["agent", "-p", "--resume", session_id, "--output-format", "stream-json", "--force", "--trust",
                       "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id), _text(prompt_path)],
                      session_id=session_id)

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
            text = str(d.get("result") or "")
            ok = not d.get("is_error")
            summary = f"{d.get('subtype')}: {_snip(text)}" if ok else _snip(text) or f"{d.get('subtype')}: error"
            detail = {"message": text} if text else None
            # Token counts only, when the line carries them: no cost field is documented for agent -p.
            return Parsed("turn_completed" if ok else "error", summary, sid, detail,
                          usage_fields(d.get("usage"), num_turns=d.get("num_turns")))
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]
