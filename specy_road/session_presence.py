"""Presence files: which agent sessions are active in this checkout, and where.

``roadmap/registry.yaml`` makes claimed leaves visible to every clone. Work that
is not a claim — a design note, a merge, a review, a verifier's experiments —
had nothing, and on 2026-10-26 four agents in one checkout found that out
(design note ``docs/design-notes/agent-guidance-and-shared-checkouts.md``,
decisions 5 and 6).

A session records itself in ``work/.sessions/<agent-id>.yaml`` (gitignored,
and always in the **main** worktree so linked worktrees share one set): its
branch, worktree, the paths it is editing, and an expiry. ``handoff status``
lists live sessions, ``do-next-available-task`` warns when a live session's
paths overlap the leaf's touch zones, and ``session check`` refuses when
staged paths overlap another live session's. Expiry is what keeps a crashed
session from holding paths forever: nothing is enforced past the warning, and
a record older than its ``expires`` is simply ignored.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from specy_road.finish_implementation_check import zone_matches
from specy_road.git_subprocess import git_text
from specy_road.review_files import reviews_root

SESSIONS_DIRNAME = ".sessions"
DEFAULT_TTL_HOURS = 4
_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass
class Session:
    agent: str
    branch: str | None
    worktree: str | None
    paths: list[str]
    started: str
    touched: str
    expires: str
    note: str = ""
    path: Path | None = field(default=None, repr=False)

    def is_live(self, now: datetime | None = None) -> bool:
        try:
            return _parse(self.expires) > (now or _now())
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        d = {"agent": self.agent, "branch": self.branch, "worktree": self.worktree, "paths": self.paths,
             "started": self.started, "touched": self.touched, "expires": self.expires}
        if self.note:
            d["note"] = self.note
        return d


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(s: str) -> datetime:
    dt = datetime.fromisoformat(str(s))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sessions_dir(repo_root: Path) -> Path:
    return reviews_root(repo_root).parent / SESSIONS_DIRNAME


def session_path(repo_root: Path, agent: str) -> Path:
    if not _ID.match(agent):
        raise ValueError(f"agent id {agent!r}: use letters, digits, '.', '_' or '-' (max 64)")
    return sessions_dir(repo_root) / f"{agent}.yaml"


def default_agent_id() -> str:
    """``SPECY_ROAD_AGENT_ID``, else ``<user>-s<session id>``.

    The POSIX session id is shared by every command one terminal or one
    harness process runs (each ``Bash`` call, each hook), and differs between
    terminals and between harnesses, so ``start``, ``touch``, ``end`` and the
    guard from one agent name the same record without any setup. Workers are
    started in a new session and carry their own id. Set the variable when
    two agents share one terminal session.
    """
    env = os.environ.get("SPECY_ROAD_AGENT_ID", "").strip()
    if env and _ID.match(env):
        return env
    user = re.sub(r"[^A-Za-z0-9._-]", "-", os.environ.get("USER") or "agent")[:20]
    try:
        sid = os.getsid(0)
    except (AttributeError, OSError):   # Windows: no sessions; the process is the best there is
        sid = os.getpid()
    return f"{user}-s{sid}"


def load_session(path: Path) -> Session | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict) or not raw.get("agent"):
        return None
    paths = [str(p) for p in raw.get("paths") or [] if str(p).strip()]
    return Session(str(raw["agent"]), raw.get("branch"), raw.get("worktree"), paths,
                   str(raw.get("started", "")), str(raw.get("touched", "")), str(raw.get("expires", "")),
                   str(raw.get("note") or ""), path)


def list_sessions(repo_root: Path, *, live_only: bool = True, now: datetime | None = None) -> list[Session]:
    d = sessions_dir(repo_root)
    if not d.is_dir():
        return []
    out = [s for s in (load_session(p) for p in sorted(d.glob("*.yaml"))) if s]
    return [s for s in out if s.is_live(now)] if live_only else out


def start_session(repo_root: Path, agent: str, *, paths: list[str] | None, note: str = "",
                  ttl_hours: float = DEFAULT_TTL_HOURS, worktree: Path | None = None) -> Session:
    """Create or renew the record; ``paths`` replace the old set, ``None`` keeps it (``touch``)."""
    path = session_path(repo_root, agent)
    if paths is None:
        old = load_session(path) if path.is_file() else None
        paths = list(old.paths) if old else []
    now = _now()
    old = load_session(path) if path.is_file() else None
    wt = (worktree or repo_root).resolve()
    s = Session(agent, git_text(["branch", "--show-current"], wt) or None, str(wt),
                sorted({p.strip().strip("/") for p in paths if p.strip()}),
                old.started if old else now.isoformat(), now.isoformat(),
                (now + timedelta(hours=ttl_hours)).isoformat(), note or (old.note if old else ""), path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(s.to_dict(), sort_keys=False), encoding="utf-8")
    return s


def end_session(repo_root: Path, agent: str) -> bool:
    path = session_path(repo_root, agent)
    if path.is_file():
        path.unlink()
        return True
    return False


def overlaps(session: Session, paths: list[str]) -> list[tuple[str, str]]:
    """``(session_path, path)`` pairs where one contains the other."""
    out = []
    for sp in session.paths:
        for p in paths:
            q = p.strip().strip("/")
            if q and (zone_matches(sp, q) or zone_matches(q, sp)):
                out.append((sp, q))
    return out


def conflicts(repo_root: Path, paths: list[str], *, exclude: str | None = None,
              now: datetime | None = None) -> list[tuple[Session, list[tuple[str, str]]]]:
    """Live sessions, other than ``exclude``, whose paths overlap ``paths``."""
    out = []
    for s in list_sessions(repo_root, now=now):
        if s.agent == exclude:
            continue
        hits = overlaps(s, paths)
        if hits:
            out.append((s, hits))
    return out


def warn_lines(found: list[tuple[Session, list[tuple[str, str]]]], *, what: str) -> list[str]:
    lines = []
    for s, hits in found:
        where = f" on {s.branch}" if s.branch else ""
        lines.append(f"sessions: warning — {what} overlap live session {s.agent!r}{where} "
                     f"(until {s.expires}): " + ", ".join(f"'{a}' vs '{b}'" for a, b in hits[:4]))
    return lines
