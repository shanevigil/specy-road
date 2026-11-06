"""Read model profiles (``model-profiles/<family>/<api_id>.md``) for the roster.

A profile is Markdown with a schema-2 YAML front matter (the machine part: ids,
limits, prices, ``role_fit``, ``access.cli``, ``effort_map``, ``effort_by_role``, ``launch_mode``) and body sections
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
from dataclasses import dataclass, field, replace
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import yaml

from specy_road.orchestration_config import load_orchestration_config
from specy_road.runtime_paths import specy_road_package_dir

PROFILES_REL = Path("model-profiles")
PROFILE_SCHEMA = 2
#: A profile older than this is stale unless the roster says otherwise.
DEFAULT_MAX_AGE_DAYS = 180
ROLES = ("coordinator", "executor", "reviewer")
_REQUIRED = ("profile_schema", "family", "model", "api_id", "version_rank", "researched", "access", "role_fit")
#: ``access.launch_mode``: ``full`` lets the harness discover its hooks, skills, MCP servers and
#: CLAUDE.md; ``bare`` (Claude Code's ``--bare``) skips them. Absent means ``full``.
LAUNCH_MODES = ("full", "bare")
#: ``guidance_bypass_observed``: a model seen going around specy-road's guidance (M21.44); its keys and harnesses.
GUIDANCE_BYPASS_KEY = "guidance_bypass_observed"
GUIDANCE_BYPASS_FIELDS = ("date", "harness", "evidence")
GUIDANCE_BYPASS_HARNESSES = ("claude-code", "codex", "cursor", "generic")
#: The executor id in the template's ``roadmap/orchestration.yaml``, there to be replaced.
STARTER_PLACEHOLDER_ID = "my-executor"
#: The least ``SequenceMatcher`` ratio at which a profile's name counts as like a roster id.
CLOSEST_MIN_RATIO = 0.6


@dataclass
class Profile:
    path: Path
    data: dict[str, Any]
    sections: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    alias: str | None = None   # the ``aliases`` entry a roster id matched, see :meth:`for_id`

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def api_id(self) -> str:
        """The id the harness is told: the matched alias, else the front matter's ``api_id``."""
        return self.alias or str(self.data.get("api_id") or self.path.stem)

    def for_id(self, model_id: Any) -> Profile | None:
        """This profile when ``model_id`` is its ``api_id``, file name or one of its ``aliases``, else ``None``.

        An alias is a harness's own id for the model, often with an effort suffix
        (Cursor's ``gpt-5.6-sol-high``); the copy returned reports it as ``api_id``,
        so a worker is launched with the id its harness lists.
        """
        if model_id in (self.api_id, self.path.stem):
            return self
        aliases = self.data.get("aliases")
        if isinstance(aliases, list) and model_id in aliases:
            return replace(self, alias=str(model_id))
        return None

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

    def launch_mode(self) -> str:
        """``access.launch_mode``, ``full`` when absent (an invalid value is a profile error)."""
        access = self.data.get("access")
        return str((access.get("launch_mode") if isinstance(access, dict) else None) or "full")

    def effort(self, role: str) -> str | None:
        """The model's own effort level for ``role``: ``effort_map[effort_by_role[role]]``, else ``None``."""
        access = self.data.get("access")
        if not isinstance(access, dict) or not isinstance(access.get("effort_by_role"), dict) \
                or not isinstance(access.get("effort_map"), dict):
            return None
        key = access["effort_by_role"].get(role)
        level = access["effort_map"].get(key) if isinstance(key, str) else None
        return str(level) if level is not None else None

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


def _effort_errors(access: dict[str, Any], name: str) -> list[str]:
    """``access.effort_by_role``: each role names an ``effort_map`` key with a known level."""
    by_role = access["effort_by_role"]
    if not isinstance(by_role, dict):
        return [f"profile {name}: `access.effort_by_role` must be a mapping of role → effort_map key"]
    levels = access.get("effort_map") if isinstance(access.get("effort_map"), dict) else {}
    out = []
    for role, key in by_role.items():
        if role not in ROLES:
            out.append(f"profile {name}: `access.effort_by_role` names unknown role {role!r}; "
                       f"expected {', '.join(ROLES)}")
        elif not isinstance(key, str) or key not in levels or str(levels[key]).lower() == "unknown":
            out.append(f"profile {name}: `access.effort_by_role.{role}` is {key!r}, not an effort_map key "
                       f"with a known level ({', '.join(str(k) for k, v in levels.items() if str(v).lower() != 'unknown')})")
    return out


