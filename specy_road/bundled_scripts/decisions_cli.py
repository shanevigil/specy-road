#!/usr/bin/env python3
"""CLI for ``specy-road decisions add|list|close`` (M11.34; preferences M11.58; standing rules M22.51).

``--kind lesson`` reads and writes project review lessons in ``constraints/review-lessons.md``
(:mod:`specy_road.review_lessons`), which ``lessons add|list``, its deprecated alias, also run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.cli_args import add_json_arg, add_model_arg
from specy_road.bundled_scripts.finish_task import TERMINAL, human_criteria
from specy_road.review_override import OPERATOR, recorder, role_refusal
from specy_road.roadmap_load import load_roadmap
from specy_road.decisions import (
    PREFERENCE,
    STANDING_RULE,
    active_preferences,
    add_entry,
    add_preference,
    close_entry,
    decisions_path,
    format_open_entry,
    format_preference,
    open_questions,
)
from specy_road.decisions_local import LOCAL, SHARED, load_merged, next_free_id
from specy_road.model_profiles import ROLES
from specy_road.review_lessons import LESSONS_REL, add_lesson, format_lesson, lessons_path, read_lessons
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _parse_option(raw: str) -> dict[str, str]:
    if "|" not in raw:
        print(f"error: --option must be label|effect, got {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    label, effect = raw.split("|", 1)
    label, effect = label.strip(), effect.strip()
    if not label or not effect:
        print(f"error: --option label and effect must be non-empty: {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    return {"label": label, "effect": effect}


def _criterion_text(root: Path, node_id: str | None, criterion: str) -> str | None:
    """The ``human:`` text of ``node_id``'s criterion ``criterion``, or ``None`` when it is not one."""
    node = next((n for n in load_roadmap(root)["nodes"] if n["id"] == node_id), None)
    return human_criteria(node).get(criterion) if node else None


def _criterion_error(root: Path, ns: argparse.Namespace) -> str | None:
    """``--criterion`` needs a human-action entry for a ``human:`` criterion of the node, at most one open in the
    merged ledger; a ledger that does not read or fails the schema refuses, since no open entry can be ruled out."""
    if ns.kind != "human-action":
        return "--criterion applies only to --kind human-action"
    if _criterion_text(root, ns.node, ns.criterion) is None:
        return f"{ns.criterion} is not a `human:` acceptance criterion of {ns.node}"
    doc, _local_ids, errs = load_merged(root)
    if errs:
        return f"{errs[0]}; fix it first: an open entry for {ns.node} {ns.criterion} cannot be ruled out"
    if any(e.get("node") == ns.node and e.get("criterion") == ns.criterion for e in open_questions(doc)):
        return f"{ns.node} {ns.criterion} already has an open entry; a person closes that one"
    return None


LESSON = "lesson"

_QUESTION_FLAGS = (("node", "NODE"), ("why", "--why"), ("option", "--option"),
                   ("recommendation", "--recommendation"),
                   ("recommendation_reason", "--recommendation-reason"), ("default", "--default"))
_QUESTION_ONLY = (("option", "--option"), ("recommendation", "--recommendation"),
                  ("recommendation_reason", "--recommendation-reason"), ("default", "--default"),
                  ("needed_by", "--needed-by"))
_PREFERENCE_ONLY = (("role", "--role"), ("model", "--model"), ("applies_to", "--applies-to"),
                    ("expires", "--expires"), ("supersedes", "--supersedes"))


_LESSON_REFUSED = _QUESTION_ONLY + _PREFERENCE_ONLY + (
    ("why", "--why"), ("id", "--id"), ("criterion", "--criterion"), ("asked", "--asked"), ("local", "--local"))


