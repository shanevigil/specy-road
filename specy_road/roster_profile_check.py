"""Resolve each roster ``profile:`` value against ``model-profiles/`` in the working tree.

A ``profile:`` is a repo-relative path, ``model-profiles/<family-dir>/<file>.md``. A value in
another form (``anthropic/claude-opus-5-5``, a bare id, a missing file) used to pass ``validate``
and surface later in ``orchestrate plan`` as "not committed on the integration branch" plus a
``may_process`` hint, neither of which named the problem. :func:`profile_value_problem` names it
with the accepted form, and the concrete path when the value's last part names a known profile.
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import Any

from specy_road.model_profiles import (
    PROFILES_REL,
    bundled_profiles_root,
    list_profiles,
    load_profile,
    near_miss_profile,
    roster_profile_gaps,
)
from specy_road.orchestration_config import load_orchestration_config

GENERIC_FORM = f"{PROFILES_REL.as_posix()}/<family-dir>/<profile-id>.md"


def accepted_form(repo_root: Path, value: str) -> str:
    """``model-profiles/<dir>/<id>.md`` for the profile the value's last part names, else the generic form."""
    stem = PurePosixPath(str(value).replace("\\", "/")).name.removesuffix(".md")
    for root in (repo_root, bundled_profiles_root()):
        near = near_miss_profile(stem, list_profiles(root)) if stem else None
        if near is not None:
            return near.path.relative_to(root).as_posix()
    return GENERIC_FORM


def profile_value_form_problem(repo_root: Path, value: Any) -> str | None:
    """``invalid profile: <value>, accepted form <form>`` unless ``value`` is a repo-relative
    ``model-profiles/…/*.md`` path using forward slashes (the file need not exist in the working tree)."""
    raw = str(value)
    if "\\" in raw:
        return f"invalid profile: {value}, accepted form {accepted_form(repo_root, raw)}"
    rel = PurePosixPath(raw)
    if (not rel.is_absolute() and ".." not in rel.parts and rel.parts[:1] == (PROFILES_REL.as_posix(),)
            and rel.suffix == ".md"):
        return None
    return f"invalid profile: {value}, accepted form {accepted_form(repo_root, raw)}"


def profile_value_problem(repo_root: Path, value: Any) -> str | None:
    """``invalid profile: <value>, accepted form <form>`` unless ``value`` is a ``.md`` file under
    ``model-profiles/`` in the working tree."""
    why = profile_value_form_problem(repo_root, value)
    if why:
        return why
    rel = PurePosixPath(str(value))
    if not (repo_root / rel).is_file():
        return f"invalid profile: {value}, accepted form {accepted_form(repo_root, str(value))}"
    return None


def roster_profile_problems(repo_root: Path) -> list[str]:
    """One message per working-tree roster entry whose ``profile:`` does not resolve, or resolves to
    a profile that does not load."""
    config, err = load_orchestration_config(repo_root)
    if err or not config:
        return []
    out = []
    for entry in config.get("roster") or []:
        value = entry.get("profile")
        if not value:
            continue
        where = f"roster entry {entry.get('id')!r} in roadmap/orchestration.yaml"
        why = profile_value_problem(repo_root, value)
        if why:
            out.append(f"{where}: {why}")
            continue
        prof = load_profile(repo_root / str(value))
        if not prof.ok:
            out.append(f"{where}: profile {value} does not load: {'; '.join(prof.errors)}")
    return out


def report_roster_profiles(repo_root: Path) -> None:
    """``validate``'s roster-profile output: unmatched ids (a stdout notice when nothing can launch the
    entry, which ``--strict`` does not count), unresolved ``profile:`` values (warnings), and, under
    ``signed_reviews``, each executor or reviewer entry whose model records guidance bypass (M21.44)."""
    from specy_road.orchestrate_assign import guidance_bypass_lines   # noqa: PLC0415 — via orchestration_pinned, it imports this module
    for launchable, msg in roster_profile_gaps(repo_root):
        print(f"{'warning' if launchable else 'notice'}: {msg}", file=sys.stderr if launchable else sys.stdout)
    for msg in roster_profile_problems(repo_root):
        print(f"warning: {msg}", file=sys.stderr)
    for line in guidance_bypass_lines(repo_root):
        print(line, file=sys.stderr)
