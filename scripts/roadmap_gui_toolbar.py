"""Toolbar row for scripts/roadmap_gui.py (indent, highlight)."""

from __future__ import annotations

import sys
from pathlib import Path

_TB_DIR = Path(__file__).resolve().parent
if str(_TB_DIR) not in sys.path:
    sys.path.insert(0, str(_TB_DIR))

import streamlit as st  # noqa: E402

from roadmap_crud_ops import edit_node_set_pairs  # noqa: E402
from roadmap_gui_tree import indent_parent_id, outdent_parent_id  # noqa: E402


def _pm_outdent(repo_root: Path, by_id: dict, sel: str) -> None:
    o_target = outdent_parent_id(by_id, sel) if sel in by_id else None
    if st.button(
        "← Outdent",
        key="pm_outdent",
        disabled=sel not in by_id or o_target is None,
        help="Move to parent of current parent",
    ):
        try:
            edit_node_set_pairs(
                repo_root,
                sel,
                [("parent_id", o_target if o_target else "")],
            )
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _pm_indent(
    repo_root: Path,
    by_id: dict,
    tree_rows: list[tuple[dict, int]],
    sel: str,
) -> None:
    in_target = indent_parent_id(tree_rows, by_id, sel) if sel in by_id else None
    if st.button(
        "Indent →",
        key="pm_indent",
        disabled=in_target is None,
        help="Make child of the row above in the outline",
    ):
        try:
            edit_node_set_pairs(
                repo_root,
                sel,
                [("parent_id", in_target or "")],
            )
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _toolbar_dep_highlight(by_id: dict, sel: str) -> None:
    deps = list(by_id[sel].get("dependencies") or []) if sel in by_id else []
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
    tree_rows: list[tuple[dict, int]],
    sel: str,
) -> None:
    c1, c2, c3, c4 = st.columns([1.1, 1.1, 2.2, 2.2])
    with c1:
        _pm_outdent(repo_root, by_id, sel)
    with c2:
        _pm_indent(repo_root, by_id, tree_rows, sel)
    with c3:
        _toolbar_dep_highlight(by_id, sel)
    with c4:
        st.caption(f"Selected: `{sel}`")
