"""The ``codex`` harness adapter: ``codex exec --json`` (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path

from specy_road.worker_adapter_base import (CODEX_POLICY, CODEX_REVIEW_POLICY, Adapter, Capabilities, Launch,
                                         Parsed, _model_flag)
from specy_road.worker_adapter_parsers import _json, _snip, _text, limit_detail, usage_fields
from specy_road.worker_usage_delta import SESSION_TOKENS

#: Memories off on launch and resume, as config (``exec resume`` takes ``-c``): the feature and both of its
#: switches (harness-facts: ``--disable memories`` is ``features.memories=false``; v2's key names are undocumented).
CODEX_MEMORY_OFF = ("-c", "features.memories=false", "-c", "memories.use_memories=false",
                    "-c", "memories.generate_memories=false")

def codex_homes() -> Path:
    """Where the per-profile ``CODEX_HOME`` directories live, one per model id the harness is told."""
    return Path.home() / ".specy-road" / "codex-home"


def profile_home(model: str | None) -> Path:
    """The profile's own ``CODEX_HOME``: none of the user's config, memories or global AGENTS.md reaches the
    worker, and its sessions stay apart. The user's ``auth.json`` is linked in, so the login carries over."""
    home = codex_homes() / re.sub(r"[^A-Za-z0-9._-]", "_", model or "default")
    home.mkdir(parents=True, exist_ok=True)
    auth = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"
    if auth.is_file() and not (home / "auth.json").exists() and not (home / "auth.json").is_symlink():
        (home / "auth.json").symlink_to(auth)
    return home


def session_home(session_id: str) -> Path | None:
    """The per-profile home whose ``sessions/`` holds the thread's rollout, so a resume finds it."""
    root = codex_homes()
    hits = sorted(root.glob(f"*/sessions/**/*{session_id}*.jsonl")) if root.is_dir() else []
    return root / hits[0].relative_to(root).parts[0] if hits else None


class Codex(Adapter):
    harness = "codex"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="codex exec --json (prompt on stdin); thread id from thread.started; "
                              "resume = `codex exec resume <id> -` (prompt on stdin); hand off with `codex resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch([self._program(harness_bin), "exec", "--json", *_model_flag("-m", model), *self.effort_flag(effort), *CODEX_POLICY,
                       *CODEX_MEMORY_OFF, "-C", str(worktree), *self._add_dir(worktree, repo_root, node_id), "-"],
                      stdin=_text(prompt_path), env={"CODEX_HOME": str(profile_home(model))})

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        # Same policy as the launch, prompt on stdin again (128 KiB argv cap). `exec resume` takes neither --sandbox,
        # -C (the wrapper runs it in the worktree) nor a documented --add-dir, so the policy goes in as config overrides.
        home = session_home(session_id) or profile_home(model)   # where the launch left the thread
        return Launch([self._program(harness_bin), "exec", "resume", "--json", *_model_flag("-m", model), *self.effort_flag(effort),
                       *CODEX_POLICY, *CODEX_MEMORY_OFF, session_id, "-"],
                      stdin=_text(prompt_path), session_id=session_id, env={"CODEX_HOME": str(home)})

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, harness_bin: str | None = None) -> Launch:
        """A reviewer's turn in the read-only sandbox: it writes nothing, so it needs no writable root, and the
        verdict comes back as the final message, shaped by ``--output-schema`` and written to ``-o``. Both flags
        are documented for ``codex exec`` only, so a resume (``session`` is ``(id, True)``) leaves them out and
        its last ``agent_message`` is parsed instead; a fresh turn cannot choose its thread id. A resume passes
        ``-m`` again, as the fresh turn does, so a format-repair retry runs on the requested model. Both turns pass
        ``CODEX_MEMORY_OFF`` and an isolated ``CODEX_HOME``: the profile's on a fresh turn, the session's home
        (else the profile's) on resume, as a worker launch and resume do."""
        if session and session[1]:
            home = session_home(session[0]) or profile_home(model)   # where the fresh turn left the thread
            return Launch([self._program(harness_bin), "exec", "resume", "--json", *_model_flag("-m", model),
                           *self.effort_flag(effort), *CODEX_REVIEW_POLICY, *CODEX_MEMORY_OFF,
                           session[0], "-"], stdin=_text(prompt_path), session_id=session[0],
                          env={"CODEX_HOME": str(home)})
        return Launch([self._program(harness_bin), "exec", "--json", *_model_flag("-m", model), *self.effort_flag(effort),
                       *CODEX_REVIEW_POLICY, *CODEX_MEMORY_OFF, *(["--output-schema", str(schema)] if schema else []),
                       *(["-o", str(output)] if output else []), "-"], stdin=_text(prompt_path),
                      env={"CODEX_HOME": str(profile_home(model))})

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
            usage = usage_fields(d.get("usage"))
            # The thread's running total on `exec resume`, not the turn's: the wrapper subtracts the last turn's
            # (worker_usage_delta), as it does Claude's session cost.
            usage["session_usage"] = {k: usage[k] for k in SESSION_TOKENS}
            return Parsed("turn_completed", "turn completed", detail={"usage": d.get("usage")}, usage=usage)
        if t in ("turn.failed", "error"):
            raw = json.dumps(d.get("error") or d.get("message") or d)
            return Parsed("error", _snip(raw), detail={"message": raw})
        return None

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        # A price estimate from the running token total is the session's cost too: recorded the same way.
        out = [replace(p, usage={**p.usage, "session_cost_usd": p.usage.get("cost_usd")}) if p.usage else p
               for p in super().parse_events(line, launch)]
        d = _json(line)
        # A limit arrives as a failure whose text names the reset ("try again in/at"): read it, never the exit code.
        limit = limit_detail(out[0].detail["message"], failed=True) if out and out[0].type == "error" and d else None
        if limit:
            out.append(Parsed("usage_limited", f"usage limit; resets {limit['reset_at'] or 'at an unstated time'}",
                              detail={**limit, "source": f"codex {d.get('type')}"}))
        return out

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        home = session_home(session_id)   # the worker's thread is in its profile's CODEX_HOME, not ~/.codex
        return ["env", f"CODEX_HOME={home}", "codex", "resume", session_id] if home else ["codex", "resume", session_id]