def _kind_flag_error(ns: argparse.Namespace) -> str | None:
    """Which flags this kind needs or refuses; argparse cannot say it per ``--kind``."""
    if ns.kind == PREFERENCE:
        bad = [flag for attr, flag in _QUESTION_ONLY if getattr(ns, attr)]
        return f"--kind preference does not take {', '.join(bad)}" if bad else None
    if ns.kind == STANDING_RULE:
        bad = [flag for attr, flag in _QUESTION_ONLY + _PREFERENCE_ONLY if attr != "expires" and getattr(ns, attr)]
        if bad:
            return f"--kind standing-rule does not take {', '.join(bad)}"
        return None if (ns.why or "").strip() else "--kind standing-rule needs --why: the operator's words, quoted"
    missing = [flag for attr, flag in _QUESTION_FLAGS if not getattr(ns, attr)]
    if missing:
        return f"--kind {ns.kind} needs {', '.join(missing)}"
    bad = [flag for attr, flag in _PREFERENCE_ONLY if getattr(ns, attr)]
    return f"{', '.join(bad)} apply only to --kind preference" if bad else None


def _add_preference(root: Path, ns: argparse.Namespace) -> int:
    """A preference, or a standing rule (the same write with ``kind``)."""
    try:
        entry = add_preference(
            root, summary=ns.summary, role=ns.role, models=ns.model, applies_to=ns.applies_to,
            expires=ns.expires, why=ns.why, node_id=ns.node, preference_id=ns.id,
            supersedes=ns.supersedes, asked=ns.asked, local=ns.local, kind=ns.kind,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    tail = f"; closed {ns.supersedes}" if ns.supersedes else ""
    print(f"added {entry['id']} ({ns.kind}){tail} → {decisions_path(root, ns.local)}")
    return 0


def add_lesson_entry(root: Path, *, rule: str, example: str | None, from_node: str | None) -> int:
    """Append one review lesson (``decisions add --kind lesson``, and ``lessons add``)."""
    try:
        add_lesson(root, rule=rule, example=example, from_node=from_node)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"added lesson → {lessons_path(root)}")
    return 0


def list_lessons(root: Path) -> int:
    """Print every review lesson in file order (``decisions list --kind lesson``, and ``lessons list``)."""
    path = lessons_path(root)
    try:
        entries = read_lessons(path)
    except OSError as e:
        print(f"error: could not read {LESSONS_REL.as_posix()}: {e}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"No review lessons: {LESSONS_REL.as_posix()} does not exist; "
              "`specy-road decisions add --kind lesson` creates it.")
        return 0
    if not entries:
        print(f"No review lessons in {LESSONS_REL.as_posix()}.")
        return 0
    for e in entries:
        print(format_lesson(e))
    return 0


