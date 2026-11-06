"""Roster entries built from the shipped model profiles (``specy-road models roster``).

Each entry has the ``id`` (the profile's file name), the roster ``family`` the profiles README
gives that vendor, ``profile:`` in the ``model-profiles/<dir>/<file>.md`` form ``validate``
accepts, the ``harness`` whose executor template renders the profile's family (``generic``
when none does), and the roles asked for. :func:`write_entries` adds them to the roster of
``roadmap/orchestration.yaml`` as text, so the file's comments stay.
"""

from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path
from typing import Any

import yaml

from specy_road.harness_facts import load_facts
from specy_road.model_profiles import Profile, bundled_profiles_root, list_profiles
from specy_road.orchestration_config import ORCHESTRATION_REL

#: Profile ``family`` → roster ``family`` (model-profiles/README.md): the gate counts families by these.
ROSTER_FAMILY = {"Anthropic Claude": "anthropic", "OpenAI GPT": "openai", "Google Gemini": "google",
                 "SpaceXAI Grok": "xai", "Meta Muse": "meta", "Cursor Composer": "cursor", "DeepSeek": "deepseek"}


class RosterError(ValueError):
    """An unknown profile id, or a roster file the entries cannot be added to."""


def shipped_profiles() -> list[Profile]:
    return [p for p in list_profiles(bundled_profiles_root()) if p.ok]


def profile_id(p: Profile) -> str:
    return p.path.stem


def find_profile(pid: str, profiles: list[Profile]) -> Profile:
    """The profile whose file name, else ``api_id`` or alias, is ``pid``; refused with the nearest ids."""
    hit = next((p for p in profiles if profile_id(p) == pid), None) or \
        next((p for p in profiles if p.for_id(pid)), None)
    if hit is None:
        near = get_close_matches(pid, [profile_id(p) for p in profiles], n=3, cutoff=0.4)
        raise RosterError(f"no shipped profile {pid!r}" + (f"; nearest: {', '.join(near)}" if near else "")
                          + " (`specy-road models list` shows them)")
    return hit


def harness_for(family: Any, facts: dict[str, Any]) -> str:
    return next((h["id"] for h in facts["harnesses"]
                 if family in h["executor_template"]["renders_cli_for"]), "generic")


def roster_entries(requests: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """``(role, profile id)`` pairs → one entry per profile, roles in the order asked."""
    profiles, facts = shipped_profiles(), load_facts()
    root = bundled_profiles_root()
    out: dict[str, dict[str, Any]] = {}
    for role, pid in requests:
        p = find_profile(pid, profiles)
        fam = str(p.data.get("family"))
        entry = out.setdefault(profile_id(p), {
            "id": profile_id(p),
            "family": ROSTER_FAMILY.get(fam, fam.split()[0].lower()),
            "profile": p.path.relative_to(root).as_posix(),
            "harness": harness_for(fam, facts),
            "roles": []})
        if role not in entry["roles"]:
            entry["roles"].append(role)
    return list(out.values())


def format_entries(entries: list[dict[str, Any]], indent: str = "  ") -> str:
    lines = []
    for e in entries:
        lines += [f"{indent}- id: {e['id']}", f"{indent}  family: {e['family']}", f"{indent}  profile: {e['profile']}",
                  f"{indent}  harness: {e['harness']}", f"{indent}  roles: [{', '.join(e['roles'])}]"]
    return "\n".join(lines) + "\n"


def missing_profile_files(repo_root: Path, entries: list[dict[str, Any]]) -> list[str]:
    """Each entry's ``profile:`` the repo does not have yet, with the command that adds it."""
    return [f"{e['profile']} is not in this repo; run `specy-road refresh-profiles --only {e['id']}`"
            for e in entries if not (repo_root / e["profile"]).is_file()]


def _roster_span(lines: list[str]) -> tuple[int, int, str]:
    """``(roster: line, insert index, item indent)``; the block ends at the next top-level key."""
    start = next((i for i, ln in enumerate(lines) if ln.split("#")[0].rstrip() in ("roster:", "roster: []")), None)
    if start is None:
        raise RosterError(f"{ORCHESTRATION_REL.as_posix()} has no block-style `roster:` to add to; paste the entries by hand")
    end = start
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and not ln.startswith((" ", "-", "#")):
            break
        if ln.strip() and not ln.lstrip().startswith("#"):
            end = i
    item = next((ln for ln in lines[start + 1:end + 1] if ln.lstrip().startswith("- ")), "  - ")
    return start, end + 1, item[: len(item) - len(item.lstrip())]


def write_entries(repo_root: Path, entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Add ``entries`` to the roster file; ``(added ids, ids already rostered)``. The result must parse."""
    path = repo_root / ORCHESTRATION_REL
    if not path.is_file():
        raise RosterError(f"no {ORCHESTRATION_REL.as_posix()}; write the starter first with "
                          "`specy-road validate --generate-orchestration`")
    text = path.read_text(encoding="utf-8")
    rostered = {e.get("id") for e in (yaml.safe_load(text) or {}).get("roster") or []}
    new = [e for e in entries if e["id"] not in rostered]
    if not new:
        return [], [e["id"] for e in entries]
    lines = text.splitlines(keepends=True)
    start, at, indent = _roster_span([ln.rstrip("\n") for ln in lines])
    if lines[start].split("#")[0].strip() == "roster: []":
        parts = lines[start].split("#", 1)
        lines[start] = "roster:" + (f" #{parts[1]}" if len(parts) > 1 else "") + "\n"
    if at > 0 and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    out = "".join(lines[:at]) + format_entries(new, indent) + "".join(lines[at:])
    ids = [e.get("id") for e in (yaml.safe_load(out) or {}).get("roster") or []]
    if any(e["id"] not in ids for e in new):
        raise RosterError(f"could not add the entries to {ORCHESTRATION_REL.as_posix()} safely; paste them by hand")
    path.write_text(out, encoding="utf-8")
    return [e["id"] for e in new], [e["id"] for e in entries if e["id"] in rostered]

