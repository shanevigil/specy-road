"""Whether the model a harness reports is the one it was told, by name (M15.19).

Cursor's stream-json names the model by its display name (``Grok 4.6 High``, ``Claude Opus 5.5 300K High``) while
the roster passes the slug (``cursor-grok-4.6-high``, ``claude-opus-5-5-high``). :func:`same_model` compares the
reported name with every name the told model goes by: the slug, the roster entry's ``harness_model`` and the
profile's ids and names, after :func:`normalise`. A context-size token beside an effort is not part of the name.
When the request names an effort, a profile alias for a different effort is not a name of that request.
:func:`roster_match` finds the roster entry and pinned profile a launched slug belongs to, for the price estimate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: Cursor's prefix on the slugs it routes itself (``cursor-grok-4.6-high``); its display names drop it.
_HARNESS_PREFIX = "cursor-"
#: Trailing effort identity, longest first so ``xhigh`` is not read as ``high``. ``fast`` stays on the identity
#: (``high-fast``). ``Extra High`` is written ``xhigh`` before this table is applied.
_EFFORT_TAILS = (
    "xhigh-fast", "minimal-fast", "medium-fast", "none-fast", "high-fast", "max-fast", "low-fast",
    "minimal", "medium", "xhigh", "none", "high", "max", "low",
)
_CONTEXT_SIZE = re.compile(r"\d+[km]")


def normalise(name: object) -> str:
    """``name`` lowercased, every run of other characters than letters and digits (spaces, dots, hyphens,
    underscores, Cursor's zero-width padding) one ``-``: ``Grok 4.6 High`` is ``grok-4-6-high``."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def _tail(parts: list[str]) -> str:
    """The effort identity ``parts`` ends with (``high``, ``high-fast``, ``xhigh``), or ``''``."""
    key = "-".join(parts)
    for tail in _EFFORT_TAILS:
        if key == tail or key.endswith("-" + tail):
            return tail
    return ""


def _comparable(name: object) -> str:
    """``normalise`` with ``Extra High`` as ``xhigh`` and a context-size token dropped beside an effort tail.

    A name that does not end in an effort keeps its context-size token, so ``GPT-5.6 Sol 1M`` (the medium
    display name, the effort word omitted) does not become the bare model.
    """
    key = normalise(name).replace("extra-high", "xhigh")
    parts = [p for p in key.split("-") if p]
    if _tail(parts):
        parts = [p for p in parts if _CONTEXT_SIZE.fullmatch(p) is None]
    return "-".join(parts)


def _forms(name: object) -> set[str]:
    key = _comparable(name)
    return {key, key.removeprefix(_HARNESS_PREFIX)} - {""}


def _effort(name: object) -> str:
    """The request or report's effort identity, or ``''`` when ``name`` is missing or names none."""
    if name is None:
        return ""
    key = _comparable(name).removeprefix(_HARNESS_PREFIX)
    return _tail([p for p in key.split("-") if p])


def _keeps_name(name: object, requested: set[str]) -> bool:
    """A profile name counts when it names no effort, or the effort the request names.

    A request that names no effort keeps every profile name. That is the limit of this rule: effort identity
    is enforced only when the slug or ``harness_model`` names one.
    """
    if not name:
        return False
    effort = _effort(name)
    if effort in requested:
        return True
    return not effort or not requested


def _profile_names(profile: Any, slug: object, harness_model: object) -> list:
    """Profile ids and names whose effort does not contradict the request."""
    data = profile.data
    aliases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
    requested = {_effort(slug), _effort(harness_model)} - {""}
    raw = [profile.api_id, profile.path.stem, data.get("model"), data.get("display_name"), *aliases]
    return [n for n in raw if _keeps_name(n, requested)]


def same_model(reported: object, slug: object, harness_model: object = None, profile: Any = None) -> bool:
    """True when ``reported`` is, after :func:`normalise` and without Cursor's ``cursor-`` prefix, the ``slug``,
    the roster entry's ``harness_model``, or the profile's ``api_id``, file name, ``aliases``, ``model`` or
    ``display_name``. A context-size token beside an effort is not part of the name (``Claude Opus 5.5 300K
    High`` is ``claude-opus-5-5-high``), and ``Extra High`` is ``xhigh``. When the slug or ``harness_model``
    names an effort, a profile name that names a different effort is ignored, so ``GPT-5.6 Sol 1M Medium``
    does not match ``gpt-5.6-sol-high`` through an alias list. ``fast`` is part of that identity. A profile
    name that names no effort still counts. A different model or effort does not match."""
    names = [slug, harness_model]
    if profile is not None:
        names += _profile_names(profile, slug, harness_model)
    told = set().union(*(_forms(n) for n in names if n))
    return bool(_forms(reported) & told)


def roster_match(repo_root: Path, model_id: str) -> tuple[dict[str, Any], Any]:
    """``(entry, profile)`` for the first roster entry whose ``id`` or ``harness_model`` is ``model_id`` or whose
    pinned profile answers to it (:meth:`Profile.for_id`); ``({}, None)`` when none does or the roster is unreadable.
    ``profile`` is ``None`` for a matching entry without a valid profile."""
    from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry  # noqa: PLC0415

    config, err = pinned_config(repo_root)
    if err or not model_id:
        return {}, None
    for entry in config.get("roster") or []:
        prof = pinned_profile_for_entry(repo_root, entry)
        prof = prof if prof is not None and prof.ok else None
        aliased = prof.for_id(model_id) if prof is not None else None
        if aliased or model_id in (entry.get("id"), entry.get("harness_model")):
            return entry, aliased or prof
    return {}, None