def cmd_add(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    if err := _kind_flag_error(ns) or (ns.criterion and _criterion_error(root, ns)):
        print(f"error: {err}", file=sys.stderr)
        return 1
    # One id sequence across both ledgers: a new entry must not shadow, or be shadowed by, the other's.
    ns.id = ns.id or next_free_id(root, {PREFERENCE: "P", STANDING_RULE: "R"}.get(ns.kind, "D"))
    if ns.kind in (PREFERENCE, STANDING_RULE):
        return _add_preference(root, ns)
    options = [_parse_option(o) for o in ns.option]
    try:
        entry = add_entry(
            root,
            node_id=ns.node,
            kind=ns.kind,
            summary=ns.summary,
            why_now=ns.why,
            options=options,
            recommendation=ns.recommendation,
            recommendation_reason=ns.recommendation_reason,
            default_if_unanswered=ns.default,
            decision_id=ns.id,
            needed_by=ns.needed_by,
            asked=ns.asked,
            local=ns.local,
            criterion=ns.criterion,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"added {entry['id']} (open) → {decisions_path(root, ns.local)}")
    return 0


def cmd_add_any(ns: argparse.Namespace) -> int:
    """``decisions add``: a lesson goes to ``constraints/review-lessons.md``, any other kind to the ledger."""
    if ns.kind == LESSON:
        return _cmd_add_lesson(ns)
    if ns.example:
        print("error: --example applies only to --kind lesson", file=sys.stderr)
        return 1
    return cmd_add(ns)


def _cmd_add_lesson(ns: argparse.Namespace) -> int:
    """``decisions add --kind lesson``: ``--summary`` is the rule and ``NODE`` the leaf it escaped from."""
    bad = [flag for attr, flag in _LESSON_REFUSED if getattr(ns, attr)]
    if bad:
        print(f"error: --kind lesson does not take {', '.join(bad)}", file=sys.stderr)
        return 1
    return add_lesson_entry(resolve_repo_root(ns), rule=ns.summary, example=ns.example, from_node=ns.node)


def cmd_list_any(ns: argparse.Namespace) -> int:
    """``decisions list``: ``--kind lesson`` prints the review lessons, otherwise the ledger's open entries."""
    if ns.kind != LESSON:
        return cmd_list(ns)
    if ns.json:
        print("error: --kind lesson has no --json output", file=sys.stderr)
        return 1
    return list_lessons(resolve_repo_root(ns))


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    doc, local_ids, errs = load_merged(root)
    if errs:
        for line in errs:
            print(f"decisions.schema: {line}", file=sys.stderr)
        return 1
    prefs, questions = active_preferences(doc), open_questions(doc)
    if ns.json:
        print(json.dumps([{**e, "source": LOCAL if e["id"] in local_ids else SHARED} for e in prefs + questions],
                         indent=2))
        return 0
    if not prefs and not questions:
        print("No open decisions in roadmap/decisions.yaml or roadmap/decisions.local.yaml.")
        return 0
    for e in prefs + questions:   # each entry names its ledger: local wins over shared for the same id
        head, rest = (format_preference(e) if e in prefs else format_open_entry(e)).split("\n", 1)
        print(f"{head}  ({LOCAL if e['id'] in local_ids else SHARED})\n{rest}")
        print()
    return 0


def cmd_close(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    doc, local_ids, errs = load_merged(root)
    if errs:
        print(f"error: {errs[0]}", file=sys.stderr)
        return 1
    target = next((e for e in doc["entries"] if e.get("id") == ns.decision_id), None)
    if not target:
        print(f"error: no decision {ns.decision_id!r} in roadmap/decisions.yaml or roadmap/decisions.local.yaml",
              file=sys.stderr)
        return 1
    if target.get("criterion"):
        return _close_criterion(root, ns, target, local=ns.decision_id in local_ids)
    close_entry(root, ns.decision_id, ns.answer, local=ns.decision_id in local_ids)
    print(f"closed {ns.decision_id!r}")
    return 0


def _close_criterion(root: Path, ns: argparse.Namespace, target: dict, *, local: bool) -> int:
    """A person's decision on a ``human:`` criterion: an interactive terminal, not a launched worker, a git
    identity, and a ``y`` to the prompt; there is no non-interactive override (M22.69)."""
    if not sys.stdin.isatty():
        print(f"error: {ns.decision_id} decides {target['node']} {target['criterion']}, which only a person "
              "records: run decisions close yourself in an interactive terminal (there is no --yes), or answer "
              "it in the PM GUI's Status window", file=sys.stderr)
        return 1
    if why := role_refusal():
        print(f"error: {why}", file=sys.stderr)
        return 1
    who = recorder(root)
    if not who:
        print("error: set git user.name and user.email: the entry names who recorded the decision", file=sys.stderr)
        return 1
    text = _criterion_text(root, target["node"], target["criterion"]) or "(not a `human:` criterion of the node)"
    print(f"node: {target['node']}\n{target['criterion']}: {text}\nanswer: {ns.answer.strip()}")
    if input("Record this as your decision? [y/N] ").strip().lower() != "y":
        print(f"nothing recorded; {ns.decision_id} stays open", file=sys.stderr)
        return 1
    close_entry(root, ns.decision_id, f"{ns.answer.strip()} (recorded by {who})", local=local,
                decided_by=OPERATOR, channel=TERMINAL)
    print(f"closed {ns.decision_id!r} as your decision (channel terminal)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    dec = sub.add_parser("decisions", help="Tracked open human decisions in roadmap/decisions.yaml; "
                                           "--kind lesson: review lessons in constraints/review-lessons.md")
    dsub = dec.add_subparsers(dest="decisions_cmd", required=True)

    add = dsub.add_parser("add", help="Open a self-contained human decision, record a routing preference, or "
                                      "append a review lesson")
    add.add_argument("node", metavar="NODE", nargs="?",
                     help="Roadmap node id this entry belongs to (optional for a preference or standing rule); "
                          "for a lesson, the leaf the defect escaped from")
    add.add_argument("--kind", required=True, choices=["decision", "human-action", PREFERENCE, STANDING_RULE, LESSON])
    add.add_argument("--summary", required=True, help="Plain-words summary; for a preference or standing rule, "
                                                      "the rule; for a lesson, the defect class as a one-line "
                                                      "rule for reviewers")
    add.add_argument("--example", help="Lesson only: one line showing the defect, such as where it escaped")
    add.add_argument("--why", help="Why now and what it blocks (decision); the human's reason (preference); "
                                   "the operator's words, quoted (standing-rule, required)")
    add.add_argument("--option", action="append", metavar="LABEL|EFFECT",
                     help="Repeat for each option (label|effect); decision and human-action")
    add.add_argument("--recommendation")
    add.add_argument("--recommendation-reason")
    add.add_argument("--default", dest="default", help="Default if unanswered")
    add.add_argument("--id", dest="id", help="Entry id (default: next D#; P# for a preference, R# for a "
                                             "standing rule)")
    add.add_argument("--needed-by", help="ISO date by which an answer is needed")
    add.add_argument("--criterion", metavar="A#",
                     help="human-action only: the node's `human:` acceptance criterion this asks a person to "
                          "decide; finish-this-task counts it once a person closes the entry")
    add.add_argument("--asked", help="ISO date when asked or stated (default: today)")
    add.add_argument("--role", choices=ROLES, help="Preference: the role the rule routes")
    add_model_arg(add, append=True,
                  help="Preference: a preferred roster id; repeat, most preferred first. "
                       "Availability is not a preference: set available/paused_until in the roster")
    add.add_argument("--applies-to", action="append", metavar="LEAF_KIND",
                     help="Preference: a leaf kind it covers, such as docs or data; repeat (default: every leaf)")
    add.add_argument("--expires", help="Preference or standing rule: active through this date (YYYY-MM-DD) or "
                                       "until this datetime")
    add.add_argument("--supersedes", metavar="ID", help="Preference: close this open preference in the same write")
    add.add_argument("--local", action="store_true",
                     help="Write the gitignored roadmap/decisions.local.yaml (this clone only, no commit needed) "
                          "instead of roadmap/decisions.yaml; readers merge it over the tracked ledger, local wins")
    add_repo_root_arg(add)
    add.set_defaults(func=cmd_add_any)

    lst = dsub.add_parser("list", help="List active preferences, then open entries ordered by needed-by")
    lst.add_argument("--kind", choices=[LESSON],
                     help="lesson: print every review lesson in constraints/review-lessons.md, in file order")
    add_json_arg(lst)
    add_repo_root_arg(lst)
    lst.set_defaults(func=cmd_list_any)

    close = dsub.add_parser("close", help="Close an entry with its answer; an entry with a criterion closes only "
                                          "at a person's interactive terminal, after a y/N prompt")
    close.add_argument("decision_id", metavar="ID")
    close.add_argument("--answer", required=True,
                       help="The answer; for an entry with a criterion, shown to you with the criterion for y/N, "
                            "then recorded with your git identity")
    add_repo_root_arg(close)
    close.set_defaults(func=cmd_close)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
