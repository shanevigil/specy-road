"""The ``cursor`` harness adapter: ``agent -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from specy_road.runtime_paths import project_root
from specy_road.worker_adapter_base import Adapter, Capabilities, Launch, Parsed, _model_flag
from specy_road.worker_adapter_parsers import (
    _json,
    _snip,
    _text,
    apply_roster_price_estimate,
    model_from_argv,
    usage_fields,
    worktree_from_argv,
)


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
            # Token counts only on the line; cost comes from the roster profile when rates are known.
            return Parsed("turn_completed" if ok else "error", summary, sid, detail,
                          usage_fields(d.get("usage"), num_turns=d.get("num_turns")))
        return None

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        parsed = self.parse(line)
        if not parsed or parsed.usage is None or parsed.usage.get("cost_usd") is not None:
            return [parsed] if parsed else []
        model = model_from_argv(launch.argv)
        if not model:
            return [parsed]
        wt = worktree_from_argv(launch.argv)
        usage = apply_roster_price_estimate(parsed.usage, model, project_root(wt) if wt else project_root())
        return [parsed] if usage is parsed.usage else [replace(parsed, usage=usage)]

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]
