"""The commands ``specy-road prompt --channel cli`` runs (split from :mod:`role_prompt` for the file limit).

Nothing here runs without ``prompt --run`` (M15.3): without it ``prompt`` prints the command
(:func:`show_cli`, :func:`show_reviewer`) and starts no process. A reviewer's command comes from its roster entry
only (:func:`reviewer_command`: never the profile's ``access.cli``), and it runs in the leaf's own worktree
(:func:`leaf_worktree`). A reviewer goes through :func:`run_reviewer_channel`, which always returns the run's filing
(:class:`~specy_road.review_record_write.Outcome`): its harness's read-only reviewer command
(:func:`run_default_reviewer`) or its own command with its program's structured-output flags
(:func:`run_custom_reviewer`), captured and filed by :func:`specy_road.review_record_write.run_and_file` (M8.3), or
a rerun request when nothing could be sent; :func:`close_cli_review_run` closes its run record from that filing.
Any other role runs its command as written (:func:`run_plain_cli`). With a ``transcript``, the output is also
collected for the run record (M11.72).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.role_prompt_stream import stream_and_capture
from specy_road.git_subprocess import git_ok
from specy_road.model_profiles import Profile
from specy_road.orchestration_role_env import CLAUDE_REVIEWER_AVOID_ENV
from specy_road.review_record_write import (Outcome, answer_scratch, close_review_run, replace_file, run_and_file,
                                            write_schema)
from specy_road.review_target import ReviewTarget
from specy_road.reviewer_run_failure import _now, harness_error_line, save_run, turn_capacity_error
from specy_road.worker_adapter_parsers import effort_note
from specy_road.worker_adapters import ADAPTERS, Launch, Unsupported, placeholder_problem, reviewer_cli, substitute_prompt

#: Reviewer harnesses whose default command specy-road launches, reads back and files from.
READ_BACK_HARNESSES = ("claude-code", "codex", "cursor")
#: Flags that let a harness write or skip its permission prompts; a reviewer command carrying one is refused.
BYPASS_FLAGS = ("--force", "--yolo", "--dangerously-skip-permissions")


def _shown(argv: list[str]) -> str:
    """The command for the terminal, a long argument (the prompt, an inline schema) shortened."""
    return shlex.join(a if len(a) <= 200 else f"<{len(a)} chars>" for a in argv)


def preflight(cmd: str | None, root: Path) -> int:
    """Run the roster's ``preflight`` (proposal §3.6: e.g. confirm which process owns a local model's port) before
    anything else is even inspected; its exit code, 0 when there is none."""
    if not cmd:
        return 0
    print(f"preflight: {cmd}", file=sys.stderr)
    rc = subprocess.run(cmd, shell=True, cwd=root, check=False).returncode
    if rc != 0:
        print(f"error: preflight failed (exit {rc}); nothing was sent", file=sys.stderr)
    return rc


def resolve_cli(prof: Profile | None, entry_cli: str | None, harness: str | None,
                level: str | None) -> tuple[str | None, list[str], str]:
    """``(cli, effort flags, error)``: the roster's ``channels.cli`` (it wins, as ``worker delegate`` has it), else
    the profile's ``access.cli``; ``error`` when there is none or it is malformed."""
    cli = entry_cli or (prof.cli() if prof else None)
    if not cli:
        return None, [], "--channel cli needs a roster `channels.cli` or an `access.cli` in the model's profile"
    why = placeholder_problem(cli)
    if why:
        return None, [], f"the cli has {why}: {cli}"
    note = effort_note(cli, level)
    if note:
        print(note, file=sys.stderr)
    return cli, ADAPTERS.get(harness or "generic", ADAPTERS["generic"]).effort_flag(level), ""


def bypass_flag(cli: str) -> str | None:
    """The first of :data:`BYPASS_FLAGS` ``cli`` passes (alone or as ``--flag=value``), else ``None``."""
    try:
        words = shlex.split(cli)
    except ValueError:   # unbalanced quotes: still refuse a flag that is plainly there
        words = cli.split()
    return next((f for w in words for f in BYPASS_FLAGS if w == f or w.startswith(f + "=")), None)


