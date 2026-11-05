"""Harness adapters: how a worker is launched, resumed, read, and handed to a human (slice 7b).

One adapter per harness the roster may name (``claude-code``, ``codex``, ``cursor``, ``generic``). Each builds
the documented one-shot command of its CLI (verified against the vendors' docs on 2026-10-27, see
``docs/design-notes/v0-3-1-worker-orchestration.md`` D2), turns the CLI's JSON output lines into worker events,
and says which of the lifecycle operations it supports. What it does not support is declared, never emulated:
a one-shot CLI has no interrupt short of killing the process, so ``interrupt`` is ``False`` and the command says
so, rather than a kill being dressed up as one. The long-lived protocols (Codex app-server, Cursor ACP) are the
later adapters that turn those flags on.

A roster entry's ``channels.cli`` (``{prompt}`` = prompt file path) replaces the built command for any harness
while its output is still parsed as that harness's; that is how an adopter widens or narrows permissions, pins
flags, or points at a wrapper. ``{session_flag}`` is the harness's own session argument, so one command serves
launch and resume (Claude Code: ``--session-id <id>`` on launch, ``--resume <id>`` on resume); where the harness's
resume is its own command (Codex, Cursor), ``channels.cli_resume`` naming ``{session}`` is what message and resume
run instead, so they keep the launch's permissions; ``{effort}`` is
its flag for the profile's executor effort (empty on Cursor), which the default commands carry too;
``{reviews_dir}`` is the main checkout's ``work/reviews/<ID>``, for the harness's writable-root flag, which the
default commands pass in a linked worktree. Claude Code's default asks for the narrowest mode that lets it edit
unattended (``acceptEdits``; ``dontAsk`` is stricter but denies every tool not allow-listed), so a first run may
have shell commands denied (under ``-p`` a denial does not stop the run; it is listed in ``permission_denials``);
Cursor's ``agent -p`` has write and shell tools already and ``--force`` force-allows every command not explicitly
denied, so that default is the widest — read the table in ``docs/orchestration-workers.md`` before trusting either
on a new repo.

A reviewer gets its own command (:meth:`Adapter.reviewer_launch`), read-only on every harness that has one:
Claude Code ``--bare`` with ``--disallowedTools`` for ``Write``, ``Edit``, ``NotebookEdit``, commits, pushes and
``gh``; Codex ``sandbox_mode=read-only``;
Cursor ``--mode ask --trust`` without ``--force``. Its final message is the review as JSON: :func:`specy_road.review_answer.final_answer` reads it by the
harness's row of :data:`~specy_road.review_answer.TURNS`, and :mod:`specy_road.review_record_write` files it as the record. A reviewer's
custom command goes through :func:`reviewer_cli`, which gives Antigravity's ``agy`` (a ``generic`` harness) its
``--json-schema`` and read-only flags.
"""

from __future__ import annotations

from specy_road.worker_adapter_base import (  # re-exported
    CODEX_POLICY,
    CODEX_REVIEW_POLICY,
    EFFORT_FLAGS,
    AGY_REVIEW_FLAGS,
    REVIEWER_DISALLOWED,
    REVIEWER_NO_WRITES,
    REVIEWER_TOOLS,
    REVIEWS_DIR,
    STDIN_INSTRUCTION,
    Adapter,
    Capabilities,
    Launch,
    Parsed,
    Unsupported,
    _bare,
    _model_flag,
    _reviews_handoff_dir,
    linked_worktree,
    reviewer_cli,
    reviews_dir_into,
)
from specy_road.worker_adapter_claude import ClaudeCode
from specy_road.worker_adapter_codex import Codex
from specy_road.worker_adapter_cursor import Cursor
from specy_road.worker_adapter_parsers import (_SESSION, _init_detail, _json, _snip, _text, _tokens,  # re-exported
                                                placeholder_problem, substitute_prompt, usage_fields)
from specy_road.worker_state import HARNESSES


ADAPTERS: dict[str, Adapter] = {a.harness: a for a in (Adapter(), ClaudeCode(), Codex(), Cursor())}
assert set(ADAPTERS) == set(HARNESSES)


def adapter_for(harness: str) -> Adapter:
    try:
        return ADAPTERS[harness]
    except KeyError:
        raise Unsupported(f"unknown harness {harness!r}; expected one of {', '.join(HARNESSES)}") from None
