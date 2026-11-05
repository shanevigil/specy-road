"""Whether a launched reviewer's harness ran the rostered model (M15.3).

A reviewer's record counts toward the gate under its roster id, so the model the harness says it ran (the
``system/init`` event's ``model``, read as worker usage reads it: :func:`~specy_road.worker_adapter_parsers.init_model`)
is compared with the roster entry's model by :func:`~specy_road.model_names.same_model`, which normalises case,
separators and display names. :func:`check` gives ``match``, ``mismatch`` or ``unreported``;
:func:`~specy_road.review_record_write.file_review` writes ``harness_model`` into the record and, on a mismatch,
``model_mismatch: true``, which :func:`model_mismatch_problem` keeps from counting in the gate. A harness that
reports no model is a warning only.
"""

from __future__ import annotations

from typing import Any, Literal

from specy_road.model_names import normalise, same_model  # noqa: F401 — normalise re-exported
from specy_road.worker_adapter_parsers import init_model

MISMATCH_REASON = "harness ran a different model"

Check = Literal["match", "mismatch", "unreported"]


def reported_model(lines: list[str] | str) -> str | None:
    """The model the run's first ``system/init`` event names, else ``None`` (Codex and plain-text harnesses print
    none). The first one wins: later lines are the model's own output."""
    for line in lines.splitlines() if isinstance(lines, str) else lines:
        model = init_model(line)
        if model:
            return model
    return None


def check(reported: str | None, entry: dict[str, Any], profile: Any = None) -> Check:
    """``reported`` against the roster ``entry`` (its ``id`` and ``harness_model``) and its ``profile``'s ids and
    names (:func:`~specy_road.model_names.same_model`)."""
    if not reported:
        return "unreported"
    return "match" if same_model(reported, entry.get("id"), entry.get("harness_model"), profile) else "mismatch"


def check_note(state: Check, reported: str | None, model: str) -> str:
    """The stderr line for ``state``; ``""`` on a match."""
    if state == "mismatch":
        return (f"warning: {MISMATCH_REASON}: the roster names {model!r}, the harness reported {reported!r}; the "
                "record is filed with model_mismatch and does not count toward the gate")
    if state == "unreported":
        return f"warning: the harness reported no model; specy-road cannot confirm it ran {model!r}"
    return ""


def model_mismatch_problem(data: dict[str, Any]) -> str | None:
    """Why the gate does not count a record filed with ``model_mismatch``, else ``None``."""
    if data.get("model_mismatch") is True:
        return f"{MISMATCH_REASON} ({data.get('harness_model') or 'unknown'}, not {data.get('model')!r})"
    return None
