"""Tracked open human decisions in ``roadmap/decisions.yaml`` (M11.34).

The same ledger holds the human's routing preferences (``kind: preference``,
M11.58): rules stated in chat, such as which executor takes docs-only leaves,
kept where a later session, an account switch or another agent can read them.
Whether a model is available or paused is never a preference; that stays in the
roster's ``available`` / ``paused_until`` fields.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.init_project import project_template_root
from specy_road.orchestration_config import _paused_until_error
from specy_road.registry_yaml import dump_registry_text
from specy_road.text_sections import find_section

DECISIONS_REL = Path("roadmap") / "decisions.yaml"
DECISIONS_LOCAL_REL = Path("roadmap") / "decisions.local.yaml"   # this clone only (M15.22)
PREFERENCE = "preference"
_SCHEMA_NAME = "decisions.schema.json"
_DECISION_HEADINGS = {"decisions and notes", "decisions"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECISION_LINE = re.compile(
    r"^\s*(?:[-*+]\s*(?:\[[ xX]\]\s*)?)?([A-Za-z][A-Za-z0-9._-]*)\s*:\s*(\S.*)$"
)


def decisions_path(root: Path, local: bool = False) -> Path:
    return root / (DECISIONS_LOCAL_REL if local else DECISIONS_REL)


def read_decisions(path: Path, *, missing_ok: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if not missing_ok:
            raise FileNotFoundError(path)
        return {"version": 1, "entries": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def write_decisions(path: Path, doc: dict[str, Any]) -> None:
    errs = schema_errors(doc, schema_path_for_write(path.parent.parent))
    if errs:
        raise ValueError("decisions.yaml: " + "; ".join(errs))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registry_text(doc), encoding="utf-8")


def bundled_schema_path() -> Path:
    return project_template_root() / "schemas" / _SCHEMA_NAME


def schema_path_for_write(project_root: Path) -> Path:
    consumer = project_root / "schemas" / _SCHEMA_NAME
    if consumer.is_file():
        return consumer
    return bundled_schema_path()


@cache
def _validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def schema_errors(doc: dict[str, Any], schema_path: Path | None = None) -> list[str]:
    path = schema_path or bundled_schema_path()
    if not path.is_file():
        return [f"missing schema at {path}"]
    out: list[str] = []
    for err in sorted(_validator(path).iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in err.path) if err.path else "(root)"
        out.append(f"{loc}: {err.message}")
    return out


def _today_iso() -> str:
    return date.today().isoformat()


def require_iso_date(name: str, value: str) -> str:
    """YYYY-MM-DD only; calendar-invalid strings (2026-13-40) are refused too."""
    text = value.strip()
    if not _ISO_DATE.fullmatch(text):
        raise ValueError(f"{name} must be an ISO date YYYY-MM-DD, got {value!r}")
    try:
        date.fromisoformat(text)
    except ValueError as e:
        raise ValueError(f"{name} must be an ISO date YYYY-MM-DD, got {value!r}") from e
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def open_entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in doc.get("entries") or [] if isinstance(e, dict) and e.get("status") == "open"]


def open_questions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Open decision and human-action entries: what the human is asked, in needed-by order."""
    return sort_for_list([e for e in open_entries(doc) if e.get("kind") != PREFERENCE])


def preference_active(e: dict[str, Any], now: datetime | date | None = None) -> bool:
    """An open preference whose ``expires`` (a date, inclusive, or a datetime) has not passed."""
    # Same boundary rule as a roster pause, so `expires` and `paused_until` read alike.
    from specy_road.orchestrate_plan import _pause_active

    if e.get("kind") != PREFERENCE or e.get("status") != "open":
        return False
    return not e.get("expires") or _pause_active({"paused_until": e["expires"]}, now)


def active_preferences(doc: dict[str, Any], now: datetime | date | None = None) -> list[dict[str, Any]]:
    """Open, unexpired preferences, oldest first; expired ones are dropped, not closed."""
    prefs = [e for e in open_entries(doc) if preference_active(e, now)]
    return sorted(prefs, key=lambda e: ((e.get("asked") or ""), e.get("id") or ""))


