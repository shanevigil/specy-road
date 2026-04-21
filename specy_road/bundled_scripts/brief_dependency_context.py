"""Resolve effective dependencies and extract their planning Intent for the brief.

Used by :mod:`generate_brief` to inline each upstream dependency's
``## Intent`` block into the work-packet brief. Goal: stop forcing PMs to
paraphrase upstream work inside this task's planning sheet — the brief
hands the coding agent the dependency's own intent prose verbatim.

Public surface:

* :func:`effective_dep_nodes` — explicit + ancestor-inherited deps for one node.
* :func:`extract_intent_block` — pull the canonical ``## Intent`` (or the gate
  equivalent ``## Why this gate exists``) from a planning sheet body.
* :func:`render_dependency_context_section` — full markdown block ready to drop
  into the brief.

Design notes (intent-only by default):
- We extract **only the first canonical context-bearing section** per dep
  (``## Intent`` for non-gate, ``## Why this gate exists`` for gate). Skipping
  Approach / Criteria-to-clear keeps the brief compact and avoids duplicating
  ancestor planning content already inlined elsewhere in the brief.
- Heading match is case-insensitive, tolerates trailing whitespace and a
  trailing colon (``## intent:`` etc.).
- Deterministic ordering: deps are sorted by display id so the brief output is
  byte-stable across runs and machines.
- Graceful fallbacks for deps without ``planning_dir`` and for sheets that
  exist but do not yet declare an Intent block.
"""

from __future__ import annotations

import re
from pathlib import Path

from planning_artifacts import normalize_planning_dir, resolve_planning_path, split_frontmatter
from planning_sheet_bootstrap import feature_sheet_level2_titles, gate_sheet_level2_titles
from roadmap_layout import effective_dependency_keys
from roadmap_node_keys import build_key_to_node


# ---------------------------------------------------------------------------
# Canonical heading sets (intent-only)
# ---------------------------------------------------------------------------


def _intent_titles_for(node_type: str | None) -> tuple[str, ...]:
    """Return the canonical level-2 titles to extract for a dep of ``node_type``.

    Intent-only by default: feature sheets contribute ``## Intent``; gate
    sheets contribute ``## Why this gate exists``. Other titles are reserved
    for a future opt-in.
    """
    if str(node_type or "").strip().lower() == "gate":
        gate = gate_sheet_level2_titles()
        return (gate[0],) if gate else ("Why this gate exists",)
    feat = feature_sheet_level2_titles()
    return (feat[0],) if feat else ("Intent",)


# ---------------------------------------------------------------------------
# Heading parser
# ---------------------------------------------------------------------------


_LEVEL2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*:?\s*$")


def _normalize_heading(raw: str) -> str:
    """Lowercase + collapse internal whitespace; strip trailing colon."""
    s = " ".join(raw.strip().lower().split())
    if s.endswith(":"):
        s = s[:-1].rstrip()
    return s


def extract_intent_block(planning_text: str, node_type: str | None) -> str | None:
    """Return the body of the dep's canonical Intent section, or ``None``.

    The body is everything between the matched ``## Heading`` line and the
    next ``## …`` heading (or end of file), with leading/trailing blank
    lines trimmed. If multiple matching headings exist, the first wins.
    """
    if not planning_text:
        return None
    _frontmatter, body = split_frontmatter(planning_text)
    wanted = {_normalize_heading(t) for t in _intent_titles_for(node_type)}
    if not wanted:
        return None

    lines = body.splitlines()
    capture: list[str] | None = None
    for line in lines:
        m = _LEVEL2_RE.match(line)
        if m:
            heading_norm = _normalize_heading(m.group("title"))
            if capture is not None:
                # We were capturing — a new ## heading ends the block.
                break
            if heading_norm in wanted:
                capture = []
            continue
        if capture is not None:
            capture.append(line)
    if capture is None:
        return None
    # Trim leading + trailing blanks while preserving inner structure.
    while capture and not capture[0].strip():
        capture.pop(0)
    while capture and not capture[-1].strip():
        capture.pop()
    return "\n".join(capture) if capture else None


# ---------------------------------------------------------------------------
# Effective dep resolution
# ---------------------------------------------------------------------------


