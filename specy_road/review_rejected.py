"""Persist a ``review record`` refusal as ``REJECTED-<model>.md`` beside the hand-off (M15.33).

Coordinators could not tell a refused filing from a model that never started. The marker is not a
``REVIEW-*.md`` record (:mod:`specy_road.review_files` ignores it). A successful ``review record`` clears it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from specy_road.orchestration_config import substitute_for
from specy_road.review_files import archive_review, render_front_matter, review_path, reviews_dir, write_review
from specy_road.review_gate import evaluate_gate, rerun_problem
from specy_road.review_record_rules import check_record
from specy_road.review_signing import NOTES_KEY, SigningError, notes_digest, sign, verify
from specy_road.review_target import ReviewTargetError, milestone_open_problem, resolve_target, same_commit
from specy_road.toolkit_version import stamp_review_toolkit_version

REJECTED_PREFIX = "REJECTED-"


def rejected_path(reviews: Path, model: str) -> Path:
    return reviews / f"{REJECTED_PREFIX}{model}.md"


def write_rejected(reviews: Path, model: str, commit: str, reason: str) -> Path:
    """Write or replace the refusal marker for ``model`` at ``commit``; ``reason`` is the full stderr message."""
    reviews.mkdir(parents=True, exist_ok=True)
    refused_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    body = reason if reason.endswith("\n") else reason + "\n"
    path = rejected_path(reviews, model)
    path.write_text(render_front_matter({"commit": commit, "refused_at": refused_at}, body), encoding="utf-8")
    return path


def clear_rejected(reviews: Path, model: str) -> None:
    path = rejected_path(reviews, model)
    if path.is_file():
        path.unlink()


def _repo_root(reviews: Path) -> Path:
    return reviews.parent.parent.parent


def _age(when: datetime, now: datetime) -> str:
    seconds = max(0, int((now - when).total_seconds()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "under 1m"


def _read_marker(path: Path) -> tuple[dict, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    data = yaml.safe_load(parts[1]) or {}
    return data, parts[2]


def _parse_when(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def rejected_state(reviews: Path, model: str, commit: str | None,
                   repo_root: Path | None = None, now: datetime | None = None) -> tuple[str, str] | None:
    """``(age, first_line)`` when a marker at ``commit`` is active and no ``REVIEW-<model>`` is filed there."""
    if not commit:
        return None
    root = repo_root or _repo_root(reviews)
    path = rejected_path(reviews, model)
    parsed = _read_marker(path)
    if not parsed:
        return None
    data, body = parsed
    if not same_commit(root, data.get("commit"), commit):
        return None
    node_id = reviews.name
    rec = review_path(root, node_id, model)
    if rec.is_file():
        from specy_road.review_files import load_review

        review = load_review(rec)
        if review.ok and same_commit(root, review.data.get("commit"), commit):
            return None
    when = _parse_when(data.get("refused_at"))
    if when is None:
        return None
    first = body.strip().split("\n", 1)[0] if body.strip() else ""
    return _age(when, now or datetime.now(timezone.utc)), first


class ReviewRecordTrace:
    """Tracks whether a ``review record`` refusal should write ``REJECTED-<model>.md``."""

    def __init__(self, repo_root: Path, node_id: str, model: str) -> None:
        self.reviews = reviews_dir(repo_root, node_id)
        self.model = model
        self.commit: str | None = None
        self._active = False

    def refuse(self, msg: str, fail, *, write: bool = True) -> int:
        if write and self._active and self.commit:
            write_rejected(self.reviews, self.model, self.commit, msg)
        return fail(msg)

    def roster_resolved(self, commit: str | None) -> None:
        """Call only after the model is on the roster; later refusals may write ``REJECTED-<model>.md``."""
        self.commit = commit
        self._active = True

    def target_resolved(self, commit: str | None) -> None:
        self.roster_resolved(commit)


def run_review_record(ns: Any, root: Path, fail: Any, relabel: Any) -> int:  # noqa: C901
    """``review record`` implementation; refusals after the target and roster resolve write ``REJECTED-<model>.md``."""
    trace = ReviewRecordTrace(root, ns.node_id, ns.model)
    try:
        t = resolve_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        return fail(str(e))
    gate = evaluate_gate(root, t.node, t.commit, branch=(t.entry or {}).get("branch"))
    if gate.config_error:
        return fail(f"orchestration config: {gate.config_error}")
    if mile := milestone_open_problem(t):
        return fail(mile)
    config = gate.config
    entry = next((e for e in config["roster"] if e.get("id") == ns.model), None)
    if entry is None:
        return fail(f"{ns.model!r} is not in the roster on the integration branch "
                    "(roadmap/orchestration.yaml); a review from it would not count")
    trace.roster_resolved(gate.commit)
    rec, err = check_record(ns, root, t)
    if err:
        return trace.refuse(err, fail)
    if "reviewer" not in (entry.get("roles") or []) and not substitute_for(config, ns.node_id, ns.model):
        return trace.refuse(f"{ns.model!r} has no reviewer role and no active substitution covers {ns.node_id}", fail)
    why = rerun_problem(config["policy"], rec["data"])
    if why:
        return trace.refuse(f"{ns.file}: does not count — {why}; list what you re-ran in commands_rerun", fail)
    # The body's hash rides in the front matter, so a signature covers the notes too.
    data = {**rec["data"], "commit": gate.commit, NOTES_KEY: notes_digest(rec["body"])}
    if ns.launch_mode:   # before signing: the signature covers it
        data["launch_mode"] = ns.launch_mode
    data = stamp_review_toolkit_version(data)
    if ns.sign_key:
        if not entry.get("public_key"):
            return trace.refuse(f"--sign-key given, but the roster entry for {ns.model!r} has no public_key; "
                              "the gate could not verify the record", fail)
        try:
            data["signature"] = sign(data, Path(ns.sign_key))
        except SigningError as e:
            return trace.refuse(f"could not sign: {e}", fail)
        ok, why = verify(data, data["signature"], str(entry["public_key"]), ns.model)
        if not ok:
            return trace.refuse(f"the signature does not verify against the roster public_key for {ns.model!r} "
                                f"({why}); wrong key?", fail)
    elif config["policy"].get("signed_reviews"):
        return trace.refuse("policy.signed_reviews is on: pass --sign-key <your private key>; the roster entry "
                            f"for {ns.model!r} must carry the matching public_key", fail)
    data["family"] = entry["family"]
    dest = review_path(root, ns.node_id, ns.model)
    text = render_front_matter(data, rec["body"])
    write_review(dest, text)   # replaces a record filed as review-<model>.md, whatever the filesystem's case rules
    clear_rejected(trace.reviews, ns.model)
    archive_review(root, ns.node_id, ns.model, text)
    print(f"Wrote {dest}")
    after = evaluate_gate(root, t.node, t.commit, branch=(t.entry or {}).get("branch"))
    if after.distinct_families:
        relabel(root, after)
        if any(o.family == entry["family"] and o.model != ns.model for o in after.approvals + after.blocks):
            print(f"note: another counted review is also from family {entry['family']!r}; "
                  "it is less independent and counts once toward the distinct-family policy.")
    print(f"policy: {after.summary()}")
    return 0