def load_checked_decisions(root: Path) -> dict[str, Any] | None:
    """The tracked ledger, checked against the decisions schema.

    ``None`` when ``roadmap/decisions.yaml`` is absent. A parse error, a
    non-mapping root or schema errors raise ``ValueError`` naming that file.
    """
    path = decisions_path(root)
    if not path.is_file():
        return None
    name = DECISIONS_REL.as_posix()
    try:
        doc = read_decisions(path, missing_ok=False)
    except yaml.YAMLError as e:
        raise ValueError(f"{name}: {e}") from e
    if not isinstance(doc, dict):
        raise ValueError(f"{name}: root must be a mapping")
    errs = schema_errors(doc, schema_path_for_write(root))
    if errs:
        raise ValueError(f"{name}: " + "; ".join(errs))
    return doc


def notice_decisions_naming_no_node(
    root: Path, live_ids: set[str], now: datetime | date | None = None
) -> None:
    """One stdout notice for open questions and active preferences naming no live node.

    Entries with no ``node``, closed entries and expired preferences are omitted.
    An absent, unreadable or schema-invalid ledger prints nothing.
    """
    try:
        doc = load_checked_decisions(root)
    except ValueError:
        return
    if doc is None:
        return
    rows = []
    for entry in (*open_questions(doc), *active_preferences(doc, now)):
        node = entry.get("node")
        if isinstance(node, str) and node and node not in live_ids:
            rows.append(f"{entry['id']} [{entry['kind']}] node {node}")
    if rows:
        print(
            "roadmap: notice — roadmap/decisions.yaml names no live node:\n  "
            + "\n  ".join(rows)
        )