def effective_dep_nodes(
    node: dict,
    by_id: dict[str, dict],
) -> list[dict]:
    """Return the list of nodes this ``node`` effectively depends on.

    Effective = explicit ``dependencies`` on this node plus every dependency
    inherited from any ancestor. Mirrors
    :func:`roadmap_layout.effective_dependency_keys`. Sorted deterministically
    by display id.
    """
    nk = node.get("node_key")
    if not isinstance(nk, str) or not nk:
        return []
    nodes_list = list(by_id.values())
    eff_map = effective_dependency_keys(nodes_list)
    keys = eff_map.get(nk) or set()
    if not keys:
        return []
    by_key = build_key_to_node(nodes_list)
    out: list[dict] = []
    for k in keys:
        dep = by_key.get(k)
        if dep is not None:
            out.append(dep)
    out.sort(key=lambda d: str(d.get("id") or ""))
    return out


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _read_text_safely(path: Path) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    try:
        return path.read_text(encoding="utf-8"), True
    except (OSError, UnicodeDecodeError):
        return "", False


def _fallback_snippet(text: str, max_lines: int = 8) -> str:
    """First N non-blank, non-heading lines (used when ## Intent is missing)."""
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        out.append(raw.rstrip())
        if len(out) >= max_lines:
            break
    return "\n".join(out)


def _render_one_dep(repo_root: Path, dep: dict) -> list[str]:
    """Markdown lines for a single dep's sub-section."""
    nid = dep.get("id") or "(unknown id)"
    title = dep.get("title") or "(no title)"
    out = [f"### `{nid}` — {title}", ""]
    pd_raw = dep.get("planning_dir")
    if not isinstance(pd_raw, str) or not pd_raw.strip():
        out.append(
            "_(no planning sheet — intent unavailable; verify by codebase scan or ask the PM.)_"
        )
        out.append("")
        return out
    try:
        norm = normalize_planning_dir(pd_raw.strip())
        sheet = resolve_planning_path(repo_root, norm)
    except ValueError as e:
        out.append(f"_(invalid planning_dir on dep: {e})_")
        out.append("")
        return out
    text, ok = _read_text_safely(sheet)
    rel = sheet.relative_to(repo_root) if sheet.is_absolute() else sheet
    if not ok:
        out.append(f"_(planning file not present on disk: `{rel}`)_")
        out.append("")
        return out
    intent = extract_intent_block(text, dep.get("type"))
    if intent:
        out.append("**Intent (from this dependency's planning sheet):**")
        out.append("")
        out.append(intent.rstrip())
        out.append("")
        return out
    snippet = _fallback_snippet(text)
    if snippet:
        out.append(
            f"_(planning sheet does not yet declare a canonical Intent section — "
            f"see `{rel}`; first lines:)_"
        )
        out.append("")
        out.append(snippet)
        out.append("")
        return out
    out.append(f"_(planning sheet `{rel}` is empty.)_")
    out.append("")
    return out


def render_dependency_context_section(
    active_node: dict,
    by_id: dict[str, dict],
    repo_root: Path,
) -> list[str]:
    """Build the new ``## 6. Dependency context`` brief section.

    Always emits the section header so downstream tooling (and the LLM-review
    prompt's instruction to "scan ## 6") sees a stable landmark. Body is a
    short note when there are no effective deps.
    """
    out = [
        "## 6. Dependency context (intent of upstream work)",
        "",
        (
            "_**Effective** dependencies below — this node's explicit "
            "`dependencies` plus every dependency inherited from an ancestor "
            "(same set the do-next-available-task picker uses). Each is "
            "**part of the brief on purpose** — do not ask the PM to repeat "
            "any of this prose inside this task's planning sheet. If "
            "something here is unclear or insufficient for this specific "
            "task, add a one-line clarification under `## Approach` (or "
            "`## Decisions and notes` for gates) citing the dep by display "
            "id._"
        ),
        "",
    ]
    deps = effective_dep_nodes(active_node, by_id)
    if not deps:
        out.append("- _no effective dependencies_")
        out.append("")
        return out
    for dep in deps:
        out.extend(_render_one_dep(repo_root, dep))
    return out
