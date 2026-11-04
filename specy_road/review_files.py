"""Read and validate the review hand-off files under ``work/reviews/<NODE_ID>/``.

Two kinds of file, each Markdown with a YAML front matter block that is the
machine-readable part:

* ``READY-<agent>.md`` — an executor's hand-off: branch, commit, base, changed
  paths, and the tail of each verify command
  (``schemas/handoff.schema.json``).
* ``REVIEW-<model>.md`` — one reviewer's verdict on one commit
  (``schemas/review-record.schema.json``). ``review record`` overwrites it
  each round and keeps a copy of every filing under ``history/``, which is
  what escalation counts rounds from (``review_rca``).

Beside them, ``RCA-<round>.md`` is a root-cause analysis of a stalled review
loop (``schemas/rca-record.schema.json``).

Plain files work across every harness, including IDE chats that cannot see
each other: the executor writes READY, reviewers write REVIEW beside it, and the
coordinator polls the directory. Both schemas ship in the wheel, like
``archive.schema.json``, so adopters get fixes by upgrading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_text
from specy_road.runtime_paths import specy_road_package_dir
from specy_road.schema_revision import accepted_at_revision

REVIEWS_REL = Path("work") / "reviews"
READY_PREFIX = "READY-"
REVIEW_PREFIX = "REVIEW-"
RCA_PREFIX = "RCA-"
HISTORY_DIRNAME = "history"
PACKET_NAME = "PACKET.md"
#: The interactive approver. A solo maintainer both coordinates and reviews, so
#: only this model may attest ``is_coordinator: true``.
HUMAN = "human"
#: How a reviewer's harness was started (``review record --launch-mode``): ``full`` loads the
#: repository's hooks and MCP servers, ``bare`` none (Claude Code ``--bare``), ``explicit`` only what the command names.
REVIEW_LAUNCH_MODES = ("full", "bare", "explicit")


@dataclass
class ReviewFile:
    path: Path
    data: dict[str, Any]
    body: str
    errors: list[str] = field(default_factory=list)
    on_disk: Path | None = None   # the file itself, when its name differs from ``path`` only in case

    @property
    def ok(self) -> bool:
        return not self.errors


def _main_checkout(top: Path) -> Path | None:
    """The main worktree of the linked worktree at ``top``, from ``.git`` and ``commondir``: git is never run,
    so a process git refuses to serve (a sandbox, an ownership check) finds what every other command does."""
    try:
        line = (top / ".git").read_text(encoding="utf-8").strip() if (top / ".git").is_file() else ""
    except OSError:
        return None
    gitdir = Path(top, line.removeprefix("gitdir:").strip())   # absolute, or relative to top
    try:
        common = Path(gitdir, (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:   # unreadable or absent: git's own <common>/worktrees/<name> layout, else not a worktree
        common = gitdir.parent.parent.resolve() if gitdir.parent.name == "worktrees" else None
    linked = line.startswith("gitdir:") and common and common.name == ".git"   # not bare, not a submodule
    return common.parent if linked else None


def reviews_root(repo_root: Path) -> Path:
    """``work/reviews`` in the **main** worktree, whichever linked worktree asks: the one resolver, since
    it is gitignored and each worktree would have its own empty copy. A project nested below the git root
    (``sr/``) or a fixture inside another checkout keeps its own ``work/``, at the same place."""
    here = Path(repo_root).resolve()
    top = next((p for p in (here, *here.parents) if (p / ".git").exists()), None)   # git's own discovery
    main = _main_checkout(top) if top else None
    return main / here.relative_to(top) / REVIEWS_REL if main else repo_root / REVIEWS_REL


def reviews_dir(repo_root: Path, node_id: str) -> Path:
    return reviews_root(repo_root) / node_id


def review_path(repo_root: Path, node_id: str, model: str) -> Path:
    return reviews_dir(repo_root, node_id) / f"{REVIEW_PREFIX}{model}.md"


def write_review(path: Path, text: str) -> None:
    """Write ``path`` under its exact name; on macOS APFS writing over ``review-x.md`` would keep that name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for p in path.parent.iterdir():
        if p.name.lower() == path.name.lower() and p.is_file():
            p.unlink()
    path.write_text(text, encoding="utf-8")


