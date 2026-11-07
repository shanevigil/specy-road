"""Deferring new-input-class findings to a follow-up leaf: the one qualification rule and the marker file.

An RCA record of type ``defer_findings`` proposes moving blocking findings whose **input class** is new to a
follow-up leaf. :func:`qualify_deferral` holds every rule that decides whether a set of items may be deferred,
and is the only place they live: ``specy-road review defer`` calls it before writing anything, and the gate
(:func:`apply_deferrals`) calls it again on every applied marker each time it evaluates, from the same
evidence (:func:`deferral_evidence`). A ``DEFERRAL-<round>.yaml`` marker is a cache of what a human applied,
never an authority: it is shape-checked where it is read (:func:`load_markers`), a malformed one resolves
nothing and is reported, and a block counts as resolved only while the marker is in effect
(:func:`deferral_in_effect`): bound to the valid RCA it names and to the closed decision ``review defer``
recorded for it in ``roadmap/decisions.yaml``, with items that still qualify. The fix-round budget's next step is
:mod:`specy_road.review_next_step`. Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.decisions import decisions_path, read_decisions
from specy_road.review_files import RCA_PREFIX, ReviewFile, reviews_dir
from specy_road.review_target import same_commit

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult
    from specy_road.review_rca import Round

DEFERRAL_PREFIX = "DEFERRAL-"
CATEGORIES = ("correctness", "regression", "boundary", "test_integrity")
_TEXT = {"type": "string", "minLength": 1}
#: The marker's shape, checked where the file is read; anything else resolves nothing.
MARKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["node_id", "rca", "round", "decision", "deferred"],
    "properties": {
        "node_id": _TEXT, "rca": _TEXT, "decision": _TEXT,
        "round": {"type": "integer", "minimum": 1},
        "deferred": {"type": "array", "minItems": 1, "items": {
            "type": "object",
            "required": ["reviewer", "commit", "finding", "category", "acceptance_id", "input_class"],
            "properties": {
                "reviewer": _TEXT, "finding": _TEXT, "input_class": _TEXT,
                "commit": {"type": "string", "pattern": "^[0-9a-f]{7,40}$"},
                "category": {"enum": list(CATEGORIES)},
                "acceptance_id": {"type": "string", "pattern": "^A[1-9][0-9]*$"},
                "round": {"type": "integer", "minimum": 1},
            },
        }},
    },
}


def normalise_input_class(text: str) -> str:
    """Two input classes match when equal after lower-casing and collapsing whitespace (no fuzzy match)."""
    return " ".join(str(text).lower().split())


def round_of(rounds: list[Round], commit: str) -> int | None:
    """The 0-based index of the round whose commit ``commit`` names (short or full SHA), else ``None``."""
    commit = str(commit)
    return next((i for i, rnd in enumerate(rounds)
                 if rnd.commit.startswith(commit) or commit.startswith(rnd.commit)), None)


@dataclass
class Marker:
    name: str
    data: dict[str, Any]

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.data["deferred"]


@dataclass
class Evidence:
    """What :func:`qualify_deferral` judges items against: the leaf's review rounds, its valid RCA records and
    applied markers, the record the items come from (``source``, never its own evidence) and the round it
    covers."""
    rounds: list[Round]
    rcas: list[ReviewFile]
    markers: list[Marker]
    source: str
    covers: int
    problems: list[str] = field(default_factory=list)   # malformed markers, reported by the caller


def deferral_evidence(repo_root: Path, node_id: str, source: str, covers: int) -> Evidence:
    """The one way both callers build :class:`Evidence`, from :func:`specy_road.review_rca.loop_state`."""
    from specy_road.review_rca import loop_state   # review_rca imports this module

    loop = loop_state(repo_root, node_id)
    markers, bad = load_markers(repo_root, node_id)
    return Evidence(loop.rounds, [r for r in loop.rcas if r.ok], markers, source, covers, bad)


def _earlier_classes(ev: Evidence, before: int) -> list[tuple[str, str]]:
    """``(file, input class)`` named before round ``before`` (1-based): RCA records whose trigger round is
    earlier, and applied deferrals of findings from earlier rounds; the source record and its marker excluded."""
    named = [(r.path.name, x.get("input_class")) for r in ev.rcas
             if r.path.name != ev.source and int(r.data["trigger"]["round"]) < before
             for x in (r.data.get("deferred_findings") or [])
             + ((r.data.get("criterion_rewrite") or {}).get("finding_disposition") or [])]
    for m in ev.markers:
        if m.data["rca"] != ev.source:
            named += [(m.name, x["input_class"]) for x in m.items
                      if (i := round_of(ev.rounds, x["commit"])) is not None and i + 1 < before]
    return named


def _passed_before(rounds: list[Round], idx: int) -> dict[str, int]:
    """Acceptance id -> the first round before ``idx`` (1-based) where a record marked it ``pass``."""
    out: dict[str, int] = {}
    for i, rnd in enumerate(rounds[:idx], 1):
        for r in rnd.records:
            for a, v in (r.data.get("acceptance") or {}).items():
                if v == "pass":
                    out.setdefault(a, i)
    return out


def _binds(item_finding: str, original: str) -> bool:
    """An item cites an original finding by its text, optionally after a ``<round>/<reviewer>: `` prefix."""
    cited, text = " ".join(str(item_finding).split()), " ".join(str(original).split())
    return bool(text) and (cited == text or cited.endswith(": " + text))


def qualify_deferral(items: list[dict[str, Any]], ev: Evidence) -> list[str]:
    """Why ``items`` (one record's ``deferred_findings``, or one marker's ``deferred``) may not be deferred;
    empty when they may. Every deferral rule lives here:

    * **round** — an item's round is its blocking commit's round, which must hold a blocking record from its
      reviewer and be no later than the round the source record covers;
    * **new input class** — its class (normalised) matches none named before its own round;
    * **binding** — per block (reviewer and round), each item binds one to one to a finding of that record
      with the same category and text, and every finding is bound;
    * **coverage** — every acceptance id the block fails is named by an item;
    * **protected criteria** — no correctness item names an id an earlier round passed; and since a record
      does not tie findings to criteria, a block with a correctness finding that fails such an id never is.
    """
    out: list[str] = []
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for x in items:
        who = f"{x['reviewer']} @ {str(x['commit'])[:12]}"
        idx = round_of(ev.rounds, x["commit"])
        if idx is None or not any(r.data["model"] == x["reviewer"] and r.data["verdict"] == "block"
                                  for r in ev.rounds[idx].records):
            out.append(f"{who}: no blocking record from {x['reviewer']} at that commit in the review history")
            continue
        if idx + 1 > ev.covers:
            out.append(f"{who}: that commit is round {idx + 1}, later than round {ev.covers} the record covers")
            continue
        cls = normalise_input_class(x["input_class"])
        hit = next((n for n, c in _earlier_classes(ev, idx + 1) if c and normalise_input_class(c) == cls), None)
        if hit:
            out.append(f"{who}: input class {x['input_class']!r} was already named in {hit}; it is not new")
        groups.setdefault((x["reviewer"], idx), []).append(x)
    for (reviewer, idx), group in groups.items():
        out += _block_problems(ev.rounds, idx, reviewer, group)
    return out


def _block_problems(rounds: list[Round], idx: int, reviewer: str, items: list[dict[str, Any]]) -> list[str]:
    """The binding, coverage and protected-criteria rules for one block; only :func:`qualify_deferral` calls it."""
    rec = next(r.data for r in rounds[idx].records if r.data["model"] == reviewer)
    who = f"{reviewer} @ round {idx + 1}"
    free = [(cat, text) for cat, texts in (rec.get("findings") or {}).items() for text in texts or []]
    out = []
    for x in items:
        hit = next((o for o in free if o[0] == x["category"] and _binds(x["finding"], o[1])), None)
        if hit is None:
            out.append(f"{who}: {x['finding']!r} is no unlisted {x['category']} finding of that record")
        else:
            free.remove(hit)
    out += [f"{who}: {cat} finding {text!r} is not deferred" for cat, text in free]
    failed = sorted(a for a, v in (rec.get("acceptance") or {}).items() if v == "fail")
    out += [f"{who}: {a} fails and no item names it" for a in failed if a not in {x["acceptance_id"] for x in items}]
    passed = _passed_before(rounds, idx)
    out += [f"{who}: a correctness finding on {x['acceptance_id']}, which round {passed[x['acceptance_id']]} "
            "marked pass" for x in items if x["category"] == "correctness" and x["acceptance_id"] in passed]
    if (rec.get("findings") or {}).get("correctness") and (prot := [a for a in failed if a in passed]):
        out.append(f"{who}: the block has a correctness finding and fails {', '.join(prot)}, which round "
                   f"{passed[prot[0]]} marked pass; the record does not tie findings to criteria, so it is "
                   "never deferred")
    return out


def marker_path(repo_root: Path, node_id: str, rca_name: str) -> Path:
    """``DEFERRAL-<round>.yaml`` beside ``RCA-<round>.md`` (gitignored, like the records it qualifies)."""
    return reviews_dir(repo_root, node_id) / f"{DEFERRAL_PREFIX}{Path(rca_name).stem.removeprefix(RCA_PREFIX)}.yaml"


@cache
def _marker_validator() -> Draft202012Validator:
    return Draft202012Validator(MARKER_SCHEMA)


def load_markers(repo_root: Path, node_id: str) -> tuple[list[Marker], list[str]]:
    """``(valid markers, one problem line per malformed one)``; never raises on a marker's content."""
    d = reviews_dir(repo_root, node_id)
    good, bad = [], []
    for p in sorted(d.glob(f"{DEFERRAL_PREFIX}*.yaml")) if d.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            bad.append(f"{p.name}: unreadable deferral marker, resolves nothing — {type(e).__name__}")
            continue
        errs = sorted(_marker_validator().iter_errors(data), key=lambda e: list(e.path))
        if not errs and data["node_id"] != node_id:
            bad.append(f"{p.name}: deferral marker for {data['node_id']!r}, not {node_id!r}; resolves nothing")
        elif errs:
            loc = "/".join(str(x) for x in errs[0].path) or "(root)"
            bad.append(f"{p.name}: malformed deferral marker, resolves nothing — {loc}: {errs[0].message}")
        else:
            good.append(Marker(p.name, data))
    return good, bad


