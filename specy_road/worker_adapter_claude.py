"""The ``claude-code`` harness adapter: ``claude -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.worker_adapter_base import (REVIEWER_DISALLOWED, STDIN_INSTRUCTION, Adapter, Capabilities, Launch, Parsed,
                                         _bare, _model_flag)
from specy_road.worker_adapter_parsers import _init_detail, _json, _snip, _text, usage_fields


class ClaudeCode(Adapter):
    harness = "claude-code"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="claude -p stream-json; session id chosen up front; resume = `claude -p --resume`; "
                              "no interrupt short of SIGTERM (turn is lost); hand off with `claude --resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        sid = str(uuid.uuid4())
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return replace(custom, launch_mode=launch_mode)   # left as written; only the check uses the mode
        return Launch(["claude", "-p", *_bare(launch_mode), "--output-format", "stream-json", "--verbose",
                       "--session-id", sid, *_model_flag("--model", model), *self.effort_flag(effort),
                       *self._add_dir(worktree, repo_root, node_id), "--permission-mode", "acceptEdits", STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=sid, launch_mode=launch_mode)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return replace(custom, launch_mode=launch_mode)
        return Launch(["claude", "-p", *_bare(launch_mode), "--resume", session_id, "--output-format", "stream-json",
                       "--verbose", *self.effort_flag(effort), *self._add_dir(worktree, repo_root, node_id),
                       "--permission-mode", "acceptEdits", STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=session_id, launch_mode=launch_mode)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None) -> Launch:
        """A fresh-session reviewer's turn: ``--bare``, so the branch under review runs none of its hooks and
        connects none of its MCP servers, and ``--add-dir`` for the hand-off directory. The instruction goes
        right after ``-p``: ``--add-dir`` takes several values and would swallow it. ``session`` is
        ``(id, resume)`` for ``review delegate``: the session flag, and stream-json so the id can be read back.
        Bare mode fires no hook, so ``--disallowedTools`` denies commits, pushes and ``gh`` beside the allowed
        tools; ``schema`` (the review output schema file) goes inline as ``--json-schema``. ``output`` is unused:
        the result event carries the final answer."""
        tracked = [*self.session_flag(*session), "--output-format", "stream-json", "--verbose"] if session else []
        structured = ["--json-schema", json.dumps(json.loads(schema.read_text(encoding="utf-8")))] if schema else []
        return Launch(["claude", "-p", STDIN_INSTRUCTION, "--bare", *tracked, *_model_flag("--model", model),
                       *self.effort_flag(effort), "--permission-mode", "acceptEdits",
                       "--allowedTools", "Read,Edit,Bash", "--disallowedTools", *REVIEWER_DISALLOWED, *structured,
                       "--add-dir", str(reviews)],
                      stdin=_text(prompt_path), session_id=session[0] if session else None, launch_mode="bare")

    def final_message(self, line: str) -> Any:
        d = _json(line)
        if not d or d.get("type") != "result":
            return None
        structured = d.get("structured_output")   # set when --json-schema validated the answer
        return structured if isinstance(structured, dict) else d.get("result")

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"claude session {sid} ({d.get('model', '?')})", sid, _init_detail(d))
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
            return Parsed("output", _snip(text) or "(tool use)", sid)
        if t == "result":
            text = str(d.get("result") or d.get("api_error") or "")
            ok = not d.get("is_error") and d.get("subtype") == "success"
            cost = d.get("total_cost_usd")
            summary = (f"{d.get('subtype')}: {_snip(text)}" if ok else _snip(text) or f"{d.get('subtype')}: error")
            detail: dict[str, Any] = {}
            if cost is not None:
                detail["cost_usd"] = cost
            if text:
                detail["message"] = text
            # total_cost_usd is the session's, earlier turns included: the wrapper logs the delta.
            usage = usage_fields(d.get("usage"), cost=cost, num_turns=d.get("num_turns"), estimate=True)
            usage["session_cost_usd"] = usage["cost_usd"]
            return Parsed("turn_completed" if ok else "error", summary, sid, detail or None, usage)
        return None

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        out = super().parse_events(line, launch)
        inferred = (out[0].detail or {}).get("inferred_mode") if out and out[0].type == "started" else None
        if inferred and inferred != launch.launch_mode:
            out.append(Parsed("error", f"claude started in {inferred} mode but the profile's launch_mode is "
                                       f"{launch.launch_mode}", out[0].session_id,
                              {"inferred_mode": inferred, "launch_mode": launch.launch_mode}))
        return out

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["claude", "--resume", session_id]

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        # `--session-id` is refused for a session that exists, so a resume needs `--resume`.
        return ["--resume", session_id] if resume else ["--session-id", session_id]
