"""The model a worker's turn asked for and the one its harness reported, for the turn's ``usage`` event (M11.33).

A harness that routes models itself (Cursor's Auto, a cascade, its own critic) can run another model than the
``--model`` it was given. The wrapper records the ``--model`` on each ``launched`` event and the model the harness's
``system/init`` line names on its ``started`` event; the turn's ``usage`` event keeps both, and its summary, which
``worker sync`` prints, says when they differ. Split from :mod:`specy_road.worker_runner` for the file limit.

A custom command runs as ``sh -c <command>``; its model is read only when the command is one simple command
(:func:`command_model`), since in a list or pipeline a ``--model`` can belong to another program than the harness.
The review gate reads a ``cursor`` entry's ``channels.cli`` the same way (``orchestration_config.entry_routing``).
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from specy_road.worker_adapter_parsers import model_from_argv
from specy_road.worker_state import WorkerEvent

#: Spans ``sh`` reads literally: single-quoted, double-quoted without a substitution inside, a backslash escape.
_LITERAL = re.compile(r"""'[^']*'|"(?:[^"\\`$]|\\.|\$(?!\())*"|\\.""", re.S)
_REDIRECT_AMP = re.compile(r"[<>]&|&>")   # 2>&1, <&3, &>file: redirections, not a list or a background job
#: Outside those spans: a list, pipeline, background job, subshell, newline or command substitution.
_CONTROL = re.compile(r"[;&|()`\n]|\$\(")


def command_model(command: str) -> str | None:
    """The ``--model`` / ``-m`` a shell command passes when it is one simple command (redirections allowed), else
    ``None``: in ``printf --model x; agent -p {prompt}`` the flag never reaches the harness, so the model is unknown."""
    if _CONTROL.search(_REDIRECT_AMP.sub(" ", _LITERAL.sub(" ", command))):
        return None
    try:
        return model_from_argv(shlex.split(command))
    except ValueError:   # an unbalanced quote: no model can be read from it
        return None


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


def mismatch_note(detail: dict[str, Any]) -> str:
    """The summary suffix when both models are known and differ (ignoring case), else ``""``."""
    told, ran = detail.get("requested_model"), detail.get("observed_model")
    if not told or not ran or str(told).lower() == str(ran).lower():
        return ""
    return f"; model mismatch: told {told}, harness reported {ran}"