def _structure_errors(data: dict[str, Any], name: str) -> list[str]:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
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
        if "launch_mode" in access and access["launch_mode"] not in LAUNCH_MODES:
            out.append(f"profile {name}: `access.launch_mode` must be full or bare, not {access['launch_mode']!r}")
        if "effort_by_role" in access:
            out += _effort_errors(access, name)
    fit = data.get("role_fit")
    if "role_fit" in data and not isinstance(fit, dict):
        out.append("`role_fit` must be a mapping of role → {score, reason}")
    elif isinstance(fit, dict):
        for role, v in fit.items():
            if not isinstance(v, dict) or not isinstance(v.get("score"), int) or isinstance(v.get("score"), bool):
                out.append(f"`role_fit.{role}` must be a mapping with an integer `score`")
    aliases = data.get("aliases")
    if "aliases" in data and not (isinstance(aliases, list) and all(isinstance(a, str) for a in aliases)):
        out.append("`aliases` must be a list of model ids")
    if "cost_usd_per_mtok" in data and not isinstance(data["cost_usd_per_mtok"], dict):
        out.append("`cost_usd_per_mtok` must be a mapping")
    if "researched" in data and _as_date(data["researched"]) is None:
        out.append(f"`researched` is not a calendar date (YYYY-MM-DD): {data['researched']!r}")
    return out


def _guidance_bypass_error(raw: Any) -> str | None:
    """Why ``guidance_bypass_observed`` is not ``{date: YYYY-MM-DD, harness: <harness id>, evidence: <text>}``."""
    if not isinstance(raw, dict) or set(raw) != set(GUIDANCE_BYPASS_FIELDS):
        return f"must be a mapping with exactly {', '.join(GUIDANCE_BYPASS_FIELDS)}"
    day = raw["date"]
    if not (type(day) is date or isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)) \
            or _as_date(day) is None:
        return f"date is not a calendar date (YYYY-MM-DD): {day!r}"
    if raw["harness"] not in GUIDANCE_BYPASS_HARNESSES:
        return f"harness must be one of {', '.join(GUIDANCE_BYPASS_HARNESSES)}, not {raw['harness']!r}"
    if not isinstance(raw["evidence"], str) or not raw["evidence"].strip():
        return "evidence must be a non-blank string"
    return None


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
    why = _guidance_bypass_error(data[GUIDANCE_BYPASS_KEY]) if GUIDANCE_BYPASS_KEY in data else None
    errors += _structure_errors(data, path.stem) + ([f"`{GUIDANCE_BYPASS_KEY}` {why}"] if why else [])
    return Profile(path, data, _sections(body), errors)


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


def unmatched_roster_ids(
    entries: list[dict[str, Any]],
    resolve: Callable[[dict[str, Any]], Profile | None],
) -> list[str]:
    """Roster entry ``id`` values ``resolve(entry)`` could not match to any profile.

    Entries with ``family: human`` are omitted: a person is not a model profile.
    """
    out: list[str] = []
    for entry in entries:
        if entry.get("family") == "human":
            continue
        if resolve(entry) is None:
            out.append(entry["id"])
    return out


def profile_for_entry(repo_root: Path, entry: dict[str, Any]) -> Profile | None:
    """The roster entry's profile **from the working tree**: its ``profile`` path, else the first
    profile whose :meth:`Profile.for_id` matches its ``id``.

    Routing and dispatch use :func:`orchestration_pinned.pinned_profile_for_entry`,
    which reads the same path from the integration branch.
    """
    rel = entry.get("profile")
    if rel:
        why = profile_rel_problem(repo_root, str(rel))
        if why:
            return Profile(repo_root / str(rel), {}, errors=[why])
        prof = load_profile((repo_root / str(rel)).resolve())
        return prof.for_id(entry.get("id")) or prof
    return next((m for p in list_profiles(repo_root) if (m := p.for_id(entry.get("id")))), None)


def closest_profile(model_id: str, profiles: list[Profile]) -> Profile | None:
    """The profile with a name (``api_id``, file name or alias) most like ``model_id``, ``None`` when
    no name reaches :data:`CLOSEST_MIN_RATIO`."""
    def score(p: Profile) -> float:
        aliases = p.data.get("aliases") if isinstance(p.data.get("aliases"), list) else []
        names = [str(p.data.get("api_id") or ""), p.path.stem, *map(str, aliases)]
        return max(SequenceMatcher(None, model_id, n).ratio() for n in names)
    best = max(profiles, key=score, default=None)
    return best if best is not None and score(best) >= CLOSEST_MIN_RATIO else None


#: Harness/vendor tokens a roster id may carry before a model's own id (``cursor-gpt-5.6-sol-high``).
_ID_PREFIXES = ("cursor", "codex", "copilot", "agy", "anthropic", "openai", "google", "xai")
#: Effort tokens a roster id may carry after it (``gpt-5.6-sol-high``).
_ID_SUFFIXES = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _norm_id(name: str) -> str:
    return re.sub(r"[._]", "-", name.lower())


