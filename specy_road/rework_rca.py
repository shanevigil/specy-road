"""The accepted root-cause analysis a rework carries as its governing design (M15.6).

After an RCA was accepted, ``worker delegate --rework`` used to send only the blocking reviews, one of which
proposed the opposite design. :func:`governing_rca` finds the leaf's accepted ``RCA-<round>.md`` — valid
under :func:`review_rca.loop_state`'s checks, and, for ``defer_findings``, with its marker in effect
(:func:`review_deferral.rca_deferral`, the rule the gate and :mod:`review_next_step` apply) — when it
was filed after at least one carried blocking review. :func:`rca_lines` renders its design and required changes first, with the sentence that overrules a
contradicting review fix; :func:`filed` marks each review as filed before or after it.

"Filed" is filing provenance: a file's modification time, which ``review record`` (``REVIEW-*.md``) and the
analyst (``RCA-*.md``) set when they write it. Which commit a review names says nothing about when it was filed.

:func:`check_inputs` reads every record file the rework section loads as bytes and decodes it before any
loader does; with blocking reviews to carry, an RCA file whose front matter or schema is broken may be the
accepted one. Both raise :class:`RcaNotCarried`, naming the file, rather than crash or leave the RCA out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from specy_road.review_deferral import rca_deferral
from specy_road.review_files import (
    HISTORY_DIRNAME,
    RCA_PREFIX,
    READY_PREFIX,
    REVIEW_PREFIX,
    ReviewFile,
    list_rcas,
    reviews_dir,
)
from specy_road.review_rca import loop_state


class RcaNotCarried(Exception):
    """A record the rework section needs cannot be read, or the accepted RCA cannot be rendered into it."""


@dataclass(frozen=True)
class RcaDoc:
    record: ReviewFile

    @property
    def name(self) -> str:
        return self.record.path.name


def filed_at(r: ReviewFile) -> int:
    """When ``r`` was filed: its file's modification time in nanoseconds."""
    return (r.on_disk or r.path).stat().st_mtime_ns


def _record_files(root: Path, node_id: str) -> list[Path]:
    """``RCA-*.md``, ``READY-*.md`` (``loop_state`` reads them for the RCA's parties), ``REVIEW-*.md`` (prefix
    in any case, as :func:`review_files.list_reviews` matches it) and ``history/*.md``: every record file the
    rework section loads. ``DEFERRAL-*.yaml`` is left out: its loader already reports undecodable bytes."""
    d = reviews_dir(root, node_id)
    if not d.is_dir():
        return []
    top = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md"
           and (p.name.startswith((RCA_PREFIX, READY_PREFIX)) or p.name.lower().startswith(REVIEW_PREFIX.lower()))]
    h = d / HISTORY_DIRNAME
    return sorted(top) + (sorted(h.glob("*.md")) if h.is_dir() else [])


def check_inputs(root: Path, node_id: str) -> None:
    """Raise :class:`RcaNotCarried` naming the first record file that cannot be read as UTF-8: the loaders read
    text and would raise ``UnicodeDecodeError`` without the path."""
    for p in _record_files(root, node_id):
        try:
            p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise RcaNotCarried(f"{p} cannot be read as UTF-8 ({type(e).__name__}: {e}); re-save it as UTF-8 "
                                "or remove it, then delegate --rework") from None


def governing_rca(root: Path, node_id: str, blocks: list[ReviewFile]) -> RcaDoc | None:
    """The accepted RCA filed after the oldest of ``blocks``; ``None`` when there is none (or no blocks).
    Raises :class:`RcaNotCarried` when a record file cannot be read as UTF-8 (:func:`check_inputs`), an RCA
    file's front matter or schema is broken (it may be the accepted one), or the accepted RCA has no design."""
    check_inputs(root, node_id)
    if not blocks:
        return None
    for r in list_rcas(root, node_id):
        if not r.ok:
            raise RcaNotCarried(f"{r.path} cannot be read ({'; '.join(r.errors)}), and it may be the accepted "
                                "root-cause analysis; fix or remove it, then delegate --rework")
    loop = loop_state(root, node_id)
    oldest = min(filed_at(r) for r in blocks)
    accepted = [r for r in loop.rcas if r.ok and (r.data["recommended_action"]["type"] != "defer_findings"
                                                    or rca_deferral(root, node_id, r.path.name) == [])]
    rec = max(accepted, key=filed_at, default=None)
    if rec is None or filed_at(rec) <= oldest:
        return None
    if not str(rec.data["recommended_action"]["instructions"]).strip():
        raise RcaNotCarried(f"{rec.path} is the accepted root-cause analysis, but its "
                            "recommended_action.instructions (the design) is empty; fill it, then delegate --rework")
    return RcaDoc(rec)


def filed(doc: RcaDoc, review: ReviewFile) -> str:
    """``filed before RCA-<n>.md`` when ``review`` was filed before the RCA was, else ``filed after``."""
    return f"filed {'before' if filed_at(review) < filed_at(doc.record) else 'after'} {doc.name}"


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
