"""The shared part of the harness adapters: launch and event types, the ``generic`` :class:`Adapter`, and the
custom-command and hand-off directory helpers every harness uses (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; its docstring describes the adapters and the
``channels.cli`` placeholders, and callers reach these names through that module.
"""

from __future__ import annotations

import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text
from specy_road.worker_adapter_parsers import _SESSION, _snip, _tokens, placeholder_problem, substitute_prompt


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


#: A model's own effort level as its harness's arguments; Cursor has no flag (its model ids carry the effort).
EFFORT_FLAGS = {"claude-code": lambda lv: ["--effort", lv], "codex": lambda lv: ["-c", f"model_reasoning_effort={lv}"]}
# `codex exec` has no --ask-for-approval (codex-cli 0.165): set both as config, which exec and resume take.
CODEX_POLICY = ("-c", "sandbox_mode=workspace-write", "-c", "approval_policy=never")
# A reviewer's turn writes nothing: specy-road files its record from the final JSON (review_record_write).
CODEX_REVIEW_POLICY = ("-c", "sandbox_mode=read-only", "-c", "approval_policy=never")
#: Claude Code's reviewer runs --bare, so no hook fires to stop these; the deny list does.
REVIEWER_DISALLOWED = ("Bash(git commit *)", "Bash(git push *)", "Bash(gh *)")
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


def _bare(launch_mode: str) -> list[str]:
    return ["--bare"] if launch_mode == "bare" else []


class Adapter:
    harness = "generic"
    caps = Capabilities(resume=False, interrupt=False, steer=False, handoff=False, events=False,
                        notes="runs the roster/profile cli; output lines become events, nothing else is known")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        why = placeholder_problem(cli)
        if why:
            raise Unsupported(f"generic harness needs a roster channels.cli or profile access.cli: {why}")
        self._session_flag_check(cli, {ph for _s, _e, ph, _p in _tokens(cli)})
        cli = reviews_dir_into(cli, repo_root, node_id)
        return Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=self.effort_flag(effort))])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None) -> Launch:
        raise Unsupported(f"{self.harness}: resume is not supported")

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None) -> Launch:
        """The harness's own read-only reviewer command; ``session`` is ``(id, resume)``, ``schema`` the review
        output schema file and ``output`` where a harness that can writes its final message. A ``generic`` entry
        has none: it runs its ``channels.cli`` and its final message is parsed as plain JSON."""
        raise Unsupported(f"{self.harness}: no default reviewer command; set the roster's channels.cli")

    def final_message(self, line: str) -> Any:
        """The reviewer's final answer when ``line`` carries one (a dict for harness-validated structured output,
        else the message text); ``None`` otherwise, and always for ``generic``, whose whole output is the message."""
        return None

    def parse(self, line: str) -> Parsed | None:
        raw = line.strip()
        if not raw:
            return None
        return Parsed("output", _snip(raw), detail={"message": raw})

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        """Every event one output line records; ``launch`` is the command that printed it."""
        parsed = self.parse(line)
        return [parsed] if parsed else []

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        raise Unsupported(f"{self.harness}: no native session to hand off")

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        """The arguments ``{session_flag}`` expands to; ``None`` where the harness has no such flag."""
        return None

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
        return Launch(["sh", "-c", substitute_prompt(cli, prompt_path, sid, flag, effort_args)], session_id=sid)