def reviewer_command(prof: Profile | None, entry: dict[str, Any], model: str) -> tuple[str | None, str | None, str]:
    """``(api id, custom cli, error)`` for the roster ``entry``'s reviewer, from the entry only: a claude-code, codex
    or cursor entry without ``channels.cli`` runs its adapter's read-only command with the entry's model (the API
    id, which must be known), any other entry its ``channels.cli``, which must pass none of :data:`BYPASS_FLAGS`.
    The profile's ``access.cli`` is never used: it is an example, often with ``--force`` and no ``--model``."""
    harness, entry_cli = entry.get("harness"), (entry.get("channels") or {}).get("cli")
    if harness in READ_BACK_HARNESSES and not entry_cli:
        api_id = prof.api_id if prof is not None else model
        if (api_id or "").strip().lower() in ("", "unknown"):
            return None, None, (f"{model!r} resolves to no API model id (its profile's api_id is unknown), so the "
                                "harness would run its own default model under this roster id; set the profile's "
                                "api_id. Nothing was launched")
        return api_id, None, ""
    if not entry_cli:
        return None, None, (f"a {harness or 'generic'} reviewer needs a roster channels.cli; the profile's "
                            "access.cli is never run for a reviewer. Nothing was launched")
    flag = bypass_flag(entry_cli)
    if flag:
        return None, None, (f"the reviewer's channels.cli passes {flag}, which lets it write or skips its "
                            f"permission checks; a reviewer runs read-only. Nothing was launched: {entry_cli}")
    return None, entry_cli, ""


def leaf_worktree(root: Path, t: ReviewTarget, explicit: Path | None = None) -> tuple[Path | None, str]:
    """``(path, error)``: where a reviewer runs, the worktree with the leaf's claimed branch checked out (``git
    worktree list``), never a checkout on the integration branch; ``explicit`` (``--worktree``) overrides."""
    if explicit is not None:
        return (explicit.resolve(), "") if explicit.is_dir() else (None, f"--worktree {explicit}: no such directory")
    branch = (t.entry or {}).get("branch")
    ok, out = git_ok(["worktree", "list", "--porcelain"], root) if branch else (False, "")
    path: Path | None = None
    for line in out.splitlines() if ok else []:
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path, ""
    codename = (t.entry or {}).get("codename") or "<codename>"
    return None, (f"no worktree has {branch or f'a claimed branch of {t.node_id}'} checked out, and a reviewer runs "
                  "in the leaf's own worktree, never in a checkout on the integration branch: pass --worktree PATH, "
                  f"or create it with `git worktree add work/.worktrees/{codename} {branch or '<branch>'}`")


def show_cli(prof: Profile | None, prompt_path: Path, entry_cli: str | None, harness: str | None,
             role: str | None) -> int:
    """``prompt --channel cli`` without ``--run``, any role but a reviewer's: print the command, start nothing."""
    level = prof.effort("reviewer" if role == "rca" else role) if prof and role else None
    cli, _effort, err = resolve_cli(prof, entry_cli, harness, level)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"would run: {cli} (prompt: {prompt_path}); add --run to launch it", file=sys.stderr)
    return 0


def show_reviewer(prof: Profile | None, prompt_path: Path, entry: dict[str, Any], model: str, reviews: Path,
                  cwd: Path) -> int:
    """``prompt --role reviewer --channel cli`` without ``--run``: print the command (less the output-schema flags
    a run adds) and where it would run; start nothing, file nothing."""
    api_id, cli, err = reviewer_command(prof, entry, model)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if cli is None:
        launch = ADAPTERS[entry["harness"]].reviewer_launch(prompt_path, api_id, reviews,
                                                            prof.effort("reviewer") if prof else None)
        cli = _shown(launch.argv) + (f" < {prompt_path}" if launch.stdin is not None else "")
    print(f"would run in {cwd}: {cli} (prompt: {prompt_path}); add --run to launch it and file its record",
          file=sys.stderr)
    return 0


def run_reviewer_channel(prof: Profile | None, prompt_path: Path, root: Path, entry: dict[str, Any], model: str,
                         reviews: Path, ref: str | None, transcript: list[str],
                         sign_key: Path | None = None, cwd: Path | None = None) -> Outcome:
    """``prompt --role reviewer --channel cli --run``: the roster ``entry``'s reviewer (:func:`reviewer_command`), run
    in ``cwd`` (the leaf's worktree: :func:`leaf_worktree`) and filed; every way out is an :class:`Outcome`, a rerun
    request (``exit`` 1, or the preflight's) when nothing could be sent."""
    rc = preflight(entry.get("preflight"), root)
    if rc:
        return Outcome("rerun", f"rerun requested: preflight failed (exit {rc}); nothing was sent", exit=rc)
    _api_id, cli, err = reviewer_command(prof, entry, model)
    if err:
        print(f"error: {err}", file=sys.stderr)
        transcript.append(f"error: {err}")
        return Outcome("rerun", f"rerun requested: {err}", exit=1)
    harness = entry.get("harness")
    level = prof.effort("reviewer") if prof else None
    if cli is None:
        return run_default_reviewer(prof, prompt_path, root, model, reviews, level, harness, ref, transcript,
                                    sign_key, cwd=cwd)
    cli, effort, err = resolve_cli(prof, cli, harness, level)
    if err:
        print(f"error: {err}", file=sys.stderr)
        transcript.append(f"error: {err}")
        return Outcome("rerun", f"rerun requested: {err}", exit=1)
    return run_custom_reviewer(prof, str(cli), prompt_path, root, model, reviews, ref, harness, effort, transcript,
                               sign_key, cwd=cwd)


