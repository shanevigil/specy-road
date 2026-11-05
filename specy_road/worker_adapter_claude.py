"""The ``claude-code`` harness adapter: ``claude -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.claude_config import claude_projects_dir
from specy_road.reviewer_auth import bare_settings_argv
from specy_road.worker_adapter_base import (REVIEWER_DISALLOWED, REVIEWER_NO_WRITES, REVIEWER_TOOLS, STDIN_INSTRUCTION,
                                         Adapter, Capabilities, Launch, Parsed, _bare, _model_flag)
from specy_road.worker_adapter_parsers import _init_detail, _json, _snip, _text, limit_detail, usage_fields

#: The executor's tools, listed rather than left to the mode: since 2.1.302 ``claude -p`` silently denies a tool
#: nothing approved, and ``acceptEdits`` approves no shell command beyond the read-only and filesystem sets.
EXECUTOR_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
#: An executor's permissions, the same on launch and resume: the mode, the allow-list, and no prompts (anything
#: still unresolved is denied and Claude is told not to retry; the denial shows in the stream, see ``parse_events``).
#: ``--allowedTools`` takes several values, so a single-value flag follows it before the instruction.
EXECUTOR_PERMISSIONS = ("--allowedTools", EXECUTOR_TOOLS, "--permission-prompts", "none", "--permission-mode", "acceptEdits")


class ClaudeCode(Adapter):
    harness = "claude-code"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="claude -p stream-json; session id chosen up front; resume = `claude -p --resume`; "
                              "no interrupt short of SIGTERM (turn is lost); hand off with `claude --resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        sid = str(uuid.uuid4())
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return replace(custom, launch_mode=launch_mode)   # left as written; only the check uses the mode
        return Launch([self._program(harness_bin), "-p", *_bare(launch_mode), "--output-format", "stream-json", "--verbose",
                       "--session-id", sid, *_model_flag("--model", model), *self.effort_flag(effort),
                       *self._add_dir(worktree, repo_root, node_id), *EXECUTOR_PERMISSIONS, STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=sid, launch_mode=launch_mode)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return replace(custom, launch_mode=launch_mode)
        # A resumed session does not keep the launch's --model: pass it again, as the launch did.
        return Launch([self._program(harness_bin), "-p", *_bare(launch_mode), "--resume", session_id, "--output-format", "stream-json",
                       "--verbose", *_model_flag("--model", model), *self.effort_flag(effort),
                       *self._add_dir(worktree, repo_root, node_id), *EXECUTOR_PERMISSIONS, STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=session_id, launch_mode=launch_mode)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, mode: str = "bare",
                        harness_bin: str | None = None) -> Launch:
        """A fresh-session reviewer's turn. ``mode="bare"`` (the default) passes ``--bare``. ``mode="explicit"``
        passes ``--setting-sources user`` and ``--strict-mcp-config`` (help.txt) and never ``--bare`` or
        ``--mcp-config``. Bare mode with only an ``apiKeyHelper`` also passes ``--settings`` and that file's path
        (:func:`~specy_road.reviewer_auth.bare_settings_argv`), never the helper command. ``harness_bin`` is the
        roster entry's binary (:meth:`Adapter._program`). Either way the branch under review runs none of its
        hooks and connects none of its MCP servers, and ``--add-dir`` names the hand-off directory. The instruction goes
        right after ``-p``: ``--add-dir`` takes several values and would swallow it. ``session`` is
        ``(id, resume)`` for ``review delegate``: the session flag, and stream-json so the id can be read back.
        Read-only (A2): no file-writing tool is allowed or approved (``Write``, ``Edit`` and ``NotebookEdit`` are
        denied, and no permission mode approves edits); bare mode fires no hook, so ``--disallowedTools`` denies
        commits, pushes and ``gh`` too (A4). ``--add-dir`` lets it read the hand-off directory. ``schema`` (the review output schema file) goes inline as ``--json-schema``. ``output`` is unused:
        the result event carries the final answer."""
        tracked = [*self.session_flag(*session), "--output-format", "stream-json", "--verbose"] if session else []
        structured = ["--json-schema", json.dumps(json.loads(schema.read_text(encoding="utf-8")))] if schema else []
        # explicit reads the subscription login from user settings and still loads no project settings or MCP.
        # bare with only an apiKeyHelper passes the settings file's path, never the helper command.
        auth = (["--setting-sources", "user", "--strict-mcp-config"] if mode == "explicit"
                else ["--bare", *bare_settings_argv()])
        return Launch([self._program(harness_bin), "-p", STDIN_INSTRUCTION, *auth, *tracked,
                       *_model_flag("--model", model),
                       *self.effort_flag(effort), "--allowedTools", REVIEWER_TOOLS,
                       "--disallowedTools", *REVIEWER_NO_WRITES, *REVIEWER_DISALLOWED, *structured,
                       "--add-dir", str(reviews)],
                      stdin=_text(prompt_path), session_id=session[0] if session else None,
                      launch_mode="explicit" if mode == "explicit" else "bare")

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
        out = [*super().parse_events(line, launch), *self._turn_signals(_json(line))]
        inferred = (out[0].detail or {}).get("inferred_mode") if out and out[0].type == "started" else None
        # explicit is a reviewer mode (M15.2), not a profile launch_mode the tool list can infer
        if inferred and launch.launch_mode in ("bare", "full") and inferred != launch.launch_mode:
            out.append(Parsed("error", f"claude started in {inferred} mode but the profile's launch_mode is "
                                       f"{launch.launch_mode}", out[0].session_id,
                              {"inferred_mode": inferred, "launch_mode": launch.launch_mode}))
        return out

    @staticmethod
    def _turn_signals(d: dict[str, Any] | None) -> list[Parsed]:
        """What the post-run check reads from a line (worker_turn_check): a ``system/api_retry``, each entry of a
        result's ``permission_denials``, and a usage limit in the result's text (code.claude.com/docs/en/headless)."""
        if not d:
            return []
        sid = d.get("session_id")
        if d.get("type") == "system" and d.get("subtype") == "api_retry":
            keys = ("attempt", "max_retries", "retry_delay_ms", "error_status", "error")
            return [Parsed("api_retry", f"api retry {d.get('attempt')}/{d.get('max_retries')}: {d.get('error')} "
                                        f"(next in {d.get('retry_delay_ms')} ms)", sid, {k: d.get(k) for k in keys})]
        if d.get("type") != "result":
            return []
        out = [Parsed("permission_denied", f"denied {p.get('tool_name')}: {_snip(json.dumps(p.get('tool_input')), 160)}",
                      sid, {k: p.get(k) for k in ("tool_name", "tool_input", "tool_use_id")})
               for p in d.get("permission_denials") or [] if isinstance(p, dict)]
        limit = limit_detail(str(d.get("result") or d.get("api_error") or ""),
                             failed=bool(d.get("is_error")) or d.get("subtype") != "success")
        if limit:
            out.append(Parsed("usage_limited", f"usage limit; resets {limit['reset_at'] or 'at an unstated time'}",
                              sid, {**limit, "source": "claude-code result"}))
        return out

    @staticmethod
    def transcript_limit(session_id: str | None, *, home: Path | None = None) -> Parsed | None:
        """A usage limit the session transcript's last assistant message names (Claude writes an API error as
        one), for a turn that exited non-zero with no result line: ``<config dir>/projects/<project>/<session-id>.jsonl``
        (harness-facts), found by the id alone. The prompt is never read: a brief may mention limits."""
        root = claude_projects_dir(home)
        if not session_id or not re.fullmatch(r"[A-Za-z0-9-]+", session_id) or not root.is_dir():
            return None
        text = ""
        for path in sorted(root.glob(f"*/{session_id}.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                d = _json(line) or {}
                message = d.get("message") if d.get("type") == "assistant" else None
                content = message.get("content") if isinstance(message, dict) else None
                parts = [content] if isinstance(content, str) else [
                    p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text"]
                text = " ".join(parts).strip() or text
        limit = limit_detail(text, failed=True)
        return Parsed("usage_limited", f"usage limit; resets {limit['reset_at'] or 'at an unstated time'}", session_id,
                      {**limit, "source": "claude-code transcript"}) if limit else None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["claude", "--resume", session_id]

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        # `--session-id` is refused for a session that exists, so a resume needs `--resume`.
        return ["--resume", session_id] if resume else ["--session-id", session_id]