def write_marker(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def answer_item(x: dict[str, Any]) -> str:
    """How ``review defer`` names one deferred item in its decision's answer (``commit`` already full), and
    what :func:`deferral_in_effect` looks for there."""
    return (f"{x['finding']} (reviewer {x['reviewer']!r}, commit {x['commit']}, {x['category']} on "
            f"{x['acceptance_id']}, input class {x['input_class']!r})")


_ITEM_KEYS = ("reviewer", "finding", "category", "acceptance_id", "input_class")


def _items_match(repo_root: Path, ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> bool:
    """One to one: equal on :data:`_ITEM_KEYS`, and commits that name the same commit."""
    free = list(theirs)
    for x in ours:
        hit = next((y for y in free if all(x[k] == y.get(k) for k in _ITEM_KEYS)
                    and same_commit(repo_root, str(x["commit"]), str(y.get("commit")))), None)
        if hit is None:
            return False
        free.remove(hit)
    return not free


def _decision_problems(repo_root: Path, node_id: str, m: Marker) -> list[str]:
    """Why the decision ``m`` names is not the closed one ``review defer`` recorded for this deferral."""
    did, rca = m.data["decision"], m.data["rca"]
    try:
        doc = read_decisions(decisions_path(repo_root))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return [f"decision {did}: the ledger cannot be read"]
    entries = doc.get("entries") if isinstance(doc, dict) else None
    e = next((e for e in entries or [] if isinstance(e, dict) and e.get("id") == did), None)
    if e is None or e.get("status") != "closed" or e.get("node") != node_id or e.get("kind") != "decision":
        return [f"decision {did} is no closed decision of {node_id}"]
    answer = str(e.get("answer") or "")
    if (not str(e.get("why_now") or "").startswith(f"{rca} recommends defer_findings")
            or not answer.startswith("Deferred by ") or f"from {rca}:" not in answer):
        return [f"decision {did} was not recorded by `review defer` for {rca}"]
    return [f"decision {did} does not name {answer_item(x)}" for x in m.items if answer_item(x) not in answer]


def deferral_in_effect(repo_root: Path, node_id: str, m: Marker) -> list[str]:
    """Why the shape-valid marker ``m`` (:func:`load_markers`) is not in effect; empty when it is. The only
    place that decides it: the RCA it names is valid, recommends ``defer_findings`` at the marker's round and
    defers exactly the marker's items; its decision is the closed one ``review defer`` recorded for those items
    (:func:`answer_item`); and :func:`qualify_deferral` accepts the items now."""
    ev = deferral_evidence(repo_root, node_id, m.data["rca"], m.data["round"])
    ev.markers = [o for o in ev.markers if o.name != m.name]
    rca = next((r for r in ev.rcas if r.path.name == m.data["rca"]), None)
    if rca is None:
        out = [f"{m.data['rca']} is no valid RCA record of {node_id}"]
    elif (rca.data["recommended_action"]["type"] != "defer_findings"
          or int(rca.data["trigger"]["round"]) != m.data["round"]):
        out = [f"{rca.path.name} is no defer_findings record of round {m.data['round']}"]
    elif not _items_match(repo_root, m.items, rca.data.get("deferred_findings") or []):
        out = [f"its items are not {rca.path.name}'s deferred_findings"]
    else:
        out = _decision_problems(repo_root, node_id, m) or qualify_deferral(m.items, ev)
    return [f"{m.name}: {p}" for p in out]


def rca_deferral(repo_root: Path, node_id: str, rca_name: str) -> list[str] | None:
    """The marker beside ``rca_name``: ``None`` when there is none, ``[]`` when it is in effect for that
    record (:func:`deferral_in_effect`), else why it is not."""
    path = marker_path(repo_root, node_id, rca_name)
    if not path.exists():
        return None
    good, bad = load_markers(repo_root, node_id)
    m = next((m for m in good if m.name == path.name), None)
    if m is None:
        return [b for b in bad if b.startswith(path.name + ":")] or [f"{path.name}: unreadable deferral marker"]
    if m.data["rca"] != Path(rca_name).name:
        return [f"{path.name}: names {m.data['rca']}, not {Path(rca_name).name}"]
    return deferral_in_effect(repo_root, node_id, m)


def apply_deferrals(repo_root: Path, result: GateResult) -> None:
    """Move a counted block to ``ineligible`` when a valid marker names its reviewer and commit and is in
    effect (:func:`deferral_in_effect`). Without a marker naming the block, neither the ledger nor the history
    is read."""
    markers = load_markers(repo_root, result.node_id)[0] if result.blocks else []
    verdicts: dict[str, bool] = {}   # marker name -> it is in effect
    for b in list(result.blocks):
        naming = [m for m in markers if any(x["reviewer"] == b.model and same_commit(
            repo_root, x["commit"], str(b.review.data["commit"])) for x in m.items)]
        for m in naming:
            if m.name not in verdicts:
                verdicts[m.name] = not deferral_in_effect(repo_root, result.node_id, m)
        ok = [m for m in naming if verdicts[m.name]]
        if ok:
            result.blocks.remove(b)
            result.ineligible.append((b.review, "deferred by " + ", ".join(m.data["decision"] for m in ok)))
