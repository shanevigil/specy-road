"""Read and validate the review hand-off files under ``work/reviews/<NODE_ID>/``.

Two kinds of file, each Markdown with a YAML front matter block that is the
machine-readable part:

* ``READY-<agent>.md`` — an executor's hand-off: branch, commit, base, changed
  paths, and the tail of each verify command
  (``schemas/handoff.schema.json``).
* ``REVIEW-<model>.md`` — one reviewer's verdict on one commit
  (``schemas/review-record.schema.json``).

Plain files work across every harness, including IDE chats that cannot see
each other: the executor writes READY, reviewers write REVIEW beside it, and the
coordinator polls the directory. Both schemas ship in the wheel, like
``archive.schema.json``, so adopters get fixes by upgrading.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.bundled_scripts.planning_artifacts import split_frontmatter
from specy_road.git_subprocess import git_text
from specy_road.runtime_paths import specy_road_package_dir

REVIEWS_REL = Path("work") / "reviews"
READY_PREFIX = "READY-"
REVIEW_PREFIX = "REVIEW-"
PACKET_NAME = "PACKET.md"
#: The interactive approver. A solo maintainer both coordinates and reviews, so
#: only this model may attest ``is_coordinator: true``.
HUMAN = "human"


@dataclass
class ReviewFile:
    path: Path
    data: dict[str, Any]
    body: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def reviews_root(repo_root: Path) -> Path:
    """``work/reviews`` in the **main** worktree, whichever worktree asks.

    ``work/reviews/`` is gitignored, so each linked worktree would otherwise
    have its own empty copy: an executor in a worktree hands off into the
    coordinator's checkout, and the gate run from that worktree must read the
    same directory.
    """
    common = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo_root)
    if common and Path(common).name == ".git":
        return Path(common).parent / REVIEWS_REL
    return repo_root / REVIEWS_REL


def reviews_dir(repo_root: Path, node_id: str) -> Path:
    return reviews_root(repo_root) / node_id


def ready_path(repo_root: Path, node_id: str, agent: str) -> Path:
    return reviews_dir(repo_root, node_id) / f"{READY_PREFIX}{agent}.md"


def review_path(repo_root: Path, node_id: str, model: str) -> Path:
    return reviews_dir(repo_root, node_id) / f"{REVIEW_PREFIX}{model}.md"


@cache
def _validator(name: str) -> Draft202012Validator:
    path = specy_road_package_dir() / "schemas" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def _schema_errors(data: dict[str, Any], schema_name: str) -> list[str]:
    out = []
    for e in sorted(_validator(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
        out.append(f"{loc}: {e.message}")
    return out


_SHA_KEYS = ("commit", "base")


def _scalars_to_str(data: dict[str, Any], text: str) -> None:
    """Undo YAML's typing of values the schemas want as strings.

    An unquoted ``2026-10-26`` loads as a date. A SHA is worse: YAML 1.1 reads
    ``1234567`` as an int, ``0123456`` as octal and ``0x1234567`` as hex, so
    converting the loaded value back would yield a different string — or a
    different, valid-looking SHA. ``commit`` and ``base`` are therefore taken
    from the front matter text exactly as written.
    """
    for key, value in list(data.items()):
        if isinstance(value, date):
            data[key] = value.isoformat()
    block = text.split("\n---", 1)[0]
    for key in _SHA_KEYS:
        m = re.search(rf"^{key}:[ \t]*([\"']?)([^\"'\s#]+)\1[ \t]*(?:#.*)?$", block, re.M)
        if m and key in data:
            data[key] = m.group(2)


def _read(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {}, "", [f"cannot read: {e}"]
    data, body = split_frontmatter(text)
    if not isinstance(data, dict) or not data:
        return {}, body, ["missing YAML front matter (--- … ---) at the top of the file"]
    _scalars_to_str(data, text)
    return data, body, []


def load_ready(path: Path) -> ReviewFile:
    data, body, errs = _read(path)
    if not errs:
        errs = _schema_errors(data, "handoff.schema.json")
    return ReviewFile(path, data, body, errs)


def review_semantic_errors(
    data: dict[str, Any], acceptance_ids: list[str] | None = None
) -> list[str]:
    """Rules the schema cannot express. ``acceptance_ids`` comes from the brief."""
    errs = []
    if data.get("authored_fix"):
        errs.append("authored_fix: a session that wrote the change cannot review it")
    if data.get("is_coordinator") and data.get("model") != HUMAN:
        errs.append("is_coordinator: the coordinator's own session is never a reviewer")
    results = data.get("acceptance") or {}
    if data.get("verdict") == "approve":
        failed = sorted(k for k, v in results.items() if v == "fail")
        if failed:
            errs.append(f"verdict: approve with failing acceptance {', '.join(failed)}")
        if data.get("required_changes"):
            errs.append("verdict: approve with required_changes listed; use block")
    if acceptance_ids is not None:
        missing = [a for a in acceptance_ids if a not in results]
        unknown = sorted(set(results) - set(acceptance_ids))
        if missing:
            errs.append(f"acceptance: no result for {', '.join(missing)}")
        if unknown:
            errs.append(f"acceptance: {', '.join(unknown)} not in the brief")
    return errs


def load_review(path: Path, acceptance_ids: list[str] | None = None) -> ReviewFile:
    data, body, errs = _read(path)
    if not errs:
        errs = _schema_errors(data, "review-record.schema.json")
    if not errs:
        errs = review_semantic_errors(data, acceptance_ids)
    return ReviewFile(path, data, body, errs)


def _files(repo_root: Path, node_id: str, prefix: str) -> list[Path]:
    d = reviews_dir(repo_root, node_id)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(f"{prefix}*.md") if p.is_file())


def list_ready(repo_root: Path, node_id: str) -> list[ReviewFile]:
    return [load_ready(p) for p in _files(repo_root, node_id, READY_PREFIX)]


def list_reviews(
    repo_root: Path, node_id: str, acceptance_ids: list[str] | None = None
) -> list[ReviewFile]:
    return [load_review(p, acceptance_ids) for p in _files(repo_root, node_id, REVIEW_PREFIX)]


def latest_ready(repo_root: Path, node_id: str) -> ReviewFile | None:
    """The most recently modified valid READY file, if any."""
    valid = [r for r in list_ready(repo_root, node_id) if r.ok]
    if not valid:
        return None
    return max(valid, key=lambda r: (r.path.stat().st_mtime, r.path.name))


def node_ids_with_reviews(repo_root: Path) -> list[str]:
    root = reviews_root(repo_root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def render_front_matter(data: dict[str, Any], body: str = "") -> str:
    import yaml

    head = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{head}\n---\n{body}"
