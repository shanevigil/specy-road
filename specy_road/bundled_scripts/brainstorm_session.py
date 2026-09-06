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

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.roadmap_edit_fields import title_to_codename

SESSION_VERSION = 1
SESSION_PREFIX = "brainstorm-"
SESSION_SUFFIX = ".yaml"
PROMPT_SUFFIX = "-prompt.md"

#: What an idea is, for the recommend pass and for `promote`'s node type.
IDEA_KINDS = ("feature", "capability", "risk", "research", "experiment")
IDEA_STATUSES = ("proposed", "accepted", "rejected", "revised")
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
        raise BrainstormError(
            f"idea {ident}: kind {kind!r} not one of {', '.join(IDEA_KINDS)}"
        )
    status = _str_field(raw, "status", "proposed") or "proposed"
    if status not in IDEA_STATUSES:
        raise BrainstormError(
            f"idea {ident}: status {status!r} not one of {', '.join(IDEA_STATUSES)}"
        )
    rec = _opt_str_field(raw, "recommendation")
    if rec is not None and rec not in RECOMMENDATIONS:
        raise BrainstormError(
            f"idea {ident}: recommendation {rec!r} not one of "
            f"{', '.join(RECOMMENDATIONS)}"
        )
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
    )


@dataclass
class BrainstormSession:
    slug: str
    topic: str = ""
    under: str | None = None
    mode: str = "brainstorm"
    ideas: list[Idea] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SESSION_VERSION,
            "slug": self.slug,
            "topic": self.topic,
            "under": self.under,
            "mode": self.mode,
            "ideas": [i.to_dict() for i in self.ideas],
        }

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
    path = session_path(root, slug)
    if not path.is_file():
        raise BrainstormError(
            f"no brainstorm session {slug!r} (looked for {path.name} in work/)"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise BrainstormError(f"cannot read {path.name}: {e}") from e
    if not isinstance(raw, dict):
        raise BrainstormError(f"{path.name} is not a YAML mapping")
    if raw.get("version") != SESSION_VERSION:
        raise BrainstormError(
            f"{path.name}: unsupported version {raw.get('version')!r} "
            f"(expected {SESSION_VERSION})"
        )
    mode = _str_field(raw, "mode", "brainstorm") or "brainstorm"
    if mode not in MODES:
        raise BrainstormError(
            f"{path.name}: mode {mode!r} not one of {', '.join(MODES)}"
        )
    ideas_raw = raw.get("ideas")
    ideas = [idea_from_dict(i) for i in ideas_raw] if isinstance(ideas_raw, list) else []
    seen: set[str] = set()
    for i in ideas:
        if i.id.upper() in seen:
            raise BrainstormError(f"{path.name}: duplicate idea id {i.id}")
        seen.add(i.id.upper())
    return BrainstormSession(
        slug=_str_field(raw, "slug") or slug,
        topic=_str_field(raw, "topic"),
        under=_opt_str_field(raw, "under"),
        mode=mode,
        ideas=ideas,
    )


def write_session(root: Path, session: BrainstormSession) -> Path:
    path = session_path(root, session.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            session.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
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
