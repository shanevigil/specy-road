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
        raw = self.data.get("researched")
        if isinstance(raw, date):
            return raw
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            return None

    def role_score(self, role: str) -> int | None:
        fit = (self.data.get("role_fit") or {}).get(role) or {}
        score = fit.get("score") if isinstance(fit, dict) else None
        return int(score) if isinstance(score, int) else None

    def cli(self) -> str | None:
        cli = (self.data.get("access") or {}).get("cli")
        return None if not cli or str(cli).strip().lower() == "none" else str(cli)

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
            out.append(f"version_rank: previous (superseded by a newer {self.data.get('track') or self.data.get('family')} release)")
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


def load_profile(path: Path) -> Profile:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Profile(path, {}, errors=[f"cannot read: {e}"])
    block, body = _split(text)
    if block is None:
        return Profile(path, {}, errors=["missing YAML front matter (--- … ---)"])
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        return Profile(path, {}, errors=[f"front matter is not valid YAML: {e}"])
    if not isinstance(data, dict):
        return Profile(path, {}, errors=["front matter must be a mapping"])
    errors = [f"missing `{k}`" for k in _REQUIRED if k not in data]
    if data.get("profile_schema") != PROFILE_SCHEMA:
        errors.append(f"profile_schema is {data.get('profile_schema')!r}, expected {PROFILE_SCHEMA}")
    return Profile(path, data, _sections(body), errors)


def profiles_dir(repo_root: Path) -> Path:
    return repo_root / PROFILES_REL


def list_profiles(repo_root: Path) -> list[Profile]:
    root = profiles_dir(repo_root)
    if not root.is_dir():
        return []
    paths = sorted(p for p in root.rglob("*.md") if p.name != "README.md")
    return [load_profile(p) for p in paths]


def profile_for_entry(repo_root: Path, entry: dict[str, Any]) -> Profile | None:
    """The roster entry's profile: its ``profile`` path, else a file named after its ``id``."""
    rel = entry.get("profile")
    if rel:
        return load_profile(repo_root / str(rel))
    for p in list_profiles(repo_root):
        if p.api_id == entry.get("id") or p.path.stem == entry.get("id"):
            return p
    return None