def _id_forms(model_id: str) -> set[str]:
    """``model_id`` normalised, with and without one known prefix and one known effort suffix."""
    forms = {_norm_id(model_id)}
    forms |= {f[len(pre) + 1:] for f in list(forms) for pre in _ID_PREFIXES if f.startswith(pre + "-")}
    forms |= {f.rsplit("-", 1)[0] for f in list(forms) if f.rsplit("-", 1)[-1] in _ID_SUFFIXES and "-" in f}
    return forms


def near_miss_profile(model_id: str, profiles: list[Profile]) -> Profile | None:
    """The one profile whose ``api_id``, file name or alias equals ``model_id`` up to punctuation
    and a harness/vendor prefix or effort suffix (:func:`_id_forms`); ``None`` when none or several do."""
    forms = _id_forms(model_id)
    hits: dict[str, Profile] = {}
    for p in profiles:
        aliases = p.data.get("aliases") if isinstance(p.data.get("aliases"), list) else []
        if forms & {_norm_id(str(n)) for n in (p.api_id, p.path.stem, *aliases)}:
            hits.setdefault(p.api_id, p)
    return next(iter(hits.values())) if len(hits) == 1 else None


def _near_miss_fix(repo_root: Path, model_id: str, bundled: list[Profile]) -> str:
    """The roster line that matches ``model_id`` to its near-miss bundled profile, ``""`` without one."""
    near = near_miss_profile(model_id, bundled)
    if near is None:
        return ""
    rel = f"{PROFILES_REL.as_posix()}/{near.path.relative_to(bundled_profiles_root() / PROFILES_REL).as_posix()}"
    add = "" if (repo_root / rel).is_file() else ", then run `specy-road refresh-profiles` to add the file"
    return (f"; it differs from bundled api_id {near.api_id} only in punctuation or a vendor/effort "
            f"prefix or suffix: add `profile: {rel}` to that entry{add}")


def bundled_profiles_root() -> Path:
    """The project template whose ``model-profiles/`` this specy-road version ships."""
    return specy_road_package_dir() / "templates" / "project"


def _launchable(entry: dict[str, Any]) -> bool:
    """The entry names a ``harness`` or a ``channels.cli``, so a worker can be started for it."""
    channels = entry.get("channels")
    return bool(entry.get("harness") or (isinstance(channels, dict) and channels.get("cli")))


def _profile_hint(repo_root: Path, model_id: str, profiles: list[Profile]) -> str:
    """What to do about an unmatched ``model_id``, naming a profile only when its name is close."""
    near = closest_profile(model_id, profiles)
    if near:
        return (f"closest profile is {display_rel(repo_root, near.path)} (api_id {near.data.get('api_id')}); "
                "list the id in its `aliases` or give the entry `profile:`")
    if not profiles:
        return f"no profiles under {PROFILES_REL}/; add one or give the entry `profile:`"
    return f"no profile under {PROFILES_REL}/ has a close name; add one or give the entry `profile:`"


def roster_profile_gaps(repo_root: Path) -> list[tuple[bool, str]]:
    """``(launchable, message)`` per working-tree roster entry with an ``executor`` or ``reviewer``
    role that :func:`profile_for_entry` matches to no profile, naming the closest one if any is
    close: without a match the profile's model notes never reach that entry's prompts. ``launchable``
    is :func:`_launchable`; an entry nothing can launch is only a notice, and the starter's
    untouched placeholder (:data:`STARTER_PLACEHOLDER_ID`) is not reported."""
    config, err = load_orchestration_config(repo_root)
    if err or not config:
        return []
    entries = [e for e in config.get("roster") or []
               if {"executor", "reviewer"} & set(e.get("roles") or [])
               and (_launchable(e) or e.get("id") != STARTER_PLACEHOLDER_ID)]
    missing = unmatched_roster_ids(entries, lambda entry: profile_for_entry(repo_root, entry))
    profiles = list_profiles(repo_root) if missing else []
    bundled = list_profiles(bundled_profiles_root()) if missing else []
    by_id = {e["id"]: e for e in entries}
    out = []
    for mid in missing:
        hint = _profile_hint(repo_root, str(mid), profiles) + _near_miss_fix(repo_root, str(mid), bundled)
        out.append((_launchable(by_id[mid]),
                    f"roster entry {mid!r} in roadmap/orchestration.yaml matches no model profile by api_id, "
                    f"file name or alias, so its model notes never reach its prompts; {hint}"))
    return out
