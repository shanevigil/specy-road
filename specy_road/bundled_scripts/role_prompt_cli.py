"""The commands ``specy-road prompt --channel cli`` runs (split from :mod:`role_prompt` for the file limit).

A reviewer runs its harness's read-only reviewer command (:func:`run_default_reviewer`) or its own command with its
program's structured-output flags (:func:`run_custom_reviewer`), captured and filed by
:func:`specy_road.review_record_write.run_and_file` (M8.3); any other role runs its command as written
(:func:`run_plain_cli`). With a ``transcript``, the output is also collected for the run record (M11.72).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path

from specy_road.bundled_scripts.role_prompt_stream import stream_and_capture
from specy_road.model_profiles import Profile
from specy_road.orchestration_role_env import CLAUDE_REVIEWER_AVOID_ENV
from specy_road.review_record_write import output_path, run_and_file, write_schema
from specy_road.worker_adapters import ADAPTERS, Launch, Unsupported, reviewer_cli, substitute_prompt


def _shown(argv: list[str]) -> str:
    """The command for the terminal, a long argument (the prompt, an inline schema) shortened."""
    return shlex.join(a if len(a) <= 200 else f"<{len(a)} chars>" for a in argv)


def run_default_reviewer(prof: Profile | None, prompt_path: Path, root: Path, model: str | None, reviews: Path,
                         level: str | None, harness: str = "claude-code", ref: str | None = None,
                         transcript: list[str] | None = None, sign_key: Path | None = None) -> int:
    """The harness's own read-only reviewer command (Claude Code bare, with ``--add-dir`` for the hand-off
    directory), its final JSON filed as the record (:func:`~specy_road.review_record_write.file_review`, signed
    with ``sign_key``); 0 only when a record was filed. ``transcript`` collects the output for the run record
    (M11.72). The caller holds the leaf's run lock (the answer is emptied under it)."""
    api_id = prof.api_id if prof is not None else model
    api_id = None if (api_id or "").strip().lower() in ("", "unknown") else api_id   # unknown: the harness default
    adapter, out = ADAPTERS[harness], output_path(reviews, str(model))
    session = (str(uuid.uuid4()), False) if harness == "claude-code" else None   # stream-json, to read the result
    launch = adapter.reviewer_launch(prompt_path, api_id, reviews, level, session=session,
                                     schema=write_schema(root, reviews), output=out)
    if harness == "claude-code":
        launch = replace(launch, env={**(launch.env or {}), **CLAUDE_REVIEWER_AVOID_ENV})   # as `review delegate`'s
        print("note: the reviewer runs with --bare (no repository hooks, MCP servers or CLAUDE.md), and bare mode "
              "never reads your subscription login: it needs ANTHROPIC_API_KEY (or an apiKeyHelper)", file=sys.stderr)
    print(f"running: {_shown(launch.argv)}" + (f" < {prompt_path}" if launch.stdin is not None else ""), file=sys.stderr)
    return run_and_file(launch, adapter, root, str(model), reviews, ref, transcript, sign_key)


def run_custom_reviewer(prof: Profile | None, cli: str, prompt_path: Path, root: Path, model: str, reviews: Path,
                        ref: str | None, harness: str | None, effort: list[str],
                        transcript: list[str] | None = None, sign_key: Path | None = None) -> int:
    """A roster ``channels.cli`` or profile ``access.cli`` reviewer, run as written plus its program's
    structured-output flags (:func:`reviewer_cli`), captured and filed like the default commands."""
    try:
        cli = reviewer_cli(cli, write_schema(root, reviews))
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        if transcript is not None:
            transcript.append(f"error: {e}")
        return 1
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    launch = Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=effort)],
                    launch_mode=prof.launch_mode() if prof is not None else "full")
    return run_and_file(launch, ADAPTERS.get(harness or "generic", ADAPTERS["generic"]), root, model, reviews, ref,
                        transcript, sign_key)


def run_plain_cli(cli: str, prompt_path: Path, root: Path, effort: list[str],
                  transcript: list[str] | None = None) -> int:
    """Any other role's command, run as written; with ``transcript``, streamed and transcribed (M11.72)."""
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    try:
        cmd = substitute_prompt(cli, prompt_path, effort=effort)
        if transcript is None:
            return subprocess.run(cmd, shell=True, cwd=root, check=False).returncode
        return stream_and_capture(cmd, cwd=root, transcript=transcript, shell=True)
    except OSError as e:   # E2BIG: "<prompt>" puts the whole text on the command line
        print(f"error: could not launch the cli: {e.strerror}; if the prompt is too long for a command line, "
              'use {prompt} (its file path) instead of "<prompt>"', file=sys.stderr)
        if transcript is not None:
            transcript.append(f"error: could not launch the cli: {e.strerror}")
        return 1
