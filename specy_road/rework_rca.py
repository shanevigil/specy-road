"""The accepted root-cause analysis a rework carries as its governing design (M15.6).

After an RCA was accepted, ``worker delegate --rework`` used to send only the blocking reviews, one of which
proposed the opposite design. :func:`governing_rca` finds the leaf's accepted ``RCA-<round>.md`` — valid
under :func:`review_rca.loop_state`'s checks, and, for ``defer_findings``, applied by ``review defer`` (the
M12.1 next-step rules in :mod:`review_next_step`) — when it analysed the round of at least one carried
blocking review. :func:`rca_lines` renders its design and required changes first, with the sentence that
overrules a contradicting review fix; :func:`filed` marks each review as filed before or after it.

An RCA file that cannot be read (front matter or schema) at or after the oldest carried review's round may
be the accepted one, so :func:`governing_rca` raises :class:`RcaNotCarried` rather than leave it out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from specy_road.review_deferral import marker_path
from specy_road.review_files import ReviewFile, list_rcas
from specy_road.review_rca import loop_state
from specy_road.review_target import full_sha


class RcaNotCarried(Exception):
    """An RCA that may be the accepted one cannot be rendered into the prompt."""


@dataclass(frozen=True)
class RcaDoc:
    record: ReviewFile
    commits: frozenset[str]   # the commits of the rounds it analysed (rounds 1..trigger.round)

    @property
    def name(self) -> str:
        return self.record.path.name


def _key(root: Path, commit: str) -> str:
    return full_sha(root, commit) or commit


def _file_round(path: Path) -> int | None:
    m = re.fullmatch(r"RCA-(\d+)\.md", path.name)
    return int(m.group(1)) if m else None


def governing_rca(root: Path, node_id: str, blocks: list[ReviewFile]) -> RcaDoc | None:
    """The accepted RCA newer than the oldest of ``blocks``; ``None`` when there is none (or no blocks).
    Raises :class:`RcaNotCarried` when it, or an unreadable RCA that may be it, cannot be rendered."""
    if not blocks:
        return None
    loop = loop_state(root, node_id)
    index = {c: i for i, c in enumerate((r.commit for r in loop.rounds), 1)}
    # A carried review not in the review history came after every round an RCA analysed.
    oldest = min(index.get(_key(root, str(r.data["commit"])), len(loop.rounds) + 1) for r in blocks)
    for r in list_rcas(root, node_id):
        n = _file_round(r.path)
        if not r.ok and (n is None or n >= oldest):
            raise RcaNotCarried(f"{r.path} cannot be read ({'; '.join(r.errors)}), and it may be the accepted "
                                "root-cause analysis; fix or remove it, then delegate --rework")
    accepted = [r for r in loop.rcas if r.ok and (r.data["recommended_action"]["type"] != "defer_findings"
                                                    or marker_path(root, node_id, r.path.name).exists())]
    rec = max(accepted, key=lambda r: int(r.data["trigger"]["round"]), default=None)
    if rec is None or int(rec.data["trigger"]["round"]) < oldest:
        return None
    if not str(rec.data["recommended_action"]["instructions"]).strip():
        raise RcaNotCarried(f"{rec.path} is the accepted root-cause analysis, but its "
                            "recommended_action.instructions (the design) is empty; fill it, then delegate --rework")
    done = int(rec.data["trigger"]["round"])
    return RcaDoc(rec, frozenset(rnd.commit for rnd in loop.rounds[:done]))


def filed(root: Path, doc: RcaDoc, review: ReviewFile) -> str:
    """``filed before RCA-<n>.md`` when ``review``'s commit is in a round the RCA analysed, else ``after``."""
    when = "before" if _key(root, str(review.data["commit"])) in doc.commits else "after"
    return f"filed {when} {doc.name}"


def rca_lines(doc: RcaDoc) -> list[str]:
    """The governing design: the RCA's recommended action, any proposed criterion, and its in-scope findings."""
    d = doc.record.data
    action = d["recommended_action"]
    approval = ", requires human approval" if action.get("requires_human_approval") else ""
    out = [f"### Governing design: `{doc.name}` (accepted root-cause analysis, round {d['trigger']['round']})", "",
           f"Record: `{doc.record.path}`", "",
           "This root-cause analysis is the governing design for this rework. A review's suggested fix below "
           "that contradicts it is overruled: follow this design, and take from each review only what agrees "
           "with it.", "",
           f"**Design** (`{action['type']}`{approval}):", "", str(action["instructions"]).strip(), ""]
    rewrite = d.get("criterion_rewrite")
    if rewrite:
        out += [f"**Proposed criterion** ({rewrite['acceptance_id']}): {rewrite['proposed_text']}", ""]
    must = [x["finding"] for x in (rewrite or {}).get("finding_disposition") or [] if x["label"] == "in_scope_must_fix"]
    if must:
        out += ["**Required changes** (findings it labels in scope, must fix):", "", *(f"- {f}" for f in must), ""]
    return out
