"""The ``codex`` harness adapter: ``codex exec --json`` (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from specy_road.worker_adapter_base import (CODEX_POLICY, CODEX_REVIEW_POLICY, Adapter, Capabilities, Launch, Parsed,
                                         _model_flag)
from specy_road.worker_adapter_parsers import _json, _snip, _text, usage_fields


class Codex(Adapter):
    harness = "codex"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="codex exec --json (prompt on stdin); thread id from thread.started; "
                              "resume = `codex exec resume <id> -` (prompt on stdin); hand off with `codex resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch(["codex", "exec", "--json", *_model_flag("-m", model), *self.effort_flag(effort), *CODEX_POLICY,
                       "-C", str(worktree), *self._add_dir(worktree, repo_root, node_id), "-"], stdin=_text(prompt_path))

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        # Same policy as the launch, prompt on stdin again (128 KiB argv cap). `exec resume` takes neither --sandbox,
        # -C (the wrapper runs it in the worktree) nor a documented --add-dir, so the policy goes in as config overrides.
        return Launch(["codex", "exec", "resume", "--json", *_model_flag("-m", model), *self.effort_flag(effort),
                       *CODEX_POLICY, session_id, "-"],
                      stdin=_text(prompt_path), session_id=session_id)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None) -> Launch:
        """A reviewer's turn in the read-only sandbox: it writes nothing, so it needs no writable root, and the
        verdict comes back as the final message, shaped by ``--output-schema`` and written to ``-o``. Both flags
        are documented for ``codex exec`` only, so a resume (``session`` is ``(id, True)``) leaves them out and
        its last ``agent_message`` is parsed instead; a fresh turn cannot choose its thread id."""
        if session and session[1]:
            return Launch(["codex", "exec", "resume", "--json", *self.effort_flag(effort), *CODEX_REVIEW_POLICY,
                           session[0], "-"], stdin=_text(prompt_path), session_id=session[0])
        return Launch(["codex", "exec", "--json", *_model_flag("-m", model), *self.effort_flag(effort),
                       *CODEX_REVIEW_POLICY, *(["--output-schema", str(schema)] if schema else []),
                       *(["-o", str(output)] if output else []), "-"], stdin=_text(prompt_path))

    def final_message(self, line: str) -> Any:
        d = _json(line)
        item = (d or {}).get("item") or {}
        if (d or {}).get("type") != "item.completed" or item.get("type") != "agent_message":
            return None
        return item.get("text")

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
                text = str(item.get("text") or "")
                return Parsed("output", _snip(text) or "(empty message)",
                              detail={"message": text} if text else None)
            return Parsed("output", f"{item.get('type', 'item')} done")
        if t == "turn.completed":
            return Parsed("turn_completed", "turn completed", detail={"usage": d.get("usage")},
                          usage=usage_fields(d.get("usage")))
        if t in ("turn.failed", "error"):
            raw = json.dumps(d.get("error") or d.get("message") or d)
            return Parsed("error", _snip(raw), detail={"message": raw})
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["codex", "resume", session_id]
