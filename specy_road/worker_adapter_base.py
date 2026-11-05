"""The shared part of the harness adapters: launch and event types, the ``generic`` :class:`Adapter`, and the
custom-command and hand-off directory helpers every harness uses (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; its docstring describes the adapters and the
``channels.cli`` placeholders, and callers reach these names through that module.
"""

from __future__ import annotations

import shlex
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text
from specy_road.worker_adapter_parsers import (
    _SESSION,
    _json,
    _snip,
    _tokens,
    apply_roster_price_estimate,
    model_from_argv,
    placeholder_problem,
    project_root_from_worktree,
    substitute_prompt,
    worktree_from_argv,
)


@dataclass(frozen=True)
class Capabilities:
    resume: bool
    interrupt: bool
    steer: bool
    handoff: bool
    events: bool
    notes: str


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    stdin: str | None = None        # prompt text piped in, when the CLI reads it that way
    session_id: str | None = None   # chosen up front, when the harness lets the caller pick
    launch_mode: str = "full"       # the profile's access.launch_mode, checked against what the harness reports
    env: dict[str, str] | None = None   # set in the harness's environment on top of the wrapper's (Codex: CODEX_HOME)


@dataclass(frozen=True)
class Parsed:
    """One output line turned into an event: ``type`` is a worker-event type."""
    type: str
    summary: str
    session_id: str | None = None
    detail: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None   # a turn end's token counts and cost (:func:`usage_fields`); the wrapper logs them


class Unsupported(Exception):
    """The adapter declares this operation unsupported for its harness."""


#: What a harness is told when the prompt itself travels on stdin: an argv string is capped at 128 KiB on Linux.
STDIN_INSTRUCTION = "The task is the text on standard input. Follow it exactly; it is the whole prompt."
#: The program each harness's default command runs; a resolved ``harness_bin`` path replaces it (harness_binary).
PROGRAMS = {"claude-code": "claude", "codex": "codex", "cursor": "agent"}
#: The OS limit on one argument (Linux ``MAX_ARG_STRLEN``, its terminating NUL included): above it exec fails with
#: Errno 7 (E2BIG), which a shell reports as exit 126 or 127.
ARG_LIMIT = 128 * 1024


def file_instruction(prompt_path: Path) -> str:
    """What a harness that takes its prompt only as an argument (Cursor's ``agent -p``) is told instead of the
    prompt: the file to read, so the argument stays short whatever the prompt's size."""
    return (f"The task is the text of the file {prompt_path}. Read all of it before anything else and follow it "
            "exactly; it is the whole prompt.")


def oversized_arg(argv: list[str]) -> str | None:
    """Why ``argv`` cannot be exec'd (an argument over :data:`ARG_LIMIT`), naming the fix; ``None`` when it can."""
    size = max((len(a.encode("utf-8")) + 1 for a in argv), default=0)
    if size <= ARG_LIMIT:
        return None
    return (f"the launch command has a {size // 1024} KiB argument, over the OS limit of {ARG_LIMIT // 1024} KiB for "
            'one argument: its "<prompt>" puts the prompt text on the command line; use {prompt} (the prompt '
            "file's path, e.g. `< {prompt}`) instead")


def checked(launch: Launch) -> Launch:
    """``launch``, refused (:class:`Unsupported`) before exec when :func:`oversized_arg` says it cannot run."""
    why = oversized_arg(launch.argv)
    if why:
        raise Unsupported(why)
    return launch


#: A model's own effort level as its harness's arguments; Cursor has no flag (its model ids carry the effort).
EFFORT_FLAGS = {"claude-code": lambda lv: ["--effort", lv], "codex": lambda lv: ["-c", f"model_reasoning_effort={lv}"]}
# `codex exec` has no --ask-for-approval (codex-cli 0.165): set both as config, which exec and resume take.
CODEX_POLICY = ("-c", "sandbox_mode=workspace-write", "-c", "approval_policy=never")
# A reviewer's turn writes nothing: specy-road files its record from the final JSON (review_record_write).
CODEX_REVIEW_POLICY = ("-c", "sandbox_mode=read-only", "-c", "approval_policy=never")
#: Claude Code's reviewer runs --bare, so no hook fires to stop these; the deny list does.
REVIEWER_DISALLOWED = ("Bash(git commit *)", "Bash(git push *)", "Bash(gh *)")
#: A reviewer writes nothing (M8.3 A2): its read and shell tools only, and the file-writing tools denied outright.
REVIEWER_TOOLS = "Read,Glob,Grep,Bash"
REVIEWER_NO_WRITES = ("Write", "Edit", "NotebookEdit")
# Antigravity's `agy` runs as a `generic` harness (docs/design-notes/harness-compatibility-triage.md); a reviewer turn
# needs these, each added when the command lacks it (https://antigravity.google/docs/cli/headless): one JSON envelope
# whose structured_output is the answer, the terminal sandbox, and more than the 5m default to answer in.
AGY_REVIEW_FLAGS = (("--output-format", "json"), ("--sandbox", None), ("--print-timeout", "30m"))
REVIEWS_DIR = "{reviews_dir}"   # a custom command's writable root (module docstring)


