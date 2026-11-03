"""Tracked open human decisions in ``roadmap/decisions.yaml`` (M11.34)."""

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
from specy_road.registry_yaml import dump_registry_text
from specy_road.text_sections import find_section

DECISIONS_REL = Path("roadmap") / "decisions.yaml"
_SCHEMA_NAME = "decisions.schema.json"
_DECISION_HEADINGS = {"decisions and notes", "decisions"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECISION_LINE = re.compile(
    r"^\s*(?:[-*+]\s*(?:\[[ xX]\]\s*)?)?([A-Za-z][A-Za-z0-9._-]*)\s*:\s*(\S.*)$"
)


def decisions_path(root: Path) -> Path:
    return root / DECISIONS_REL


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


def sort_for_list(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(e: dict[str, Any]) -> tuple:
        nb = (e.get("needed_by") or "").strip()
        asked = (e.get("asked") or "").strip()
        return (0 if nb else 1, nb or "9999-12-31", asked, e.get("id") or "")

    return sorted(entries, key=key)


def next_decision_id(doc: dict[str, Any]) -> str:
    used = {e.get("id") for e in doc.get("entries") or [] if isinstance(e, dict)}
    n = 1
    while True:
        cand = f"D{n}"
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
        "End **every** turn that still has open ledger entries with one "
        "**Decisions waiting on you** block below your status, listing **all** open "
        "entries in the same self-contained shape.",
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
) -> dict[str, Any]:
    path = decisions_path(root)
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


def close_entry(root: Path, decision_id: str, answer: str, *, sheet_text: str) -> dict[str, Any]:
    if not recorded_on_sheet(sheet_text, decision_id, answer):
        print(
            f"error: planning sheet decision block has no line `{decision_id}: {answer.strip()}` "
            "(optional list marker or checkbox in front is fine; other sections and fenced "
            "examples do not count). Record the answer under `## Decisions and notes`, "
            "commit it, then run close again.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    path = decisions_path(root)
    doc = read_decisions(path)
    entries = doc.get("entries") or []
    for e in entries:
        if isinstance(e, dict) and e.get("id") == decision_id:
            if e.get("status") != "open":
                print(f"error: decision {decision_id!r} is not open", file=sys.stderr)
                raise SystemExit(1)
            e["status"] = "closed"
            e["answer"] = answer.strip()
            e["closed"] = _now_iso()
            write_decisions(path, doc)
            return e
    print(f"error: no decision {decision_id!r} in roadmap/decisions.yaml", file=sys.stderr)
    raise SystemExit(1)
