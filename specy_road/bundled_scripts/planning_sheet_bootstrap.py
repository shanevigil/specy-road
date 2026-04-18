"""Create a feature sheet on disk and set ``planning_dir`` for new roadmap nodes."""

from __future__ import annotations

from pathlib import Path

from planning_artifacts import (
    expected_planning_rel,
    normalize_planning_dir,
    resolve_planning_path,
)
from specy_road.runtime_paths import specy_road_package_dir

_TYPES_WITH_PLANNING = frozenset({"vision", "phase", "milestone", "task", "gate"})
_TEMPLATES = specy_road_package_dir() / "templates" / "planning-node"
_FEATURE_TEMPLATE = "feature-sheet.md.template"
_GATE_TEMPLATE = "gate-sheet.md.template"

# If ``feature-sheet.md.template`` is missing (broken install), LLM + validators still have a fallback.
_FALLBACK_LEVEL2_TITLES = (
    "Intent",
    "Approach",
    "Tasks / checklist",
    "References",
)

_FALLBACK_GATE_LEVEL2_TITLES = (
    "Why this gate exists",
    "Criteria to clear",
    "Decisions and notes",
    "Resolution",
    "References",
)


def _level2_titles_from_template(filename: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    path = _TEMPLATES / filename
    if not path.is_file():
        return fallback
    titles: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## ") and not line.startswith("###"):
            titles.append(line[3:].strip())
    return tuple(titles) if titles else fallback


def feature_sheet_level2_titles() -> tuple[str, ...]:
    """Ordered ``##`` section titles from ``feature-sheet.md.template`` (source of truth)."""
    return _level2_titles_from_template(_FEATURE_TEMPLATE, _FALLBACK_LEVEL2_TITLES)


def gate_sheet_level2_titles() -> tuple[str, ...]:
    """Ordered ``##`` section titles from ``gate-sheet.md.template`` (source of truth)."""
    return _level2_titles_from_template(_GATE_TEMPLATE, _FALLBACK_GATE_LEVEL2_TITLES)


def feature_sheet_structure_instruction_for_llm() -> str:
    """One instruction line for ``review_node`` SYSTEM_PROMPT (kept in sync with the template)."""
    titles = feature_sheet_level2_titles()
    ordered = ", ".join(f"## {t}" for t in titles)
    return (
        "Structure: use exactly these level-2 sections in this order: "
        f"{ordered}. "
        "Use markdown task items (`- [ ]` / `- [x]`) under Tasks / checklist. "
        "If the sheet uses legacy headings, merge content into this shape "
        "(e.g. fold Sources/Contracts into References and Intent)."
    )


def gate_sheet_structure_instruction_for_llm() -> str:
    """One instruction line for gate planning LLM review (kept in sync with ``gate-sheet.md.template``)."""
    titles = gate_sheet_level2_titles()
    ordered = ", ".join(f"## {t}" for t in titles)
    return (
        "Structure: use exactly these level-2 sections in this order: "
        f"{ordered}. "
        "This is a PM hold document, not an implementation checklist—avoid "
        "task-style build steps unless they are explicitly part of clearing the gate."
    )


def feature_sheet_expected_shape_block() -> str:
    """User-message block for LLM review (matches scaffold template)."""
    lines = "\n".join(f"- ## {t}" for t in feature_sheet_level2_titles())
    return (
        "Canonical feature sheet outline (same as `specy-road scaffold-planning`):\n"
        + lines
    )


def gate_sheet_expected_shape_block() -> str:
    """User-message block for LLM review of a gate planning sheet."""
    lines = "\n".join(f"- ## {t}" for t in gate_sheet_level2_titles())
    return (
        "Canonical gate planning sheet outline (same as `specy-road scaffold-planning` "
        "for `type: gate` nodes):\n"
        + lines
    )


def planning_review_expected_shape_block(node_type: str | None = None) -> str:
    """Expected-shape block for LLM planning review: gate vs feature sheet."""
    if str(node_type or "").strip().lower() == "gate":
        return gate_sheet_expected_shape_block()
    return feature_sheet_expected_shape_block()


def _substitute_node_id(text: str, node_id: str) -> str:
    return text.replace("{{NODE_ID}}", node_id)


def render_planning_sheet_template(node_id: str, *, node_type: str | None = None) -> str:
    """
    Render the planning markdown scaffold for ``node_id``.

    ``type: gate`` uses ``gate-sheet.md.template`` when present; all other types
    use ``feature-sheet.md.template``. Missing gate template falls back to the
    feature sheet template.
    """
    is_gate = str(node_type or "").strip().lower() == "gate"
    name = _GATE_TEMPLATE if is_gate else _FEATURE_TEMPLATE
    path = _TEMPLATES / name
    if is_gate and not path.is_file():
        path = _TEMPLATES / _FEATURE_TEMPLATE
    if not path.is_file():
        raise FileNotFoundError(f"missing template {path}")
    return _substitute_node_id(path.read_text(encoding="utf-8"), node_id)


def render_feature_sheet_template(node_id: str) -> str:
    """Render the milestone/task-style feature sheet template only."""
    path = _TEMPLATES / _FEATURE_TEMPLATE
    if not path.is_file():
        raise FileNotFoundError(f"missing template {path}")
    return _substitute_node_id(path.read_text(encoding="utf-8"), node_id)


def ensure_planning_sheet_for_new_node(repo_root: Path, node: dict) -> None:
    """
    For vision/phase/milestone/task/gate nodes, write ``planning/<id>_<slug>_<node_key>.md`` if
    missing and set ``planning_dir`` on ``node``. No-op for other types or missing id/key.
    """
    t = node.get("type")
    if t not in _TYPES_WITH_PLANNING:
        return
    nid = node.get("id")
    nk = node.get("node_key")
    if not isinstance(nid, str) or not nid.strip():
        return
    if not isinstance(nk, str) or not nk.strip():
        return
    norm = normalize_planning_dir(expected_planning_rel(node))
    root = repo_root.resolve()
    dest = resolve_planning_path(root, norm)
    if dest.exists() and dest.is_dir():
        raise ValueError(f"{norm} exists and is a directory (expected a single .md file)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file():
        dest.write_text(
            render_planning_sheet_template(nid.strip(), node_type=t),
            encoding="utf-8",
        )
    node["planning_dir"] = norm


def remove_planning_sheet_if_present(repo_root: Path, planning_dir: object) -> None:
    """Unlink the feature sheet when ``planning_dir`` resolves to a file; otherwise no-op."""
    if not isinstance(planning_dir, str) or not planning_dir.strip():
        return
    try:
        norm = normalize_planning_dir(planning_dir.strip())
    except ValueError:
        return
    p = resolve_planning_path(repo_root, norm)
    if p.is_file():
        p.unlink()
