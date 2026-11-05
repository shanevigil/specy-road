"""Whether a launched reviewer's harness ran the rostered model (M15.3).

A reviewer's record counts toward the gate under its roster id, so the models the harness says it ran (the first
``system/init`` event's ``model``, read as worker usage reads it: :func:`~specy_road.worker_adapter_parsers.init_model`,
and each ``result`` event's: :func:`result_model`) are compared with the roster entry's model by
:func:`~specy_road.model_names.same_model`, which normalises case, separators and display names. :func:`check_run` gives ``match``, ``mismatch`` or ``unreported``;
:func:`~specy_road.review_record_write.file_review` writes ``harness_model`` into the record and, on a mismatch,
``model_mismatch: true``, which :func:`model_mismatch_problem` keeps from counting in the gate. A harness that
reports no model is a warning only.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from specy_road.model_names import normalise, same_model  # noqa: F401 — normalise re-exported
from specy_road.worker_adapter_parsers import init_model

MISMATCH_REASON = "harness ran a different model"

Check = Literal["match", "mismatch", "unreported"]


def result_model(line: str) -> str | None:
    """The model a ``result`` event names: its ``model`` string, else the one key of its ``modelUsage`` (Claude Code's
    per-model usage). Several ``modelUsage`` keys (a helper model beside the main one) name no single model."""
    try:
        d = json.loads(line)
    except (ValueError, RecursionError):   # untrusted output: deep nesting is not an exception out of here
        return None
    if not isinstance(d, dict) or d.get("type") != "result":
        return None
    if isinstance(d.get("model"), str) and d["model"].strip():
        return d["model"].strip()
    usage = d.get("modelUsage")
    return next(iter(usage)) if isinstance(usage, dict) and len(usage) == 1 and str(next(iter(usage))).strip() else None


def reported_models(lines: list[str] | str) -> list[str]:
    """Every model the run reported, in order and without repeats: the first ``system/init`` event's (as worker usage
    reads it) and each ``result`` event's (:func:`result_model`). Codex and plain-text harnesses report none."""
    out: list[str] = []
    init_seen = False
    for line in lines.splitlines() if isinstance(lines, str) else lines:
        model = None if init_seen else init_model(line)
        init_seen = init_seen or model is not None
        model = model or result_model(line)
        if model and model not in out:
            out.append(model)
    return out


def check_run(lines: list[str] | str, entry: dict[str, Any], profile: Any = None) -> tuple[str | None, Check]:
    """``(harness_model, state)`` for a run's output: ``mismatch`` with the first reported model that is not the
    roster entry's when any is (so a line the model printed can add a mismatch but never hide one), else ``match``
    with the first, else ``(None, "unreported")``."""
    models = reported_models(lines)
    bad = next((m for m in models if check(m, entry, profile) == "mismatch"), None)
    if bad:
        return bad, "mismatch"
    return (models[0], "match") if models else (None, "unreported")


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