def _model_flag(flag: str, model: str | None) -> list[str]:
    """No model means the harness's own default (a profile whose ``api_id`` is ``unknown``)."""
    return [flag, model] if model else []


def linked_worktree(worktree: Path) -> bool:
    """True when ``worktree`` is a linked checkout, not the repository's main worktree."""
    common = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], worktree)
    gitdir = git_text(["rev-parse", "--path-format=absolute", "--git-dir"], worktree)
    return bool(common and gitdir and Path(common).name == ".git" and Path(gitdir) != Path(common))


def _reviews_handoff_dir(repo_root: Path, node_id: str) -> Path:
    from specy_road.review_files import reviews_dir  # noqa: PLC0415 — keeps adapter import graph small
    return reviews_dir(repo_root, node_id)


def reviews_dir_into(cli: str, repo_root: Path | None, node_id: str | None) -> str:
    """``{reviews_dir}`` → the quoted hand-off directory, whole words only (as :func:`placeholder_problem` has the
    others), so a custom command can make it a writable root; run after that check, before :func:`substitute_prompt`."""
    words = [(s, e) for s, e, _ph, _p in _tokens(cli) if REVIEWS_DIR in cli[s:e]]
    whole = (REVIEWS_DIR, f'"{REVIEWS_DIR}"', f"'{REVIEWS_DIR}'")
    if words and (not repo_root or not node_id or any(cli[s:e] not in whole for s, e in words)):
        raise Unsupported(f"channels.cli: {REVIEWS_DIR} must be a whole argument, bare or in one pair of quotes, "
                          f"and needs the leaf's id and project root: {cli}")
    for s, e in reversed(words):
        cli = cli[:s] + shlex.quote(str(_reviews_handoff_dir(repo_root, node_id))) + cli[e:]
    return cli


def reviewer_cli(cli: str, schema: Path | None) -> str:
    """A custom reviewer command with the structured-output flags its program takes. For Antigravity (``agy``):
    ``--json-schema <schema file>`` and :data:`AGY_REVIEW_FLAGS`, each only when absent, right after the program;
    ``--dangerously-skip-permissions`` (auto-approve every tool) is refused. Any other program is left as written."""
    try:
        words = shlex.split(cli)
    except ValueError:   # unbalanced quotes: placeholder_problem reports the command as it is
        return cli
    if not words or Path(words[0]).name != "agy":
        return cli
    if "--dangerously-skip-permissions" in words:
        raise Unsupported(f"an agy reviewer must not pass --dangerously-skip-permissions: {cli}")
    named = {w.split("=", 1)[0] for w in words}
    add = [] if not schema or "--json-schema" in named else ["--json-schema", shlex.quote(str(schema))]
    for flag, value in AGY_REVIEW_FLAGS:
        add += [flag, *([value] if value else [])] if flag not in named else []
    end = _program_end(cli)
    return cli[:end] + "".join(f" {a}" for a in add) + cli[end:] if add else cli


def _program_end(cli: str) -> int:
    """Where ``cli``'s first shell word ends, read as :func:`shlex.split` reads it: whitespace inside quotes or
    after a backslash belongs to the word, so a quoted program path with spaces stays whole."""
    i, quote = len(cli) - len(cli.lstrip()), None
    while i < len(cli) and (quote or not cli[i].isspace()):
        if cli[i] == "\\" and quote != "'":
            i += 1
        elif cli[i] == quote:
            quote = None
        elif not quote and cli[i] in "'\"":
            quote = cli[i]
        i += 1
    return min(i, len(cli))


def _bare(launch_mode: str) -> list[str]:
    return ["--bare"] if launch_mode == "bare" else []


