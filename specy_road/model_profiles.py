"""Read model profiles (``model-profiles/<family>/<api_id>.md``) for the roster.

A profile is Markdown with a schema-2 YAML front matter (the machine part: ids,
limits, prices, ``role_fit``, ``access.cli``, ``effort_map``) and body sections
(``## Strengths``, ``## Failure modes``, ``## Prompting rules``, …). The
toolkit ships a canonical set and ``init project`` scaffolds them into the
adopter's repo, where a roster entry's ``profile`` key points at one; the team
edits them as their own research and vendor docs move.

``specy-road models list|show|stale`` reads them, and ``specy-road prompt``
applies a profile's ``## Prompting rules`` and failure-mode mitigations to a
role prompt (proposal §4.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

PROFILES_REL = Path("model-profiles")
PROFILE_SCHEMA = 2
#: A profile older than this is stale unless the roster says otherwise.
DEFAULT_MAX_AGE_DAYS = 180
ROLES = ("coordinator", "executor", "reviewer")
_REQUIRED = ("profile_schema", "family", "model", "api_id", "version_rank", "researched", "access", "role_fit")


@dataclass
class Profile:
    path: Path
    data: dict[str, Any]
    sections: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def api_id(self) -> str:
        return str(self.data.get("api_id") or self.path.stem)

    @property
    def researched(self) -> date | None:
        return _as_date(self.data.get("researched"))

    def role_score(self, role: str) -> int | None:
        fits = self.data.get("role_fit")
        fit = fits.get(role) if isinstance(fits, dict) else None
        score = fit.get("score") if isinstance(fit, dict) else None
        return int(score) if isinstance(score, int) else None

    def cli(self) -> str | None:
        access = self.data.get("access")
        cli = access.get("cli") if isinstance(access, dict) else None
        return None if not isinstance(cli, str) or cli.strip().lower() == "none" else cli

    def bullets(self, section: str) -> list[str]:
        """The ``- `` items under ``## <section>``, without the dash."""
        return [ln[2:].strip() for ln in self.sections.get(section, []) if ln.startswith("- ")]

    def stale_reasons(self, today: date | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> list[str]:
        out = []
        when = self.researched
        if when is None:
            out.append("no valid `researched` date")
        elif ((today or date.today()) - when).days > max_age_days:
            out.append(f"researched {when.isoformat()}, more than {max_age_days} days ago")
        if self.data.get("version_rank") == "previous":
            track = self.data.get("track")  # `track: none` marks a family with one line
            line = track if track and str(track).lower() != "none" else self.data.get("family")
            out.append(f"version_rank: previous (superseded by a newer {line} release)")
        if str(self.data.get("alias_moves", "")).lower() == "yes":
            out.append("alias_moves: yes — the api_id can point at a newer checkpoint than this profile describes")
        return out


def _split(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def _sections(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for ln in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append(ln)
    return out


def _as_date(raw: Any) -> date | None:
    """A real calendar date from a YAML date or an ISO string, else ``None``."""
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _structure_errors(data: dict[str, Any]) -> list[str]:
    """Shapes the readers assume: wrong ones made ``profile_ok`` true and then raised."""
    out = []
    access = data.get("access")
    if "access" in data and not isinstance(access, dict):
        out.append("`access` must be a mapping")
    elif isinstance(access, dict):
        if access.get("cli") is not None and not isinstance(access["cli"], str):
            out.append("`access.cli` must be a string")
        if "effort_map" in access and not isinstance(access["effort_map"], dict):
            out.append("`access.effort_map` must be a mapping")
    fit = data.get("role_fit")
    if "role_fit" in data and not isinstance(fit, dict):
        out.append("`role_fit` must be a mapping of role → {score, reason}")
    elif isinstance(fit, dict):
        for role, v in fit.items():
            if not isinstance(v, dict) or not isinstance(v.get("score"), int) or isinstance(v.get("score"), bool):
                out.append(f"`role_fit.{role}` must be a mapping with an integer `score`")
    if "cost_usd_per_mtok" in data and not isinstance(data["cost_usd_per_mtok"], dict):
        out.append("`cost_usd_per_mtok` must be a mapping")
    if "researched" in data and _as_date(data["researched"]) is None:
        out.append(f"`researched` is not a calendar date (YYYY-MM-DD): {data['researched']!r}")
    return out


def parse_profile(path: Path, text: str) -> Profile:
    """A profile from its text; ``path`` is where it came from (a file or a git blob)."""
    block, body = _split(text)
    if block is None:
        return Profile(path, {}, errors=["missing YAML front matter (--- … ---)"])
    try:
        data = yaml.safe_load(block)
    except (yaml.YAMLError, ValueError) as e:   # ValueError: an impossible date like 2026-00-00
        return Profile(path, {}, errors=[f"front matter is not valid YAML: {e}"])
    if not isinstance(data, dict):
        return Profile(path, {}, errors=["front matter must be a mapping"])
    errors = [f"missing `{k}`" for k in _REQUIRED if k not in data]
    if data.get("profile_schema") != PROFILE_SCHEMA:
        errors.append(f"profile_schema is {data.get('profile_schema')!r}, expected {PROFILE_SCHEMA}")
    return Profile(path, data, _sections(body), errors + _structure_errors(data))


def load_profile(path: Path) -> Profile:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Profile(path, {}, errors=[f"cannot read: {e}"])
    return parse_profile(path, text)


def profiles_dir(repo_root: Path) -> Path:
    return repo_root / PROFILES_REL


def list_profiles(repo_root: Path) -> list[Profile]:
    root = profiles_dir(repo_root)
    if not root.is_dir():
        return []
    paths = sorted(p for p in root.rglob("*.md") if p.name != "README.md")
    return [load_profile(p) for p in paths]


def profile_rel_problem(repo_root: Path, rel: str) -> str | None:
    """Why a roster ``profile:`` path is not a plain path inside the repository."""
    parts = Path(rel).parts
    if Path(rel).is_absolute() or ".." in parts or not parts:
        return f"profile path escapes the repository: {rel}"
    if not (repo_root / rel).resolve().is_relative_to(Path(repo_root).resolve()):
        return f"profile path escapes the repository: {rel}"
    return None


def display_rel(repo_root: Path, path: Path) -> str:
    """``path`` relative to the repo when it is inside it, else as given — never a crash."""
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def profile_for_entry(repo_root: Path, entry: dict[str, Any]) -> Profile | None:
    """The roster entry's profile **from the working tree**: its ``profile`` path, else a file named after its ``id``.

    Routing and dispatch use :func:`orchestration_pinned.pinned_profile_for_entry`,
    which reads the same path from the integration branch.
    """
    rel = entry.get("profile")
    if rel:
        why = profile_rel_problem(repo_root, str(rel))
        if why:
            return Profile(repo_root / str(rel), {}, errors=[why])
        return load_profile((repo_root / str(rel)).resolve())
    for p in list_profiles(repo_root):
        if p.api_id == entry.get("id") or p.path.stem == entry.get("id"):
            return p
    return None
