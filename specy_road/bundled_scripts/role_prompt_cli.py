"""The commands ``specy-road prompt --channel cli`` runs (split from :mod:`role_prompt` for the file limit).

Nothing here runs without ``prompt --run`` (M15.3): without it ``prompt`` prints the command
(:func:`role_prompt.show_cli`, :func:`show_reviewer`) and starts no process. A reviewer's command comes from its roster entry
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
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.role_prompt_stream import stream_and_capture
from specy_road.git_subprocess import git_ok, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.model_profiles import Profile
from specy_road.orchestration_role_env import CLAUDE_REVIEWER_AVOID_ENV
from specy_road.review_record_write import (Outcome, answer_scratch, close_review_run, replace_file, run_and_file,
                                            write_schema)
from specy_road.review_files import project_of, reviews_dir
from specy_road.review_write_check import path_ancestor_link
from specy_road.review_model_check import resolve_effective_model
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target
from specy_road.reviewer_auth import claude_launch_decision, launch_note
from specy_road.reviewer_run_failure import _now, harness_error_line, save_run, turn_capacity_error
from specy_road.worker_adapter_base import checked, oversized_arg
from specy_road.worker_adapter_parsers import effort_note
from specy_road.worker_adapters import ADAPTERS, Launch, Unsupported, placeholder_problem, reviewer_cli, substitute_prompt

#: Reviewer harnesses whose default command specy-road launches, reads back and files from.
READ_BACK_HARNESSES = ("claude-code", "codex", "cursor")
#: Flags that let a harness write or skip its permission prompts; a reviewer command carrying one is refused.
BYPASS_FLAGS = ("--force", "--yolo", "--dangerously-skip-permissions")
#: The mode ``run_default_reviewer`` chose, read by :func:`close_cli_review_run` after the caller returns.
_run_launch_mode: ContextVar[str | None] = ContextVar("specy_road_claude_reviewer_launch_mode", default=None)


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


def bypass_problem(cli: str) -> str:
    """Why the reviewer command ``cli`` may not run, else ``""``: it passes one of :data:`BYPASS_FLAGS`.

    One bounded rule: ``cli`` is split as ``sh`` reads its words, erring towards seeing more. Every backslash-newline
    (``sh``'s line continuation) is removed first, so ``--for\\<newline>ce`` is ``--force``. The rest is split by
    :class:`shlex.shlex` in POSIX mode with ``punctuation_chars`` and no comment character, so ``;``, ``&``, ``|``,
    ``(``, ``)``, ``<`` and ``>`` are tokens of their own (``--force;``, ``--force&&x`` and ``(--force)`` all yield
    ``--force``), quotes are removed (``'--force'`` is ``--force``, as the program receives it), and ``#`` is an
    ordinary character (``a#b --force`` keeps its ``--force``). A token matches when it, or its part before the first
    ``=``, is exactly one of the flags. A quoted argument that only contains a flag among other text (``"use --force
    here"``) is one token and does not match. Conservative by design: a flag in a ``#`` comment, or a backslash-newline
    inside single quotes (where ``sh`` keeps it), also refuses. Out of scope, because the tokenizer does not expand
    them: flags produced by the shell at run time (``$VAR``, ``$'...'``, ``$(...)``, backquotes, brace expansion,
    aliases, a script the command runs). A command the tokenizer cannot split (an unbalanced quote) is refused."""
    lexer = shlex.shlex(cli.replace("\\\n", ""), posix=True, punctuation_chars=True)
    lexer.whitespace_split, lexer.commenters = True, ""
    try:
        words = list(lexer)
    except ValueError as e:
        return f"the reviewer's channels.cli cannot be split into words ({e}), so it cannot be checked: {cli}"
    flag = next((w.split("=", 1)[0] for w in words if w.split("=", 1)[0] in BYPASS_FLAGS), None)
    if flag:
        return (f"the reviewer's channels.cli passes {flag}, which lets it write or skips its permission checks; "
                f"a reviewer runs read-only: {cli}")
    return ""


def model_problem(prof: Profile | None, entry: dict[str, Any]) -> tuple[str | None, str]:
    """``(model id, error)``: the effective model a reviewer's harness is told for roster ``entry``
    (:func:`~specy_road.review_model_check.resolve_effective_model`), or why there is none (empty or ``unknown``,
    whether from ``harness_model``, the profile's ``api_id`` or the ``id``: the harness would run some default model
    under this roster id). Every reviewer path that shows or launches a command takes its model from here:
    :func:`reviewer_command` and :func:`run_default_reviewer`."""
    model = resolve_effective_model(entry, prof)
    if model is None:
        return None, (f"{entry.get('id')!r} resolves to no API model id (its harness_model, else its profile's "
                      "api_id, else its id is empty or unknown), so the harness would run some other model under this "
                      "roster id; set the roster entry's harness_model or the profile's api_id")
    return model, ""


def reviewer_command(prof: Profile | None, entry: dict[str, Any], model: str) -> tuple[str | None, str | None, str]:
    """``(api id, custom cli, error)`` for the roster ``entry``'s reviewer, from the entry only: a claude-code, codex
    or cursor entry without ``channels.cli`` runs its adapter's read-only command with the entry's model, any other
    entry its ``channels.cli``. Refused (``error``, nothing launched) by :func:`model_problem` on every path and
    :func:`bypass_problem` on a ``channels.cli``. The profile's ``access.cli`` is never used: it is an example,
    often with ``--force`` and no ``--model``."""
    harness, entry_cli = entry.get("harness"), (entry.get("channels") or {}).get("cli")
    api_id, err = model_problem(prof, entry)
    if not err and not entry_cli and harness not in READ_BACK_HARNESSES:
        err = (f"a {harness or 'generic'} reviewer needs a roster channels.cli; the profile's access.cli is never "
               "run for a reviewer")
    err = err or (bypass_problem(entry_cli) if entry_cli else "")
    if err:
        return None, None, f"{err}. Nothing was launched"
    return api_id, entry_cli or None, ""


def worktree_problem(root: Path, path: Path, t: ReviewTarget) -> str:
    """Why a reviewer may not run in ``path``, else ``""``: it must be the top of a git checkout, must not have the
    integration branch checked out, and, when the leaf has a claimed branch, must have its ``HEAD`` at that branch's
    tip. Both an explicit ``--worktree`` and the one :func:`leaf_worktree` finds are checked."""
    top = git_text(["rev-parse", "--show-toplevel"], path) if path.is_dir() else None
    if not top or Path(top).resolve() != path.resolve():
        return f"{path} is not the top of a git checkout"
    base = resolve_integration_defaults(root, explicit_base=None, explicit_remote=None)[0]
    if git_text(["branch", "--show-current"], path) == base:
        return f"{path} has the integration branch {base} checked out, and a reviewer never runs there"
    branch = (t.entry or {}).get("branch")
    tip = git_text(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"], root) if branch else None
    if branch and (not tip or git_text(["rev-parse", "HEAD"], path) != tip):
        return f"{path} is not at the tip of the leaf's claimed branch {branch}"
    return ""


def leaf_worktree(root: Path, t: ReviewTarget, explicit: Path | None = None) -> tuple[Path | None, str]:
    """``(path, error)``: where a reviewer runs, the worktree with the leaf's claimed branch checked out (``git
    worktree list``), or ``explicit`` (``--worktree``); either must pass :func:`worktree_problem`."""
    path = explicit.resolve() if explicit is not None else _claimed_worktree(root, (t.entry or {}).get("branch"))
    if path is None:
        branch, codename = (t.entry or {}).get("branch"), (t.entry or {}).get("codename") or "<codename>"
        return None, (f"no worktree has {branch or f'a claimed branch of {t.node_id}'} checked out, and a reviewer "
                      "runs in the leaf's own worktree, never in a checkout on the integration branch: pass "
                      f"--worktree PATH, or create it with `git worktree add work/.worktrees/{codename} "
                      f"{branch or '<branch>'}`")
    err = worktree_problem(root, path, t)
    return (None, f"{'--worktree ' if explicit is not None else ''}{err}") if err else (path, "")


def _claimed_worktree(root: Path, branch: str | None) -> Path | None:
    """The worktree ``git worktree list`` shows with ``branch`` checked out, else ``None``."""
    ok, out = git_ok(["worktree", "list", "--porcelain"], root) if branch else (False, "")
    path: Path | None = None
    for line in out.splitlines() if ok else []:
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path
    return None


def show_reviewer(prof: Profile | None, prompt_path: Path, entry: dict[str, Any], model: str, reviews: Path,
                  cwd: Path | None) -> int:
    """``prompt --role reviewer --channel cli`` without ``--run``: print the command (less the output-schema flags
    a run adds) and where it would run; start nothing, file nothing."""
    api_id, cli, err = reviewer_command(prof, entry, model)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if cli is None:
        mode = (claude_launch_decision(entry, prof.launch_mode() if prof is not None else None)[0]
                if entry["harness"] == "claude-code" else None)   # the mode a run would choose; --run refuses a problem
        launch = ADAPTERS[entry["harness"]].reviewer_launch(prompt_path, api_id, reviews,
                                                            prof.effort("reviewer") if prof else None,
                                                            harness_bin=entry.get("harness_bin"),
                                                            **({"mode": mode} if mode else {}))
        cli = _shown(launch.argv) + (f" < {prompt_path}" if launch.stdin is not None else "")
    print(f"would run in {cwd or 'the leaf worktree (none found)'}: {cli} (prompt: {prompt_path}); add --run to launch it and file its record",
          file=sys.stderr)
    return 0


def reviewer_launch_block(prof: Profile | None, entry: dict[str, Any], _root: Path) -> Outcome | None:
    """Forced-bare authentication, or ``None``. Writes nothing.

    This is the only refusal that runs before the RUN record. A roster ``preflight`` stays in
    :func:`run_reviewer_channel`, after ``prompt --channel cli`` has opened that record (M8.3). ``_root`` is
    unused; the decision reads the reviewer environment, not the checkout.
    """
    harness, entry_cli = entry.get("harness"), (entry.get("channels") or {}).get("cli")
    if harness != "claude-code" or entry_cli:
        return None
    problem = claude_launch_decision(entry, prof.launch_mode() if prof is not None else None)[1]
    if not problem:
        return None
    print(f"error: {problem}", file=sys.stderr)
    return Outcome("rerun", problem, exit=1)


def run_reviewer_channel(prof: Profile | None, prompt_path: Path, root: Path, entry: dict[str, Any], model: str,
                         reviews: Path, ref: str | None, transcript: list[str],
                         sign_key: Path | None = None, cwd: Path | None = None) -> Outcome:
    """``prompt --role reviewer --channel cli --run``: the roster ``entry``'s reviewer (:func:`reviewer_command`), run
    in ``cwd`` (the leaf's worktree: :func:`leaf_worktree`) and filed; every way out is an :class:`Outcome`, a rerun
    request (``exit`` 1, or the preflight's) when nothing could be sent.

    Forced-bare authentication is :func:`reviewer_launch_block`, which ``prompt`` runs before it opens the RUN
    record. The roster ``preflight`` stays here, after that record exists."""
    _run_launch_mode.set(None)
    rc = preflight(entry.get("preflight"), root)
    if rc:
        return Outcome("rerun", f"rerun requested: preflight failed (exit {rc}); nothing was sent", exit=rc)
    _api_id, cli, err = reviewer_command(prof, entry, model)
    if err:
        return _refused(err, transcript)
    harness = entry.get("harness")
    level = prof.effort("reviewer") if prof else None
    if cli is None:
        return run_default_reviewer(prof, prompt_path, root, model, reviews, level, harness, ref, transcript,
                                    sign_key, entry, cwd=cwd, harness_bin=entry.get("harness_bin"))
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
                         entry: dict[str, Any] | None = None, *, cwd: Path | None = None,
                         harness_bin: str | None = None) -> Outcome:
    """The harness's own read-only reviewer command (Claude Code bare or explicit, with ``--add-dir`` for the
    hand-off directory), its final JSON filed as the record (:func:`~specy_road.review_record_write.file_review`,
    signed with ``sign_key``). ``harness_bin`` is the roster entry's, which the adapter resolves (harness_binary).
    ``transcript`` collects the output for the run record (M11.72). The caller holds the leaf's run lock; the
    harness runs in ``cwd`` (default ``root``). Codex writes its answer (``-o``) to an :func:`answer_scratch` file
    outside the checked tree. ``entry`` is the roster row, when the caller has it, so a row that forces bare is
    refused here too."""
    api_id, err = model_problem(prof, entry or {"id": model})   # the same resolution as the preview and the refusal
    if err:
        return _refused(f"{err}. Nothing was launched", transcript)
    adapter = ADAPTERS[harness]
    session = (str(uuid.uuid4()), False) if harness == "claude-code" else None   # stream-json, to read the result
    mode: str | None = None
    if harness == "claude-code":
        mode, problem = claude_launch_decision(entry, prof.launch_mode() if prof is not None else None)
        if problem:   # a direct caller (the channel refuses first): still no launch
            print(f"error: {problem}", file=sys.stderr)
            return Outcome("rerun", problem, exit=1)
        _run_launch_mode.set(mode)
    with answer_scratch(str(model)) as out:
        try:
            extra = {"mode": mode} if mode is not None else {}
            launch = adapter.reviewer_launch(prompt_path, api_id, reviews, level, session=session,
                                             schema=write_schema(root, reviews, ref), output=out,
                                             harness_bin=harness_bin, **extra)
        except Unsupported as e:   # HarnessNotFound: the dirs searched, before anything runs
            return _refused(str(e), transcript)
        if harness == "claude-code":
            launch = replace(launch, env={**(launch.env or {}), **CLAUDE_REVIEWER_AVOID_ENV})   # as `review delegate`'s
            print(launch_note(mode or "bare"), file=sys.stderr)
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
        launch = checked(Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=effort)],   # A2: before exec
                                launch_mode=prof.launch_mode() if prof is not None else "full"))
    except Unsupported as e:
        return _refused(str(e), transcript)
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    return run_and_file(launch, ADAPTERS.get(harness or "generic", ADAPTERS["generic"]), root, model, reviews, ref,
                        transcript, sign_key, cwd=cwd)


def _refused(why: str, transcript: list[str] | None) -> Outcome:
    """A reviewer launch refused before anything ran: the reason printed and transcribed, and a rerun request."""
    print(f"error: {why}", file=sys.stderr)
    if transcript is not None:
        transcript.append(f"error: {why}")
    return Outcome("rerun", f"rerun requested: {why}", exit=1)


def reviewer_turn(prof: Profile | None, out: Path, root: Path, entry: dict[str, Any], model: str, node_id: str,
                  ref: str | None, worktree: Path | None, sign_key: Path | None, *, run: bool) -> int:
    """``prompt --role reviewer --channel cli`` after the prompt is written (moved from ``role_prompt._run`` for the
    file limit): the leaf's worktree (:func:`leaf_worktree`) and command (:func:`reviewer_command`), refused before
    any run record or process; without ``run`` the command shown (:func:`show_reviewer`), with it the turn run, filed
    and its run record closed from the filing. The exit code."""
    from specy_road.reviewer_run_failure import open_reviewer_cli_run
    try:
        reviewer_target = resolve_target(root, node_id, ref)
    except ReviewTargetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    cwd, where = leaf_worktree(root, reviewer_target, worktree)
    if not run:   # the preview always shows the command; the worktree is enforced only for a launch
        rc = show_reviewer(prof, out, entry, model, reviews_dir(root, node_id), cwd)
        if rc == 0 and where:
            print(f"note: --run would refuse: {where}", file=sys.stderr)
        return rc
    err = where or reviewer_command(prof, entry, model)[2]   # refused before any run record or process
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    reviewer_run = open_reviewer_cli_run(root, reviewer_target, model, entry.get("harness"))
    transcript: list[str] = []
    try:   # the run record is closed from the filing outcome, an interrupt's included: never from older records
        filed = run_reviewer_channel(prof, out, root, entry, model, reviews_dir(root, node_id), ref,
                                     transcript, sign_key, cwd=cwd)
    except BaseException as e:
        close_cli_review_run(root, reviewer_target, model, reviewer_run,
                             Outcome("rerun", f"interrupted: {e or type(e).__name__}", exit=None), transcript)
        raise
    close_cli_review_run(root, reviewer_target, model, reviewer_run, filed, transcript)
    return filed.exit or (0 if filed.state == "recorded" else 1)


def close_cli_review_run(root: Path, t: ReviewTarget, model: str, opened: tuple[Path, dict[str, Any]], filed: Outcome,
                         transcript: list[str]) -> None:
    """Finish ``prompt --channel cli``'s reviewer run record from its filing (an interrupt passes a rerun request):
    the transcript as the log, one attempt, and :func:`~specy_road.review_record_write.close_review_run`.

    ``opened`` is :func:`~specy_road.reviewer_run_failure.open_reviewer_cli_run`'s ``(path, record)``, kept in
    memory across the harness call. Nothing is read back from the run file, which sits in the reviewer's hand-off
    directory: the record is specy-road's own, and the log is always ``RUN-<model>.log`` beside it, never a path
    from file content."""
    path, run = opened
    if path_ancestor_link(project_of(path), path) is not None:   # planted during the run: do not write the log or the record
        _run_launch_mode.set(None)
        return
    _finish_cli_review_run(root, t, model, path, run, filed, transcript)


def _finish_cli_review_run(root: Path, t: ReviewTarget, model: str, path: Path, run: dict[str, Any], filed: Outcome,
                           transcript: list[str]) -> None:
    """Write the prompt run's log and close its record. The caller has already checked every ancestor from the owned root."""
    mode = _run_launch_mode.get()
    _run_launch_mode.set(None)
    if mode:
        run["launch_mode"] = mode
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
        why = oversized_arg(["sh", "-c", cmd])   # A2: refused before exec, never Errno 7 from the shell
        if why:
            print(f"error: {why}", file=sys.stderr)
            if transcript is not None:
                transcript.append(f"error: {why}")
            return 1
        if transcript is None:
            return subprocess.run(cmd, shell=True, cwd=root, check=False).returncode
        return stream_and_capture(cmd, cwd=root, transcript=transcript, shell=True)
    except OSError as e:   # E2BIG: "<prompt>" puts the whole text on the command line
        print(f"error: could not launch the cli: {e.strerror}; if the prompt is too long for a command line, "
              'use {prompt} (its file path) instead of "<prompt>"', file=sys.stderr)
        if transcript is not None:
            transcript.append(f"error: could not launch the cli: {e.strerror}")
        return 1