def plan_preferences(root: Path, now: datetime | date | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Active preferences for ``orchestrate plan``, ``roadmap/decisions.local.yaml`` merged over the tracked
    ledger; an unreadable ledger is a warning, never a plan failure."""
    from specy_road.decisions_local import load_merged

    doc, _local_ids, errs = load_merged(root)
    if errs:
        return [], f"{errs[0]}; preferences not shown; run `specy-road decisions list`"
    return active_preferences(doc, now), None


def sort_for_list(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(e: dict[str, Any]) -> tuple:
        nb = (e.get("needed_by") or "").strip()
        asked = (e.get("asked") or "").strip()
        return (0 if nb else 1, nb or "9999-12-31", asked, e.get("id") or "")

    return sorted(entries, key=key)


def next_decision_id(doc: dict[str, Any], prefix: str = "D") -> str:
    used = {e.get("id") for e in doc.get("entries") or [] if isinstance(e, dict)}
    n = 1
    while True:
        cand = f"{prefix}{n}"
        if cand not in used:
            return cand
        n += 1


def _unfenced_lines(text: str) -> list[str]:
    """Lines outside CommonMark fenced code blocks, so examples cannot close an entry.

    Reuses the fence opener/closer in ``validate_stale_commands`` (backtick and
    tilde runs, matching lengths).
    """
    from specy_road.bundled_scripts.validate_stale_commands import (
        _fence_closes,
        _fence_marker,
        _opening_is_code_span,
    )

    open_fence: tuple[str, int] | None = None
    out: list[str] = []
    for line in text.splitlines():
        if open_fence is not None:
            if _fence_closes(line, open_fence):
                open_fence = None
            continue
        marker = _fence_marker(line)
        if marker is not None and not _opening_is_code_span(line):
            open_fence = (marker[0], marker[1])
            continue
        out.append(line)
    return out


def recorded_on_sheet(sheet_text: str, decision_id: str, answer: str) -> bool:
    """True when ``id: answer`` is in the planning-sheet decision block.

    CommonMark fences are stripped from the whole sheet first, then the
    decision block is the first level-2 section whose heading normalises to
    ``decisions and notes`` or ``decisions``. A heading that exists only
    inside a fence is not that block.
    """
    unfenced = "\n".join(_unfenced_lines(sheet_text))
    block = find_section(unfenced, _DECISION_HEADINGS)
    if not block:
        return False
    want = answer.strip()
    for line in block.splitlines():
        m = _DECISION_LINE.match(line)
        if m and m.group(1) == decision_id and m.group(2).strip() == want:
            return True
    return False


def format_open_entry(e: dict[str, Any]) -> str:
    nb = e.get("needed_by")
    deadline = f"  needed-by: {nb}" if nb else ""
    opts = "; ".join(f"{o['label']} ({o['effect']})" for o in e.get("options") or [])
    return (
        f"{e['id']} [{e['kind']}] node {e['node']}{deadline}\n"
        f"  {e['summary']}\n"
        f"  why now: {e['why_now']}\n"
        f"  options: {opts}\n"
        f"  recommendation: {e['recommendation']} — {e['recommendation_reason']}\n"
        f"  default if unanswered: {e['default_if_unanswered']}"
    )


def format_preference(e: dict[str, Any]) -> str:
    scope = [f"role {e['role']}"] if e.get("role") else []
    if e.get("models"):
        scope.append("prefer " + ", ".join(e["models"]))
    if e.get("applies_to"):
        scope.append("leaf kinds " + ", ".join(e["applies_to"]))
    if e.get("expires"):
        scope.append(f"expires {e['expires']}")
    lines = [f"{e['id']} [preference] " + ("; ".join(scope) or "every role and leaf"), f"  {e['summary']}"]
    if e.get("why_now"):
        lines.append(f"  why: {e['why_now']}")
    return "\n".join(lines)


def coordinator_decision_lines() -> list[str]:
    return [
        "## Human decisions ledger",
        "",
        "At the **start of every turn**, after `specy-road worker sync`, run "
        "`specy-road decisions list`. Before asking the human anything, search "
        "`roadmap/decisions.yaml` and each relevant planning sheet's decision block "
        "(`specy-road search \"<topic>\" --kind planning`) so you do not repeat a "
        "question that is already open or answered.",
        "",
        "Ask at most **four** open questions in one turn. Each question must be "
        "self-contained (no bare ids): say what it is, why now and what it blocks, "
        "each option and its effect, your recommendation and reason, the default you "
        "will apply if unanswered, and any needed-by date. Register new ones with "
        "`specy-road decisions add`.",
        "",
        "End **every** turn that still has open decision or human-action entries with "
        "one **Decisions waiting on you** block below your status, listing **all** of "
        "them in the same self-contained shape.",
        "",
        "## Routing preferences",
        "",
        "The human's routing preferences (which executor or reviewer to use, for which "
        "leaf kinds, until when) are `kind: preference` entries in the same ledger; "
        "`specy-road decisions list` shows the active ones first. Read them at the "
        "**start of every session** and again **before each** `worker delegate` or "
        "reviewer launch, and apply them: `orchestrate plan` lists them but does not "
        "apply them itself.",
        "",
        "Whenever the human states a preference in chat, record it at once with "
        "`specy-road decisions add --kind preference --summary \"<rule in plain words>\"` "
        "plus `--role`, `--model <roster id>` (repeat, most preferred first), "
        "`--applies-to <leaf kind>` and `--expires` when they apply. When the human "
        "changes one, record the new rule with `--supersedes <id>`; when they drop it, "
        "`specy-road decisions close <id> --answer \"<why>\"`. Whether a model is "
        "available or paused is not a preference: set `available` / `paused_until` in "
        "the roster (`roadmap/orchestration.local.yaml` needs no push).",
        "",
    ]


def add_entry(
    root: Path,
    *,
    node_id: str,
    kind: str,
    summary: str,
    why_now: str,
    options: list[dict[str, str]],
    recommendation: str,
    recommendation_reason: str,
    default_if_unanswered: str,
    decision_id: str | None = None,
    needed_by: str | None = None,
    asked: str | None = None,
    local: bool = False,
) -> dict[str, Any]:
    path = decisions_path(root, local)
    doc = read_decisions(path)
    entry_id = decision_id or next_decision_id(doc)
    for e in doc.get("entries") or []:
        if isinstance(e, dict) and e.get("id") == entry_id:
            raise ValueError(f"decision id {entry_id!r} already exists")
    entry: dict[str, Any] = {
        "id": entry_id,
        "node": node_id,
        "kind": kind,
        "summary": summary.strip(),
        "why_now": why_now.strip(),
        "options": options,
        "recommendation": recommendation.strip(),
        "recommendation_reason": recommendation_reason.strip(),
        "default_if_unanswered": default_if_unanswered.strip(),
        "asked": require_iso_date("asked", asked) if asked else _today_iso(),
        "status": "open",
    }
    if needed_by:
        entry["needed_by"] = require_iso_date("needed_by", needed_by)
    doc.setdefault("entries", []).append(entry)
    write_decisions(path, doc)
    return entry


def add_preference(
    root: Path,
    *,
    summary: str,
    role: str | None = None,
    models: list[str] | None = None,
    applies_to: list[str] | None = None,
    expires: str | None = None,
    why: str | None = None,
    node_id: str | None = None,
    preference_id: str | None = None,
    supersedes: str | None = None,
    asked: str | None = None,
    local: bool = False,
) -> dict[str, Any]:
    """Record a routing preference; ``supersedes`` closes an open preference in the same write."""
    path = decisions_path(root, local)
    doc = read_decisions(path)
    entries = doc.setdefault("entries", [])
    entry_id = preference_id or next_decision_id(doc, "P")
    if any(isinstance(e, dict) and e.get("id") == entry_id for e in entries):
        raise ValueError(f"decision id {entry_id!r} already exists")
    if expires and (err := _paused_until_error("expires", expires.strip())):
        raise ValueError(err)
    entry: dict[str, Any] = {"id": entry_id, "kind": PREFERENCE, "summary": summary.strip()}
    for key, val in (("node", node_id), ("role", role), ("why_now", (why or "").strip()),
                     ("models", models), ("applies_to", applies_to), ("expires", (expires or "").strip())):
        if val:
            entry[key] = val
    entry["asked"] = require_iso_date("asked", asked) if asked else _today_iso()
    entry["status"] = "open"
    if supersedes:
        old = next((e for e in entries if isinstance(e, dict) and e.get("id") == supersedes), None)
        if not old or old.get("kind") != PREFERENCE or old.get("status") != "open":
            raise ValueError(f"--supersedes {supersedes!r} is not an open preference")
        old.update(status="closed", answer=f"superseded by {entry_id}", closed=_now_iso())
    entries.append(entry)
    write_decisions(path, doc)
    return entry


def close_entry(root: Path, decision_id: str, answer: str, *, sheet_text: str | None,
                ledger_only: bool = False, local: bool = False) -> dict[str, Any]:
    """Close an open entry. A preference (``sheet_text`` None) needs no planning-sheet record:
    it belongs to the project's sessions, not to one leaf. ``ledger_only`` closes a decision without one
    for a caller that keeps its own audit trail (``review defer``: the RCA record and its deferral marker)."""
    if sheet_text is not None and not recorded_on_sheet(sheet_text, decision_id, answer):
        print(
            f"error: planning sheet decision block has no line `{decision_id}: {answer.strip()}` "
            "(optional list marker or checkbox in front is fine; other sections and fenced "
            "examples do not count). Record the answer under `## Decisions and notes`, "
            "commit it, then run close again.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    path = decisions_path(root, local)
    doc = read_decisions(path)
    entries = doc.get("entries") or []
    for e in entries:
        if isinstance(e, dict) and e.get("id") == decision_id:
            if e.get("status") != "open":
                print(f"error: decision {decision_id!r} is not open", file=sys.stderr)
                raise SystemExit(1)
            if sheet_text is None and e.get("kind") != PREFERENCE and not ledger_only:
                print(f"error: decision {decision_id!r} closes only with its planning-sheet record",
                      file=sys.stderr)
                raise SystemExit(1)
            e["status"] = "closed"
            e["answer"] = answer.strip()
            e["closed"] = _now_iso()
            write_decisions(path, doc)
            return e
    print(f"error: no decision {decision_id!r} in {path.relative_to(root).as_posix()}", file=sys.stderr)
    raise SystemExit(1)
