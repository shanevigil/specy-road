"""Toolbar row for scripts/roadmap_gui.py (indent, highlight)."""

from __future__ import annotations

import sys
from pathlib import Path

_TB_DIR = Path(__file__).resolve().parent
if str(_TB_DIR) not in sys.path:
    sys.path.insert(0, str(_TB_DIR))

import streamlit as st  # noqa: E402

from roadmap_gui_tree import (  # noqa: E402
    can_indent_outline,
    can_outdent_outline,
)
from roadmap_outline_ops import apply_indent, apply_outdent  # noqa: E402


def _pm_outdent(repo_root: Path, by_id: dict, sel: str) -> None:
    can_do = sel in by_id and can_outdent_outline(by_id, sel)
    if st.button(
        "← Outdent",
        key="pm_outdent",
        disabled=not can_do,
        help="Move to parent of current parent",
    ):
        if apply_outdent(repo_root, sel):
            st.rerun()


def _pm_indent(
    repo_root: Path,
    nodes: list[dict],
    by_id: dict,
    sel: str,
) -> None:
    can_do = sel in by_id and can_indent_outline(nodes, by_id, sel)
    if st.button(
        "Indent →",
        key="pm_indent",
        disabled=not can_do,
        help="Nest under the sibling directly above (same parent)",
    ):
        if apply_indent(repo_root, sel):
            st.rerun()


def _toolbar_dep_highlight(by_id: dict, sel: str) -> None:
    dep_keys = list(by_id[sel].get("dependencies") or []) if sel in by_id else []
    key_to_id = {n["node_key"]: n["id"] for n in by_id.values() if n.get("node_key")}
    deps = [key_to_id.get(k, k) for k in dep_keys]
    hi_opts = ["— None —"] + deps
    cur_hi = st.session_state.get("gantt_highlight_nid")
    hi_ix = 1 + deps.index(cur_hi) if cur_hi in deps else 0
    pick = st.selectbox(
        "Highlight dependency row",
        hi_opts,
        index=min(hi_ix, len(hi_opts) - 1),
        key="pm_dep_highlight",
    )
    if pick == "— None —":
        st.session_state.pop("gantt_highlight_nid", None)
    else:
        st.session_state.gantt_highlight_nid = pick


def render_pm_toolbar(
    repo_root: Path,
    by_id: dict,
    nodes: list[dict],
    sel: str,
) -> None:
    c1, c2, c3, c4 = st.columns([1.1, 1.1, 2.2, 2.2])
    with c1:
        _pm_outdent(repo_root, by_id, sel)
    with c2:
        _pm_indent(repo_root, nodes, by_id, sel)
    with c3:
        _toolbar_dep_highlight(by_id, sel)
    with c4:
        st.caption(f"Selected: `{sel}`")
