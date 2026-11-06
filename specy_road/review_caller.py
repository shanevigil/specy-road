"""Who runs ``specy-road review record`` from the command line, and whether it may file under ``--model`` (M21.31).

A review record files only under the caller's own model. The caller is identified by the environment, never by
anything it types (:func:`caller`):

* ``SPECY_ROAD_WORKER_ID`` set: the worker record it names (:func:`~specy_road.worker_state.load_record`) gives the
  model, ahead of any harness marker the worker inherited. An id that does not resolve is an error;
* else exactly one marker of :data:`HARNESS_MARKERS`: that harness;
* else (no marker, or two or more): unidentified.

:func:`refusal` is what the ``review record`` argparse handler checks before any write, lock or ``REJECTED`` file. A
worker files only as its own model, a harness only for a roster entry on that harness (an entry with no harness, or
``generic``, matches none), and an unidentified caller (a human in a plain terminal) only with ``--human-filed '<who
and why>'``, stored as ``human_filed``; the gate counts such a record only when it is signed or
``policy.count_human_filed_reviews`` is on. ``review delegate`` and ``prompt --channel cli --run`` file through
``file_review`` and are not checked here. Cooperative, like READY: ``policy.signed_reviews`` is the strong check.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.review_policy_ref import policy_source
from specy_road.worker_state import WorkerError, load_record

#: ``(harness, environment variable, value)``: the marker each harness exports to the commands it runs, confirmed
#: against the §9 replay versions (2026-11-05): Claude Code 2.1.318, codex-cli 0.166.0, Cursor agent
#: 2026.11.05-86047df. ``None``: any non-empty value.
HARNESS_MARKERS: tuple[tuple[str, str, str | None], ...] = (
    ("claude-code", "CLAUDECODE", "1"),
    ("codex", "CODEX_THREAD_ID", None),
    ("cursor", "CURSOR_AGENT", "1"),
)


class CallerError(Exception):
    """``SPECY_ROAD_WORKER_ID`` is set but names no readable worker record."""


def caller(repo_root: Path, env: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """``("worker", model)``, ``("harness", name)`` or ``None`` (unidentified); module docstring."""
    env = os.environ if env is None else env
    wid = env.get("SPECY_ROAD_WORKER_ID")
    if wid is not None:
        try:
            return "worker", load_record(repo_root, wid).model
        except WorkerError as e:
            raise CallerError(f"SPECY_ROAD_WORKER_ID is {wid!r}, which names no readable worker record ({e})") from None
    found = [h for h, var, want in HARNESS_MARKERS if (env.get(var) == want if want else env.get(var))]
    return ("harness", found[0]) if len(found) == 1 else None


def _attestation_problem(text: str | None) -> str | None:
    if text is None:
        return ("this command runs under no identified harness (no SPECY_ROAD_WORKER_ID, and not exactly one of "
                + ", ".join(var for _, var, _ in HARNESS_MARKERS)
                + "); a human filing by hand passes --human-filed '<who and why>'")
    if not text.strip() or "\n" in text or "\r" in text:
        return "--human-filed takes one non-empty line saying who files this record and why"
    return None


def refusal(repo_root: Path, ns: Any) -> str | None:
    """Why ``ns`` (``review record``'s arguments) may not file under ``ns.model``, else ``None``. For a matching
    identified caller a ``--human-filed`` is dropped from ``ns`` with a note, so it is not stored."""
    try:
        who = caller(repo_root)
    except CallerError as e:
        return f"{e}; nothing was written"
    if who is None:
        why = _attestation_problem(getattr(ns, "human_filed", None))
        return f"{why}; nothing was written" if why else None
    kind, name = who
    if kind == "worker":
        if name != ns.model:
            return (f"{ns.model} is not this worker's model, and this command runs under a worker of {name}; file a "
                    "review only under your own model id (AGENTS.md, Review roles); nothing was written")
    else:
        ref, err = policy_source(repo_root)
        config, err = (None, err) if err else effective_config(repo_root, ref)
        entry = None if err else roster_entry(config, ns.model)
        if entry is not None and entry.get("harness") != name:   # an unrostered model is refused later
            return (f"{ns.model} is a {entry.get('harness') or 'harness-less'} roster entry and this command runs "
                    f"under {name}; file a review only under your own model id (AGENTS.md, Review roles); "
                    "nothing was written")
    if getattr(ns, "human_filed", None) is not None:
        print(f"note: --human-filed ignored: this command runs under {kind} {name}, which matches {ns.model}",
              file=sys.stderr)
        ns.human_filed = None
    return None
