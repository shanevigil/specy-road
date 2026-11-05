"""Whether the model a harness reports is the one it was told, by name (M15.19).

Cursor's stream-json names the model by its display name (``Grok 4.6 High``) while the roster passes the slug
(``cursor-grok-4.6-high``). :func:`same_model` compares the reported name with every name the told model goes by:
the slug, the roster entry's ``harness_model`` and the profile's ids and names, after :func:`normalise`.
:func:`roster_match` finds the roster entry and pinned profile a launched slug belongs to, for the price estimate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: Cursor's prefix on the slugs it routes itself (``cursor-grok-4.6-high``); its display names drop it.
_HARNESS_PREFIX = "cursor-"


def normalise(name: object) -> str:
    """``name`` lowercased, every run of other characters than letters and digits (spaces, dots, hyphens,
    underscores, Cursor's zero-width padding) one ``-``: ``Grok 4.6 High`` is ``grok-4-6-high``."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def _forms(name: object) -> set[str]:
    key = normalise(name)
    return {key, key.removeprefix(_HARNESS_PREFIX)}


def same_model(reported: object, slug: object, harness_model: object = None, profile: Any = None) -> bool:
    """True when ``reported`` is, after :func:`normalise` and without Cursor's ``cursor-`` prefix, the ``slug``,
    the roster entry's ``harness_model``, or the profile's ``api_id``, file name, ``aliases``, ``model`` or
    ``display_name``."""
    names = [slug, harness_model]
    if profile is not None:
        data = profile.data
        aliases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
        names += [profile.api_id, profile.path.stem, data.get("model"), data.get("display_name"), *aliases]
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
