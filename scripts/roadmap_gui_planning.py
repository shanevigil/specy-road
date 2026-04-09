"""Planning markdown panel for scripts/roadmap_gui.py (planning_dir + light file edit)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import streamlit as st  # noqa: E402

from planning_artifacts import (  # noqa: E402
    collect_planning_artifact_errors,
    normalize_planning_dir,
    planning_artifact_paths,
)


def _filter_planning_errors(
    errors: list[str],
    nid: str,
    norm: str | None,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for msg in errors:
        if msg in seen:
            continue
        if f"node {nid}:" in msg:
            out.append(msg)
            seen.add(msg)
            continue
        if norm:
            nposix = norm.replace("\\", "/")
            if nposix in msg.replace("\\", "/"):
                out.append(msg)
                seen.add(msg)
    return out


def _editable_md(
    repo_root: Path,
    nid: str,
    label: str,
    path: Path,
    *,
    state_prefix: str,
) -> None:
    rel = path.relative_to(repo_root)
    exists = path.is_file()
    st.markdown(f"**{label}** — `{rel}` ({'present' if exists else 'missing'})")
    sk = f"{state_prefix}_{nid}_{label}"
    rlk = f"{state_prefix}_{nid}_{label}_reload"
    if st.button("Reload from disk", key=rlk):
        st.session_state[sk] = path.read_text(encoding="utf-8") if path.is_file() else ""
        st.rerun()
    if sk not in st.session_state:
        st.session_state[sk] = path.read_text(encoding="utf-8") if path.is_file() else ""
    st.text_area(
        label,
        key=sk,
        height=260,
        label_visibility="collapsed",
    )
    if st.button(f"Save {label}", key=f"{state_prefix}_save_{nid}_{label}"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(st.session_state.get(sk, "")), encoding="utf-8")
        st.success(f"Wrote `{rel}`")
        st.rerun()


def _planning_norm_or_errors(
    repo_root: Path,
    nid: str,
    pd: object,
    all_errs: list[str],
) -> str | None:
    if not isinstance(pd, str) or not pd.strip():
        return None
    try:
        return normalize_planning_dir(pd.strip())
    except ValueError as e:
        st.error(f"Invalid planning_dir: {e}")
        for e_line in _filter_planning_errors(all_errs, nid, None):
            st.warning(e_line)
        return None


def _render_planning_file_editors(
    repo_root: Path,
    nid: str,
    norm: str,
) -> None:
    paths = planning_artifact_paths(repo_root, norm)
    _editable_md(
        repo_root,
        nid,
        "overview.md",
        paths["overview"],
        state_prefix="pm_overview",
    )
    _editable_md(repo_root, nid, "plan.md", paths["plan"], state_prefix="pm_plan")
    _editable_md(
        repo_root,
        nid,
        "tasks.md",
        paths["tasks_md"],
        state_prefix="pm_tasks",
    )
    td = paths["tasks_dir"]
    if td.is_dir():
        st.markdown(
            "**tasks/** (per-task markdown; each file needs YAML frontmatter `node_id:`)",
        )
        for md in sorted(td.rglob("*.md")):
            st.markdown(f"- `{md.relative_to(repo_root)}`")


def render_planning_lens(repo_root: Path, node: dict, all_nodes: list[dict]) -> None:
    nid = node["id"]
    pd = node.get("planning_dir")
    with st.expander("Planning markdown (`planning_dir`)", expanded=False):
        st.caption(
            "Structured overview/plan/tasks beside the roadmap graph. "
            "See `planning/README.md` and CLI `specy-road scaffold-planning <NODE_ID>`."
        )
        all_errs = collect_planning_artifact_errors(repo_root, all_nodes)
        norm = _planning_norm_or_errors(repo_root, nid, pd, all_errs)
        if norm is None and isinstance(pd, str) and pd.strip():
            return
        for e_line in _filter_planning_errors(all_errs, nid, norm):
            st.error(e_line)
        if not norm:
            st.info(
                "Set **planning_dir** in **Edit node** (e.g. `planning/M1.2`) "
                "to link markdown artifacts.",
            )
            return
        try:
            _render_planning_file_editors(repo_root, nid, norm)
        except ValueError as e:
            st.error(str(e))
