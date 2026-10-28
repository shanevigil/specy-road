"""Brainstorm session file under ``work/brainstorm-<slug>.yaml``.

One session holds the raw output of a diverge pass and the PM's triage of it.
It is a tracked artifact of record, like ``work/brief-*.md``: the ideas that
were rejected are as much a part of the reasoning trail as the ones that became
roadmap nodes, and a later session that re-proposes a parked idea should be
able to see it was already considered.

The session is never part of the merged graph, so it is validated here rather
than by a ``schemas/*.json``. Nothing outside the brainstorm modules reads it.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.brainstorm_fields import (
    extra_to_dict,
    parse_extra,
)
from specy_road.bundled_scripts.roadmap_edit_fields import title_to_codename
from specy_road.history_cache import CACHE_DIR, ensure_cache_dir
from specy_road.worker_lock import _lock_file

SESSION_VERSION = 2
#: v1 files (no rounds, URL-only evidence) read as-is and are written back as v2.
READABLE_VERSIONS = (1, 2)
SESSION_PREFIX = "brainstorm-"
SESSION_SUFFIX = ".yaml"
PROMPT_SUFFIX = "-prompt.md"

#: What an idea is, for the recommend pass and for `promote`'s node type.
IDEA_KINDS = ("feature", "capability", "risk", "research", "experiment", "refactor", "platform")
IDEA_STATUSES = ("proposed", "accepted", "rejected", "revised", "parked")
RECOMMENDATIONS = ("strong", "consider", "park")
MODES = ("brainstorm", "roadmap")

#: Ideas the converge pass keeps: `promote` turns exactly these into nodes.
PROMOTABLE_STATUSES = ("accepted",)

#: What `slugify` can emit, and therefore all a slug is ever allowed to be.
#: A slug reaches us straight from `--slug` or from a GUI request body and is
#: interpolated into a filename, so anything with a separator or a `..` in it
#: would write outside `work/` — `x/../../roadmap/registry` resolves onto the
#: tracked registry file.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX_LEN = 80


class BrainstormError(ValueError):
    """A brainstorm session could not be read, written, or mutated.

    A ``ValueError`` so that ``run_forwarded_cli`` already prints it as
    ``error: <message>`` and exits 1, like every other bundled CLI.
    """


def slugify(text: str) -> str:
    """Kebab-case slug for a session name, or '' when nothing survives."""
    return title_to_codename(text)


def work_dir(root: Path) -> Path:
    return root / "work"


def validate_slug(slug: str) -> str:
    """The slug, or raise if it is not a bare kebab-case name.

    Every path this module builds goes through here, so a slug can only ever
    name a file directly inside ``work/``.
    """
    cleaned = (slug or "").strip()
    if not cleaned:
        raise BrainstormError("session slug is empty")
    if len(cleaned) > SLUG_MAX_LEN:
        raise BrainstormError(
            f"session slug is longer than {SLUG_MAX_LEN} characters"
        )
    if not SLUG_RE.match(cleaned):
        raise BrainstormError(
            f"invalid session slug {cleaned!r} — expected lowercase letters, "
            "digits and single hyphens, as `slugify` produces"
        )
    return cleaned


def session_path(root: Path, slug: str) -> Path:
    """Path to ``work/brainstorm-<slug>.yaml``."""
    safe = validate_slug(slug)
    return work_dir(root) / f"{SESSION_PREFIX}{safe}{SESSION_SUFFIX}"


def prompt_path(root: Path, slug: str) -> Path:
    """Path to ``work/brainstorm-<slug>-prompt.md`` (regenerated, gitignored)."""
    safe = validate_slug(slug)
    return work_dir(root) / f"{SESSION_PREFIX}{safe}{PROMPT_SUFFIX}"


def list_slugs(root: Path) -> list[str]:
    """Slugs of every session in ``work/``, sorted."""
    base = work_dir(root)
    if not base.is_dir():
        return []
    out = []
    for p in base.glob(f"{SESSION_PREFIX}*{SESSION_SUFFIX}"):
        name = p.name[len(SESSION_PREFIX):-len(SESSION_SUFFIX)]
        if name:
            out.append(name)
    return sorted(out)


def resolve_slug(root: Path, slug: str | None) -> str:
    """The session to act on: the one named, or the only one that exists.

    Omitting ``--slug`` is the common case — a PM usually has one brainstorm
    open — but guessing between several would silently triage the wrong one.
    """
    if slug and slug.strip():
        return validate_slug(slug)
    found = list_slugs(root)
    if not found:
        raise BrainstormError(
            "no brainstorm sessions in work/ — start one with: "
            "specy-road brainstorm start --topic '<question>'"
        )
    if len(found) > 1:
        listed = ", ".join(found)
        raise BrainstormError(
            f"several brainstorm sessions open ({listed}) — pass --slug SLUG"
        )
    return found[0]


@dataclass
class Idea:
    """One raw idea. Only ``id`` and ``title`` are ever required."""

    id: str
    title: str
    rationale: str = ""
    kind: str = "feature"
    effort: str = ""
    evidence: list[str] = field(default_factory=list)
    status: str = "proposed"
    recommendation: str | None = None
    promoted_node_key: str | None = None
    # v2 (brainstorm_fields): provenance, structured evidence, clusters,
    # critics, decision records. Omitted from the file when empty.
    origin: dict[str, str] | None = None
    cluster_id: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    overlap: list[dict[str, str]] = field(default_factory=list)
    critic: dict[str, str] | None = None
    hypothesis: str = ""
    assumptions: list[str] = field(default_factory=list)
    decision: dict[str, str] | None = None
    verdict_why: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "rationale": self.rationale,
            "kind": self.kind,
            "effort": self.effort,
            "evidence": list(self.evidence),
            "status": self.status,
            "recommendation": self.recommendation,
            "promoted_node_key": self.promoted_node_key,
            **extra_to_dict(self),
        }


def _str_field(raw: dict[str, Any], key: str, default: str = "") -> str:
    v = raw.get(key, default)
    return v.strip() if isinstance(v, str) else default


def _opt_str_field(raw: dict[str, Any], key: str) -> str | None:
    v = raw.get(key)
    return v.strip() if isinstance(v, str) and v.strip() else None


def idea_from_dict(raw: Any) -> Idea:
    if not isinstance(raw, dict):
        raise BrainstormError(f"idea must be a mapping, got {type(raw).__name__}")
    ident = _str_field(raw, "id")
    title = _str_field(raw, "title")
    if not ident:
        raise BrainstormError("idea is missing an id")
    if not title:
        raise BrainstormError(f"idea {ident} is missing a title")
    kind = _str_field(raw, "kind", "feature") or "feature"
    if kind not in IDEA_KINDS:
        raise BrainstormError(f"idea {ident}: kind {kind!r} not one of {', '.join(IDEA_KINDS)}")
    status = _str_field(raw, "status", "proposed") or "proposed"
    if status not in IDEA_STATUSES:
        raise BrainstormError(f"idea {ident}: status {status!r} not one of {', '.join(IDEA_STATUSES)}")
    rec = _opt_str_field(raw, "recommendation")
    if rec is not None and rec not in RECOMMENDATIONS:
        raise BrainstormError(f"idea {ident}: recommendation {rec!r} not one of {', '.join(RECOMMENDATIONS)}")
    ev_raw = raw.get("evidence")
    evidence = [
        e.strip() for e in ev_raw if isinstance(e, str) and e.strip()
    ] if isinstance(ev_raw, list) else []
    return Idea(
        id=ident,
        title=title,
        rationale=_str_field(raw, "rationale"),
        kind=kind,
        effort=_str_field(raw, "effort"),
        evidence=evidence,
        status=status,
        recommendation=rec,
        promoted_node_key=_opt_str_field(raw, "promoted_node_key"),
        **parse_extra(raw, ident),
    )


@dataclass
class BrainstormSession:
    slug: str
    topic: str = ""
    under: str | None = None
    mode: str = "brainstorm"
    ideas: list[Idea] = field(default_factory=list)
    # v2: the frame the PM agreed, the allocation grid, which diverge round
    # is current, the lens profile, and how many independent shards.
    frame: dict[str, str] = field(default_factory=dict)
    allocation: str = ""
    round: int = 1
    rounds: int = 2       # planned diverge rounds (`start --rounds`); next-round warns past it
    profile: str = "product"
    panel: int = 0

    def to_dict(self) -> dict[str, Any]:
        out = {
            "version": SESSION_VERSION,
            "slug": self.slug,
            "topic": self.topic,
            "under": self.under,
            "mode": self.mode,
            "round": self.round,
            "rounds": self.rounds,
            "profile": self.profile,
        }
        if self.panel:
            out["panel"] = self.panel
        if self.frame:
            out["frame"] = dict(self.frame)
        if self.allocation:
            out["allocation"] = self.allocation
        out["ideas"] = [i.to_dict() for i in self.ideas]
        return out

    def by_id(self, idea_id: str) -> Idea:
        want = idea_id.strip().upper()
        for i in self.ideas:
            if i.id.upper() == want:
                return i
        raise BrainstormError(f"no idea {idea_id!r} in session {self.slug!r}")

    def next_idea_id(self) -> str:
        """``B1``, ``B2``, … — max existing + 1, so ids are never reused."""
        highest = 0
        for i in self.ideas:
            digits = i.id[1:] if i.id[:1].upper() == "B" else ""
            if digits.isdigit():
                highest = max(highest, int(digits))
        return f"B{highest + 1}"

    def with_status(self, status: str) -> list[Idea]:
        return [i for i in self.ideas if i.status == status]


def read_session(root: Path, slug: str) -> BrainstormSession:
    """The session in ``work/``; a bad file is reported with its fix, never coerced or rewritten."""
    path = session_path(root, slug)
    if not path.is_file():
        raise BrainstormError(f"no brainstorm session {slug!r} (looked for {path.name} in work/)")
    try:
        return _session_from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), slug)
    except (OSError, yaml.YAMLError) as e:
        raise BrainstormError(f"cannot read work/{path.name}: {e}") from e
    except BrainstormError as e:
        raise BrainstormError(f"work/{path.name}: {e}") from e


def _ideas_from_list(ideas_raw: Any) -> list[Idea]:
    try:
        ideas = [idea_from_dict(i) for i in ideas_raw] if isinstance(ideas_raw, list) else []
    except BrainstormError as e:
        fix = "use one of those or remove the key" if " not one of " in str(e) else "fix or remove that entry"
        raise BrainstormError(f"{e} — edit the file: {fix}") from e
    seen: set[str] = set()
    for i in ideas:
        if i.id.upper() in seen:
            raise BrainstormError(f"duplicate idea id {i.id} — edit the file: renumber one of them")
        seen.add(i.id.upper())
    return ideas


def _session_from_dict(raw: Any, slug: str) -> BrainstormSession:
    if not isinstance(raw, dict):
        raise BrainstormError("not a YAML mapping — edit the file or move it out of work/")
    if raw.get("version") not in READABLE_VERSIONS:
        raise BrainstormError(f"unsupported version {raw.get('version')!r} (expected {SESSION_VERSION}) "
                              "— upgrade specy-road or edit the file")
    mode = _str_field(raw, "mode", "brainstorm") or "brainstorm"
    if mode not in MODES:
        raise BrainstormError(f"mode {mode!r} not one of {', '.join(MODES)} "
                              "— edit the file: use one of those or remove the key")
    ideas = _ideas_from_list(raw.get("ideas"))
    frame = raw.get("frame") if isinstance(raw.get("frame"), dict) else {}
    rnd = raw.get("round")
    planned = raw.get("rounds")
    file_slug = _str_field(raw, "slug")
    if file_slug and file_slug != slug:
        raise BrainstormError(f"says slug {file_slug!r}; a session file is named after its slug "
                              f"— edit the file: set slug: {slug}")
    return BrainstormSession(
        slug=file_slug or slug,
        topic=_str_field(raw, "topic"),
        under=_opt_str_field(raw, "under"),
        mode=mode,
        ideas=ideas,
        frame={str(k): str(v) for k, v in frame.items()},
        allocation=_str_field(raw, "allocation"),
        round=rnd if isinstance(rnd, int) and rnd >= 1 else 1,
        rounds=planned if isinstance(planned, int) and planned >= 1 else 2,
        profile=_str_field(raw, "profile", "product") or "product",
        panel=raw.get("panel") if isinstance(raw.get("panel"), int) else 0,
    )


def write_session(root: Path, session: BrainstormSession) -> Path:
    path = session_path(root, session.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Temp file + replace: a panel shard reading mid-write sees the old or the new session, never half.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(
        yaml.dump(session.to_dict(), default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def add_idea(session: BrainstormSession, **fields: Any) -> Idea:
    """Append a new idea, allocating its id. Validates through ``idea_from_dict``."""
    raw = {"id": session.next_idea_id(), **fields}
    idea = idea_from_dict(raw)
    session.ideas.append(idea)
    return idea


def set_status(session: BrainstormSession, idea_id: str, status: str) -> Idea:
    """Move one idea to ``status``, refusing to re-triage promoted ideas."""
    if status not in IDEA_STATUSES:
        raise BrainstormError(
            f"status {status!r} not one of {', '.join(IDEA_STATUSES)}"
        )
    idea = session.by_id(idea_id)
    if idea.promoted_node_key:
        raise BrainstormError(
            f"idea {idea.id} is already on the roadmap as {idea.promoted_node_key} — "
            "edit the node instead"
        )
    idea.status = status
    return idea


@contextmanager
def session_lock(root: Path):
    """The repo's brainstorm lock: hold it around every load-mutate-write of a session.

    Panel shards run ``add-idea`` in parallel, and the PM GUI writes the same
    files; without one lock around load, ``B<n>`` allocation and write, two take
    the same id and the last writer drops the other's idea. The lock file lives
    in the ignored ``.specyrd/cache/`` so it never shows up as an untracked file.
    """
    lock = root / CACHE_DIR / "brainstorm.lock"
    ensure_cache_dir(lock.parent)
    with lock.open("a+") as f:
        unlock = _lock_file(f)
        try:
            yield
        finally:
            unlock()
