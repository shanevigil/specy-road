"""Roster entries one clone adds for itself: ``roster_add`` in ``roadmap/orchestration.local.yaml``.

The local file is gitignored and already overlays availability (``roster:``). ``roster_add`` lists whole
entries that planning and delegation on this clone use after the pinned roster's: an added id that the
pinned roster already has is refused (a local entry never overrides a committed one), and so is an entry
with a command to run (``channels.cli``, or a profile whose ``access.cli`` is set) unless the same file
sets ``allow_local_cli: true``. An entry may never set ``allow_guidance_bypass_model`` (M21.44): that opt-in
counts only on the committed roster. Nothing here is shared with other clones, and the review gate reads only
the committed roster.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

import yaml

from specy_road.model_profiles import Profile
from specy_road.orchestration_config import (
    ORCHESTRATION_LOCAL_REL,
    _dates_to_iso,
    _semantic_error,
    orchestration_local_path,
    validate_orchestration_dict,
)

ROSTER_ADD_KEY = "roster_add"
ALLOW_LOCAL_CLI_KEY = "allow_local_cli"
#: Roster key: use a model whose profile records guidance bypass anyway, at the developer's own risk (M21.44).
GUIDANCE_OPT_IN = "allow_guidance_bypass_model"


def load_local_roster(repo_root: Path) -> tuple[list[dict[str, Any]], bool, str | None]:
    """``(entries, allow_local_cli, error)`` from the local file; no file or no key is ``([], False, None)``."""
    path = orchestration_local_path(repo_root)
    if not path.is_file():
        return [], False, None
    where = ORCHESTRATION_LOCAL_REL.as_posix()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, ValueError) as e:
        return [], False, f"YAML error in {where}: {e}"
    if not isinstance(raw, dict):
        return [], False, None   # load_availability_overlay reports a non-mapping file
    allow = raw.get(ALLOW_LOCAL_CLI_KEY, False)
    if not isinstance(allow, bool):
        return [], False, f"{where}: {ALLOW_LOCAL_CLI_KEY} must be true or false"
    entries = raw.get(ROSTER_ADD_KEY)
    if entries is None:
        return [], allow, None
    if not isinstance(entries, list):
        return [], allow, f"{where}: {ROSTER_ADD_KEY} must be a list"
    data = {"version": 1, "roster": entries}
    _dates_to_iso(data)
    err = validate_orchestration_dict(data) or _semantic_error(data)
    if err:
        return [], allow, f"{where}: {ROSTER_ADD_KEY}{err.removeprefix('roster')}"
    return entries, allow, None


def _never_local(entry: dict[str, Any], rid: str, committed: set[str]) -> str | None:
    """What no local entry may do, ``allow_local_cli`` or not: override a committed id, or set the opt-in."""
    if rid in committed:
        return ("is already a roster entry; a local entry never overrides one "
                "(set its availability under roster: instead, or pick another id)")
    if GUIDANCE_OPT_IN in entry:
        return (f"sets {GUIDANCE_OPT_IN}, which counts only on the committed roster "
                "(roadmap/orchestration.yaml on the integration branch); remove it here")
    return None


def merge_local_roster(repo_root: Path, config: dict[str, Any],
                       profile_for: Callable[[dict[str, Any]], Profile | None]) -> str | None:
    """Append this clone's ``roster_add`` entries to ``config['roster']`` (in place), or say why not.

    ``profile_for`` resolves an entry's profile the way the caller routes (the pinned ref, or the working
    tree for a dry run), so a profile's ``access.cli`` is judged from the copy that would run."""
    entries, allow, err = load_local_roster(repo_root)
    if err or not entries:
        return err
    where = f"{ORCHESTRATION_LOCAL_REL.as_posix()}: {ROSTER_ADD_KEY}"
    committed = {str(e.get("id")) for e in config.get("roster") or []}
    for i, entry in enumerate(entries):
        rid = str(entry["id"])
        if why := _never_local(entry, rid, committed):
            return f"{where}/{i}: {rid!r} {why}"
        if allow:
            continue
        if (entry.get("channels") or {}).get("cli"):
            return (f"{where}/{i}: {rid!r} sets channels.cli, a command this clone would run; "
                    f"set {ALLOW_LOCAL_CLI_KEY}: true in the same file to allow it")
        prof = profile_for(entry)
        if prof is not None and prof.ok and prof.cli():
            return (f"{where}/{i}: {rid!r} uses a profile whose access.cli would run on this clone; "
                    f"set {ALLOW_LOCAL_CLI_KEY}: true in the same file to allow it")
    config.setdefault("roster", []).extend(copy.deepcopy(entries))
    return None


def local_roster_ids(repo_root: Path) -> list[str]:
    """Ids this clone adds (empty when the file is absent or invalid: the loader reports that)."""
    entries, _allow, err = load_local_roster(repo_root)
    return [] if err else [str(e["id"]) for e in entries]
