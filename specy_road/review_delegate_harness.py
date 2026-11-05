"""One roster entry's harness launch for ``review delegate`` (M15.31: model id matches worker delegate)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from specy_road.orchestration_config import harness_model
from specy_road.orchestration_pinned import pinned_profile_for_entry
from specy_road.review_files import reviews_dir
from specy_road.review_record_write import OUTPUT_SCHEMA_NAME
from specy_road.reviewer_auth import claude_default_reviewer
from specy_road.worker_adapters import ClaudeCode, Launch, adapter_for, reviewer_cli


class HarnessSetupError(Exception):
    """Invalid roster entry or profile for a delegated reviewer launch."""


class _Harness:
    """One roster entry's way of starting and resuming a reviewer turn."""

    def __init__(self, repo_root: Path, entry: dict[str, Any], node_id: str, cwd: Path, chore: bool = False) -> None:
        self.harness = str(entry.get("harness") or "generic")
        self.adapter = adapter_for(self.harness)
        prof = pinned_profile_for_entry(repo_root, entry)
        if prof is not None and not prof.ok:
            raise HarnessSetupError(f"profile for {entry.get('id')!r}: " + "; ".join(prof.errors))
        self.cli = (entry.get("channels") or {}).get("cli")
        if not self.cli and self.harness == "generic" and prof is not None:
            self.cli = prof.cli()
        if prof is not None:
            self.api_id = harness_model(entry, prof.api_id)
        else:
            self.api_id = harness_model(entry)   # no profile: the roster id, as worker delegate passes
        self.effort = prof.effort("reviewer") if prof is not None else None
        self.mode = prof.launch_mode() if prof is not None else "full"
        self.repo_root, self.node_id, self.cwd, self.model = repo_root, node_id, cwd, str(entry.get("id"))
        self.chore = chore
        self.default = self.harness != "generic" and not self.cli and (not chore or isinstance(self.adapter, ClaudeCode))
        self.auth_error: str | None = None
        self.note: str | None = None
        self.harness_bin = entry.get("harness_bin")
        if self.default and isinstance(self.adapter, ClaudeCode):
            profile_mode = prof.launch_mode() if prof is not None else None
            self.launch_mode, self.auth_error, self.note = claude_default_reviewer(entry, profile_mode)
        else:
            self.launch_mode = self.mode
        self.can_resume = self.adapter.caps.resume
        self.output: Path | None = None
        self.log = Path()
        self.replaced: list[Path] = []

    def launch(self, prompt: Path, session: str | None) -> Launch:
        """A fresh turn, or a resume of ``session`` (an id the harness reported)."""
        if self.default:
            sid = session or (str(uuid.uuid4()) if isinstance(self.adapter, ClaudeCode) else None)
            reviews = reviews_dir(self.repo_root, self.node_id)
            structured = {} if self.chore else {"schema": reviews / OUTPUT_SCHEMA_NAME, "output": self.output}
            extra = {"mode": self.launch_mode} if isinstance(self.adapter, ClaudeCode) else {}
            return self.adapter.reviewer_launch(prompt, self.api_id, reviews, self.effort,
                                                session=(sid, session is not None) if sid else None,
                                                **structured, **extra, harness_bin=self.harness_bin)
        kw = {"node_id": self.node_id, "repo_root": self.repo_root, "launch_mode": self.mode, "effort": self.effort,
              "harness_bin": self.harness_bin}
        cli = (reviewer_cli(self.cli, reviews_dir(self.repo_root, self.node_id) / OUTPUT_SCHEMA_NAME)
               if self.cli and not self.chore else self.cli)
        if session is not None:
            return self.adapter.resume(session, prompt, self.cwd, self.api_id, cli, **kw)
        return self.adapter.launch(prompt, self.cwd, self.api_id, cli, **kw)