@cache
def _validator(name: str) -> Draft202012Validator:
    path = specy_road_package_dir() / "schemas" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def _schema_errors(data: dict[str, Any], schema_name: str, path: Path) -> list[str]:
    out = []
    for e in sorted(_validator(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
        out.append(f"{loc}: {e.message}")
    return [] if out and accepted_at_revision(data, f"schemas/{schema_name}", path, data.get("commit") or "") else out


_SHA_KEYS = ("commit", "base")


def _split_front_matter(text: str) -> tuple[str | None, str]:
    """``(yaml_block, body)``; the block ends at the first unindented ``---`` line."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def _scalars_to_str(data: dict[str, Any], root: Any) -> None:
    """Undo YAML's typing of values the schemas want as strings.

    An unquoted ``2026-10-26`` loads as a date. A SHA is worse: YAML 1.1 reads
    ``1234567`` as an int, ``0123456`` as octal and ``0x1234567`` as hex, so
    converting the loaded value back would yield a different string — or a
    different, valid-looking SHA. ``commit`` and ``base`` are therefore taken
    from the parsed node's raw scalar text (``root`` is ``yaml.compose``'s
    result), which no other line of the file can impersonate.
    """
    for key, value in list(data.items()):
        if isinstance(value, date):
            data[key] = value.isoformat()
    if not isinstance(root, yaml.MappingNode):
        return
    for k, v in root.value:
        if isinstance(k, yaml.ScalarNode) and k.value in _SHA_KEYS and isinstance(v, yaml.ScalarNode):
            data[k.value] = v.value


def _read(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {}, "", [f"cannot read: {e}"]
    block, body = _split_front_matter(text)
    missing = ["missing YAML front matter (--- … ---) at the top of the file"]
    if block is None:
        return {}, body, missing
    try:
        data = yaml.safe_load(block)
        root = yaml.compose(block, Loader=yaml.SafeLoader)
    except yaml.YAMLError as e:
        return {}, body, [f"front matter is not valid YAML: {e}"]
    if not isinstance(data, dict) or not data:
        return {}, body, missing
    _scalars_to_str(data, root)
    return data, body, []


def ready_semantic_errors(data: dict[str, Any], acceptance_ids: list[str] | None = None) -> list[str]:
    """Rules the handoff schema cannot express. ``acceptance_ids`` comes from the brief."""
    errs: list[str] = []
    blocked = data.get("blocked_on") or []
    if acceptance_ids is not None and blocked:
        known = set(acceptance_ids)
        for entry in blocked:
            aid = entry.get("acceptance")
            if aid not in known:
                errs.append(f"blocked_on: {aid} not in the brief")
    return errs


def load_ready(path: Path, node_id: str | None = None, branch: str | None = None,
               acceptance_ids: list[str] | None = None) -> ReviewFile:
    """Parse one READY file; with ``node_id`` / ``branch``, bind it to that provenance.

    A file under ``work/reviews/M1.1/`` whose front matter names another node
    or branch is a misfiled hand-off, not this node's: it is invalid here, so
    it never feeds the packet, ``handoff status`` or a worker's completion.
    """
    data, body, errs = _read(path)
    if not errs:
        errs = _schema_errors(data, "handoff.schema.json", path)
    if not errs and node_id is not None and data.get("node_id") != node_id:
        errs.append(f"node_id is {data.get('node_id')!r}, not {node_id!r} (misfiled hand-off)")
    if not errs and branch is not None and data.get("branch") != branch:
        errs.append(f"branch is {data.get('branch')!r}, not the registered {branch!r}")
    if not errs:
        errs = ready_semantic_errors(data, acceptance_ids)
    return ReviewFile(path, data, body, errs)


def review_semantic_errors(data: dict[str, Any], acceptance_ids: list[str] | None = None) -> list[str]:
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
        # An `n/a` on an id the brief lacks (a criterion moved to another leaf and
        # still named in the summary) carries no judgment; a pass or fail on one does.
        unknown = sorted(k for k in set(results) - set(acceptance_ids) if results[k] != "n/a")
        if missing:
            errs.append(f"acceptance: no result for {', '.join(missing)}")
        if unknown:
            errs.append(f"acceptance: {', '.join(unknown)} not in the brief")
    return errs


def load_review(path: Path, acceptance_ids: list[str] | None = None) -> ReviewFile:
    data, body, errs = _read(path)
    if not errs:
        errs = _schema_errors(data, "review-record.schema.json", path)
    if not errs:
        errs = review_semantic_errors(data, acceptance_ids)
    return ReviewFile(path, data, body, errs)


def _files(repo_root: Path, node_id: str, prefix: str, any_case: bool = False) -> list[Path]:
    d = reviews_dir(repo_root, node_id)
    if not d.is_dir():
        return []
    fold = str.lower if any_case else str
    return sorted(p for p in d.iterdir()
                  if fold(p.name).startswith(fold(prefix)) and fold(p.suffix) == ".md" and p.is_file())


def list_ready(repo_root: Path, node_id: str, branch: str | None = None,
               acceptance_ids: list[str] | None = None) -> list[ReviewFile]:
    """Every READY under the node's directory, bound to that node (and ``branch`` when known)."""
    return [
        load_ready(p, node_id, branch, acceptance_ids)
        for p in _files(repo_root, node_id, READY_PREFIX)
    ]


def _canonical(r: ReviewFile) -> ReviewFile:
    """Report a record filed under another case (``review-x.md``, ``REVIEW-x.MD``) as ``REVIEW-<model>.md``."""
    name = f"{REVIEW_PREFIX}{r.data.get('model')}.md"
    if name.lower() != r.path.name.lower():   # not this model's record: fix only the prefix and extension
        name = REVIEW_PREFIX + r.path.stem[len(REVIEW_PREFIX):] + ".md"
    if name != r.path.name:
        r.path, r.on_disk = r.path.with_name(name), r.path
    return r


def list_reviews(repo_root: Path, node_id: str, acceptance_ids: list[str] | None = None) -> list[ReviewFile]:
    """Every ``REVIEW-*.md``, its prefix matched in any case and reported under the canonical name."""
    return [_canonical(load_review(p, acceptance_ids)) for p in _files(repo_root, node_id, REVIEW_PREFIX, True)]


def archive_review(repo_root: Path, node_id: str, model: str, text: str) -> Path:
    """Keep a copy of a filed record under ``history/``; names sort in filing order."""
    d = reviews_dir(repo_root, node_id) / HISTORY_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{model}.md"
    path.write_text(text, encoding="utf-8")
    return path


def list_review_history(repo_root: Path, node_id: str) -> list[ReviewFile]:
    """Every record ``review record`` has filed for the node, oldest first."""
    d = reviews_dir(repo_root, node_id) / HISTORY_DIRNAME
    return [load_review(p) for p in sorted(d.glob("*.md"))] if d.is_dir() else []


def round_span(repo_root: Path, node_id: str) -> dict[str, Any]:
    """Review rounds (distinct reviewed commits) and the time from the first filed review to the latest.

    Read from ``history/`` (each copy is written once, so its mtime is its filing
    time) plus each ``REVIEW-*.md`` with no copy there: ``REVIEW-human.md``, or one
    written by hand.
    """
    seen, times = set(), []
    for r, in_history in ([(r, True) for r in list_review_history(repo_root, node_id)]
                          + [(r, False) for r in list_reviews(repo_root, node_id)]):
        if not r.ok or r.data.get("node_id") != node_id:
            continue
        raw = r.data["commit"]   # a short and a full SHA of one commit are one round
        sha = git_text(["rev-parse", "--verify", "--quiet", f"{raw}^{{commit}}"], repo_root) or raw
        if in_history or (r.data["model"], sha) not in seen:   # not the live copy of an archived record
            seen.add((r.data["model"], sha))
            times.append((r.on_disk or r.path).stat().st_mtime)
    rounds = len({sha for _model, sha in seen})
    s = int(max(times) - min(times)) if len(times) > 1 else None
    units = ((s // 86400, "d"), (s // 3600 % 24, "h"), (s // 60 % 60, "m")) if s is not None else ()
    took = "n/a" if s is None else " ".join(f"{n}{u}" for n, u in units if n) or "under 1m"
    return {"rounds": rounds, "elapsed_seconds": s, "line": f"rounds: {rounds}, first to latest: {took}"}


def list_rcas(repo_root: Path, node_id: str) -> list[ReviewFile]:
    """``RCA-*.md`` records, schema-checked and bound to ``node_id``."""
    out = []
    for p in _files(repo_root, node_id, RCA_PREFIX):
        data, body, errs = _read(p)
        errs = errs or _schema_errors(data, "rca-record.schema.json", p)
        if not errs and data.get("node_id") != node_id:
            errs.append(f"node_id is {data.get('node_id')!r}, not {node_id!r}")
        out.append(ReviewFile(p, data, body, errs))
    return out


def latest_ready(repo_root: Path, node_id: str, branch: str | None = None,
                 acceptance_ids: list[str] | None = None) -> ReviewFile | None:
    """The most recently modified valid READY file for this node (and ``branch``), if any."""
    valid = [r for r in list_ready(repo_root, node_id, branch, acceptance_ids) if r.ok]
    return max(valid, key=lambda r: (r.path.stat().st_mtime, r.path.name), default=None)


def failing_verifier_entries(ready: ReviewFile) -> list[dict[str, Any]]:
    """Each READY ``verify`` row with a non-zero exit."""
    return [v for v in (ready.data.get("verify") or []) if v.get("exit") != 0]


def pre_existing_cmds_from_approvals(approvals: list[Any]) -> set[str]:
    """Verifier command names marked pre-existing on counted approving reviews."""
    covered: set[str] = set()
    for counted in approvals:
        for cmd in counted.review.data.get("verify_pre_existing") or []:
            covered.add(str(cmd))
    return covered


def verifier_gate_problems(ready: ReviewFile | None, approvals: list[Any]) -> list[str]:
    """Failing READY verifiers not cleared by an approving review's *verified* pre-existing claim.

    A claim counts once ``review check-pre-existing`` reproduced it on the current
    integration tip (:mod:`specy_road.review_pre_existing`).
    """
    failing = failing_verifier_entries(ready) if ready is not None else []
    if not failing:
        return []
    from specy_road.review_pre_existing import gate_problems  # it reads files through this module
    return gate_problems(ready, failing, pre_existing_cmds_from_approvals(approvals))


def non_gating_verify_problems(ready: ReviewFile | None) -> list[str]:
    """READY verifier notes that are reported but do not fail the gate (empty ``verify``)."""
    if ready is None or ready.data.get("verify"):
        return []
    return [f"{ready.path.name} (executor-reported): no verifier evidence recorded (verify is empty)"]


def executor_blocked_entries(ready: ReviewFile | None) -> list[dict[str, Any]]:
    """Non-empty ``blocked_on`` on a READY file, when present."""
    if ready is None:
        return []
    return list(ready.data.get("blocked_on") or [])


def executor_blocked_display_lines(ready: ReviewFile | None) -> list[str]:
    """One ``A<n>: <reason>`` line per ``blocked_on`` entry (handoff status)."""
    return [f"{e['acceptance']}: {e['reason']}" for e in executor_blocked_entries(ready)]


def executor_blocked_gate_problems(ready: ReviewFile | None) -> list[str]:
    """Gate failures while the current READY declares ``blocked_on``."""
    name = ready.path.name if ready else "READY"
    return [
        f"{name} (executor-blocked): blocked on {e['acceptance']}"
        for e in executor_blocked_entries(ready)
    ]


def node_ids_with_reviews(repo_root: Path) -> list[str]:
    root = reviews_root(repo_root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def render_front_matter(data: dict[str, Any], body: str = "") -> str:
    head = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{head}\n---\n{body}"
