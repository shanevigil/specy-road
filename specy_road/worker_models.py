"""The model a worker's turn asked for and the one its harness reported, for the turn's ``usage`` event (M11.33).

A harness that routes models itself (Cursor's Auto, a cascade, its own critic) can run another model than the
``--model`` it was given. The wrapper records the ``--model`` on each ``launched`` event and the model the harness's
``system/init`` line names on its ``started`` event; the turn's ``usage`` event keeps both, and its summary, which
``worker sync`` prints, says when they differ (:func:`usage_event`). Split from :mod:`specy_road.worker_runner` for the file limit.

A custom command runs as ``sh -c <command>``; its model is read only when the command is one simple command and
the value is literal (:func:`command_model`): in a list or pipeline a ``--model`` can belong to another program than
the harness, and ``"${MODEL:-auto}"`` is whatever the shell expands it to.
The review gate reads a ``cursor`` entry's ``channels.cli`` the same way (``orchestration_config.entry_routing``).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from specy_road.model_names import roster_match, same_model
from specy_road.worker_adapter_parsers import _WORD, ROSTER_PRICED, model_from_argv, usage_text
from specy_road.worker_state import WorkerEvent

#: Spans ``sh`` reads literally: single-quoted, double-quoted without a substitution inside, a backslash escape.
_LITERAL = re.compile(r"""'[^']*'|"(?:[^"\\`$]|\\.|\$(?!\())*"|\\.""", re.S)
_REDIRECT_AMP = re.compile(r"[<>]&|&>")   # 2>&1, <&3, &>file: redirections, not a list or a background job
#: Outside those spans: a list, pipeline, background job, subshell, newline or command substitution.
_CONTROL = re.compile(r"[;&|()`\n]|\$\(")
#: A shell word the shell passes on unchanged: model-id characters, bare, single-quoted or in plain double quotes.
_LITERAL_WORD = re.compile(r"""(?:[\w.:/@+=,-]+|'[^']*'|"[\w.:/@+=,-]*")+""")


def command_model(command: str) -> str | None:
    """The ``--model`` / ``-m`` a shell command passes when it is one simple command (redirections allowed) and the
    value's shell word is literal, else ``None``: in ``printf --model x; agent -p {prompt}`` the flag never reaches
    the harness, and ``--model "$MODEL"`` passes whatever the shell expands, so the model is unknown."""
    if _CONTROL.search(_REDIRECT_AMP.sub(" ", _LITERAL.sub(" ", command))) or _WORD.sub("", command).strip():
        return None   # a list or pipeline, or an unbalanced quote
    raw = _WORD.findall(command)   # shell words, quotes kept
    try:
        words = [shlex.split(w)[0] for w in raw]
    except ValueError:   # a trailing backslash: the last word cannot be read
        return None
    model = model_from_argv(words)
    if not model:
        return None
    at = next(i for i, w in enumerate(words) if w in ("--model", "-m") or w.startswith("--model="))
    value = raw[at] if words[at].startswith("--model=") else raw[at + 1]
    return model if _LITERAL_WORD.fullmatch(value) else None


def launch_model(argv: list[str]) -> str | None:
    """The model a launch asks for: its argv's ``--model`` / ``-m``, else :func:`command_model` of the command a
    custom launch runs as ``sh -c <command>``."""
    model = model_from_argv(argv)
    if model or len(argv) != 3 or argv[:2] != ["sh", "-c"]:
        return model
    return command_model(argv[2])


def turn_models(events: list[WorkerEvent]) -> dict[str, str | None]:
    """``requested_model`` and ``observed_model`` from the events since the last ``launched``; ``None`` when unknown."""
    starts = [i for i, e in enumerate(events) if e.type == "launched"]
    turn = events[starts[-1]:] if starts else []
    requested = (turn[0].detail or {}).get("model") if turn else None
    observed = next((str(e.detail["model"]) for e in reversed(turn) if e.type == "started" and e.source == "worker"
                     and (e.detail or {}).get("model")), None)
    return {"requested_model": requested, "observed_model": observed}


def mismatch_note(detail: dict[str, Any], harness_model: object = None, profile: Any = None) -> str:
    """The summary suffix when both models are known and :func:`~specy_road.model_names.same_model` says they
    differ (Cursor's ``Composer 2.5`` is the ``composer-2.5`` it was told), else ``""``."""
    told, ran = detail.get("requested_model"), detail.get("observed_model")
    if not told or not ran or same_model(ran, told, harness_model, profile):
        return ""
    return f"; model mismatch: told {told}, harness reported {ran}"


def usage_event(repo_root: Path, detail: dict[str, Any]) -> dict[str, Any]:
    """The ``summary`` and ``detail`` of a turn's ``usage`` event (M15.19). The told model is compared with the
    reported one through its roster entry and profile; on a real mismatch a roster-price estimate is dropped,
    since it priced a model the harness did not run. A cost the harness reported is kept, estimate or not (Claude's
    ``total_cost_usd``): only :data:`~specy_road.worker_adapter_parsers.ROSTER_PRICED` marks a roster fill, and the
    marker is not stored."""
    detail = dict(detail)
    roster_priced = detail.pop(ROSTER_PRICED, None)
    told, ran = detail.get("requested_model"), detail.get("observed_model")
    entry, prof = roster_match(repo_root, str(told)) if told and ran else ({}, None)
    note = mismatch_note(detail, entry.get("harness_model"), prof)
    if note and roster_priced:
        detail.update(cost_usd=None, cost_is_estimate=None)
    return {"summary": f"usage: {usage_text(detail)}{note}", "detail": detail}