def run_default_reviewer(prof: Profile | None, prompt_path: Path, root: Path, model: str | None, reviews: Path,
                         level: str | None, harness: str = "claude-code", ref: str | None = None,
                         transcript: list[str] | None = None, sign_key: Path | None = None,
                         cwd: Path | None = None) -> Outcome:
    """The harness's own read-only reviewer command (Claude Code bare, with ``--add-dir`` for the hand-off
    directory), its final JSON filed as the record (:func:`~specy_road.review_record_write.file_review`, signed
    with ``sign_key``). ``transcript`` collects the output for the run record (M11.72). The caller holds the
    leaf's run lock; the harness runs in ``cwd`` (default ``root``). Codex writes its answer (``-o``) to an :func:`answer_scratch` file outside the checked tree."""
    api_id = prof.api_id if prof is not None else model
    api_id = None if (api_id or "").strip().lower() in ("", "unknown") else api_id   # unknown: the harness default
    adapter = ADAPTERS[harness]
    session = (str(uuid.uuid4()), False) if harness == "claude-code" else None   # stream-json, to read the result
    with answer_scratch(str(model)) as out:
        launch = adapter.reviewer_launch(prompt_path, api_id, reviews, level, session=session,
                                         schema=write_schema(root, reviews, ref), output=out)
        if harness == "claude-code":
            launch = replace(launch, env={**(launch.env or {}), **CLAUDE_REVIEWER_AVOID_ENV})   # as `review delegate`'s
            print("note: the reviewer runs with --bare (no repository hooks, MCP servers or CLAUDE.md), and bare mode "
                  "never reads your subscription login: it needs ANTHROPIC_API_KEY (or an apiKeyHelper)",
                  file=sys.stderr)
        print(f"running: {_shown(launch.argv)}" + (f" < {prompt_path}" if launch.stdin is not None else ""),
              file=sys.stderr)
        return run_and_file(launch, adapter, root, str(model), reviews, ref, transcript, sign_key, out, cwd=cwd)


def run_custom_reviewer(prof: Profile | None, cli: str, prompt_path: Path, root: Path, model: str, reviews: Path,
                        ref: str | None, harness: str | None, effort: list[str],
                        transcript: list[str] | None = None, sign_key: Path | None = None,
                        cwd: Path | None = None) -> Outcome:
    """A roster ``channels.cli`` reviewer, run as written in ``cwd`` (default ``root``) plus its program's
    structured-output flags (:func:`reviewer_cli`), captured and filed like the default commands."""
    try:
        cli = reviewer_cli(cli, write_schema(root, reviews, ref))
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        if transcript is not None:
            transcript.append(f"error: {e}")
        return Outcome("rerun", f"rerun requested: {e}", exit=1)
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    launch = Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=effort)],
                    launch_mode=prof.launch_mode() if prof is not None else "full")
    return run_and_file(launch, ADAPTERS.get(harness or "generic", ADAPTERS["generic"]), root, model, reviews, ref,
                        transcript, sign_key, cwd=cwd)


def close_cli_review_run(root: Path, t: ReviewTarget, model: str, opened: tuple[Path, dict[str, Any]], filed: Outcome,
                         transcript: list[str]) -> None:
    """Finish ``prompt --channel cli``'s reviewer run record from its filing (an interrupt passes a rerun request):
    the transcript as the log, one attempt, and :func:`~specy_road.review_record_write.close_review_run`.

    ``opened`` is :func:`~specy_road.reviewer_run_failure.open_reviewer_cli_run`'s ``(path, record)``, kept in
    memory across the harness call. Nothing is read back from the run file, which sits in the reviewer's hand-off
    directory: the record is specy-road's own, and the log is always ``RUN-<model>.log`` beside it, never a path
    from file content."""
    path, run = opened
    replace_file(path.with_suffix(".log"), "\n".join(transcript) + ("\n" if transcript else ""))   # no symlink
    tail = [ln.strip() for ln in transcript[-20:] if ln.strip()]
    failed = filed.exit not in (0, None)
    run["attempts"] = [{"at": _now(), "exit": filed.exit, "capacity": bool(turn_capacity_error([], transcript)),
                        "error": None if filed.state == "recorded" else harness_error_line(
                            exit_code=filed.exit, errors=[], tail=tail, fallback=filed.reason)[:300] or None}]
    close_review_run(root, t, model, run, filed, reason=f"harness exited {filed.exit}" if failed else "",
                     tail=transcript)
    run["ended_at"] = _now()
    save_run(path, run)


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