class Adapter:
    harness = "generic"
    caps = Capabilities(resume=False, interrupt=False, steer=False, handoff=False, events=False,
                        notes="runs the roster/profile cli; output lines become events, nothing else is known")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        why = placeholder_problem(cli)
        if why:
            raise Unsupported(f"generic harness needs a roster channels.cli or profile access.cli: {why}")
        self._session_flag_check(cli, {ph for _s, _e, ph, _p in _tokens(cli)})
        cli = reviews_dir_into(cli, repo_root, node_id)
        return checked(Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=self.effort_flag(effort))]))

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        raise Unsupported(f"{self.harness}: resume is not supported")

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, harness_bin: str | None = None) -> Launch:
        """The harness's own read-only reviewer command; ``session`` is ``(id, resume)``, ``schema`` the review
        output schema file and ``output`` where a harness that can writes its final message. A ``generic`` entry
        has none: it runs its ``channels.cli`` and its final message is parsed as plain JSON. ``harness_bin``, on
        every adapter's default command, is the resolved binary (:func:`specy_road.harness_binary.resolve`) that
        replaces the program name (:meth:`_program`)."""
        raise Unsupported(f"{self.harness}: no default reviewer command; set the roster's channels.cli")

    def parse(self, line: str) -> Parsed | None:
        raw = line.strip()
        if not raw:
            return None
        return Parsed("output", _snip(raw), detail={"message": raw})

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        """Every event one output line records; ``launch`` is the command that printed it."""
        parsed = self.parse(line)
        if not parsed or parsed.usage is None or parsed.usage.get("cost_usd") is not None:
            return [parsed] if parsed else []
        model = model_from_argv(launch.argv)
        if not model:
            return [parsed]
        usage = apply_roster_price_estimate(
            parsed.usage, model, project_root_from_worktree(worktree_from_argv(launch.argv)))
        return [parsed] if usage is parsed.usage else [replace(parsed, usage=usage)]

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        raise Unsupported(f"{self.harness}: no native session to hand off")

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        """The arguments ``{session_flag}`` expands to; ``None`` where the harness has no such flag."""
        return None

    def _program(self, harness_bin: str | None) -> str:
        """``argv[0]`` of the default command: the caller's resolved ``harness_bin``, else the binary found on
        ``PATH`` or in the harness's install directories (a caller that has no roster entry, e.g. a resume)."""
        if harness_bin:
            return harness_bin
        from specy_road.harness_binary import resolve  # noqa: PLC0415 — harness_binary imports this module
        return resolve(self.harness)

    def effort_flag(self, level: str | None) -> list[str]:
        """The arguments ``{effort}`` expands to for the model's own ``level``; none where the harness has no flag."""
        return EFFORT_FLAGS[self.harness](level) if level and self.harness in EFFORT_FLAGS else []

    def _session_flag_check(self, cli: str, named: set[str | None]) -> None:
        if "{session_flag}" in named and self.session_flag("", False) is None:
            raise Unsupported(f"channels.cli: {{session_flag}} is defined only for claude-code, not {self.harness}; "
                              f"use {{session}} with the harness's own flag: {cli}")

    def _add_dir(self, worktree: Path, repo_root: Path | None, node_id: str | None) -> list[str]:
        """``--add-dir`` with the hand-off directory, in a linked worktree only: Claude Code, ``codex exec`` and
        Cursor ``agent`` take it (model-profiles/harness-captures); ``codex exec resume`` documents none."""
        if not repo_root or not node_id or not linked_worktree(worktree):
            return []
        return ["--add-dir", str(_reviews_handoff_dir(repo_root, node_id))]

    def _custom(self, cli: str | None, prompt_path: Path, session_id: str | None = None,
                effort: str | None = None, *, node_id: str | None = None, repo_root: Path | None = None) -> Launch | None:
        """The roster's own command, when it has the placeholders this call needs.

        ``{prompt}`` is the prompt file path; ``{session}`` (optional) is the native session id and ``{session_flag}``
        the harness's argument for it (:meth:`session_flag`); ``{effort}`` is :meth:`effort_flag`; ``{reviews_dir}`` is
        :func:`reviews_dir_into`. A resume uses the custom command only when it names a session placeholder, since
        otherwise the default command is the only one that knows the harness's resume flag.
        """
        if not cli:
            return None
        why = placeholder_problem(cli)
        if why:
            # Never fall back to the vendor default: that would silently widen (or change) the adopter's permissions.
            raise Unsupported(f"channels.cli / access.cli: {why}: {cli}")
        named = {ph for _s, _e, ph, _p in _tokens(cli)}
        self._session_flag_check(cli, named)
        if session_id is not None and not named & _SESSION:
            return None
        # On launch a command naming {session} gets a fresh id the record keeps, so it serves `message` / `resume` too.
        sid = session_id if session_id is not None else (str(uuid.uuid4()) if named & _SESSION else None)
        flag = self.session_flag(sid, session_id is not None) if "{session_flag}" in named else None
        effort_args = self.effort_flag(effort)
        cli = reviews_dir_into(cli, repo_root, node_id)
        return checked(Launch(["sh", "-c", substitute_prompt(cli, prompt_path, sid, flag, effort_args)], session_id=sid))
