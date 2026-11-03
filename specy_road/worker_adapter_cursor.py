"""The ``cursor`` harness adapter: ``agent -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.worker_adapter_base import Adapter, Capabilities, Launch, Parsed, _model_flag
from specy_road.worker_adapter_parsers import _json, _snip, _text, usage_fields


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent -p --force --trust stream-json (--force force-allows every command not denied; --trust "
                              "skips a new worktree's trust prompt; print mode can write and run shell); session id "
                              "from the first event; resume = `agent -p --resume` (undocumented with a new prompt: verify)")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch(["agent", "-p", "--output-format", "stream-json", "--force", "--trust",   # new worktree: untrusted
                       *_model_flag("--model", model), "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id),
                       _text(prompt_path)])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch(["agent", "-p", "--resume", session_id, "--output-format", "stream-json", "--force", "--trust",
                       *_model_flag("--model", model), "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id),
                       _text(prompt_path)],
                      session_id=session_id)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None) -> Launch:
        """A reviewer's turn in ``--mode ask`` (read-only Q&A) with ``--trust`` and without ``--force``, which
        would force-allow every command not denied. ``agent -p`` has no structured-output flag, so ``schema`` and
        ``output`` are unused and the result event's text is parsed as the final JSON; ``session`` is
        ``(id, resume)``, and only a resume can name the id."""
        resume = ["--resume", session[0]] if session and session[1] else []
        return Launch(["agent", "-p", *resume, "--output-format", "stream-json", "--mode", "ask", "--trust",
                       *_model_flag("--model", model), _text(prompt_path)],
                      session_id=session[0] if resume else None)

    def final_message(self, line: str) -> Any:
        d = _json(line)
        return d.get("result") if d and d.get("type") == "result" and not d.get("is_error") else None

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
            # Token counts only on the line; cost comes from the roster profile when rates are known.
            return Parsed("turn_completed" if ok else "error", summary, sid, detail,
                          usage_fields(d.get("usage"), num_turns=d.get("num_turns")))
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]
