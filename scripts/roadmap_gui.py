#!/usr/bin/env python3
"""Streamlit PM dashboard: dependency-layer roadmap view, registry overlay, settings."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_FALLBACK = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import streamlit as st
except ImportError as e:
    print(
        "error: GUI dependencies missing. Install: pip install 'specy-road[gui]'",
        file=sys.stderr,
    )
    raise SystemExit(2) from e

from roadmap_load import load_roadmap

from roadmap_gui_editor import render_node_editor
from roadmap_gui_planning import render_planning_lens
from roadmap_gui_gantt import (
    build_gantt_figure,
    compute_depths,
    dependency_edges,
    ordered_tree_rows,
)
from roadmap_gui_toolbar import render_pm_toolbar
from roadmap_gui_lib import (
    apply_llm_env_from_settings,
    ensure_watchdog_thread,
    load_registry,
    load_settings,
    registry_by_node_id,
    resolve_repo_root,
    roadmap_fingerprint,
    save_settings,
)
from roadmap_gui_remote import build_pr_hints, test_git_remote, test_llm_connection


def _llm_azure_fields(llm: dict) -> None:
    llm["azure_endpoint"] = st.text_input(
        "Azure endpoint",
        value=llm.get("azure_endpoint") or "",
    )
    llm["azure_api_key"] = st.text_input(
        "Azure API key",
        value=llm.get("azure_api_key") or "",
        type="password",
    )
    llm["azure_deployment"] = st.text_input(
        "Deployment name",
        value=llm.get("azure_deployment") or "",
    )
    llm["azure_api_version"] = st.text_input(
        "API version",
        value=llm.get("azure_api_version") or "2024-02-15-preview",
    )


def _llm_anthropic_fields(llm: dict) -> None:
    import os

    llm["anthropic_api_key"] = st.text_input(
        "Anthropic API key",
        value=llm.get("anthropic_api_key")
        or os.environ.get("SPECY_ROAD_ANTHROPIC_API_KEY", ""),
        type="password",
    )
    llm["anthropic_model"] = st.text_input(
        "Model",
        value=llm.get("anthropic_model") or "",
        placeholder="claude-sonnet-4-20250514",
    )


def _llm_openai_fields(llm: dict) -> None:
    import os

    llm["openai_api_key"] = st.text_input(
        "API key",
        value=llm.get("openai_api_key")
        or os.environ.get("SPECY_ROAD_OPENAI_API_KEY", ""),
        type="password",
    )
    llm["openai_model"] = st.text_input(
        "Model",
        value=llm.get("openai_model") or "gpt-4o-mini",
    )
    if llm["backend"] == "compatible":
        llm["openai_base_url"] = st.text_input(
            "Base URL",
            value=llm.get("openai_base_url") or "",
        )


def _llm_tab(settings: dict) -> None:
    llm = settings["llm"]
    opts = ["openai", "azure", "compatible", "anthropic"]
    cur = (llm.get("backend") or "openai").lower()
    if cur not in opts:
        cur = "openai"
    llm["backend"] = st.selectbox("Backend", opts, index=opts.index(cur))
    if llm["backend"] == "azure":
        _llm_azure_fields(llm)
    elif llm["backend"] == "anthropic":
        _llm_anthropic_fields(llm)
    else:
        _llm_openai_fields(llm)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Test LLM"):
            ok, msg = test_llm_connection(llm)
            (st.success if ok else st.error)(msg)
    with c2:
        if st.button("Save LLM settings"):
            save_settings(settings)
            st.toast("Saved LLM settings.")


def _git_tab(settings: dict) -> None:
    gr = settings["git_remote"]
    prov_opts = ["github", "gitlab", "custom"]
    curp = (gr.get("provider") or "github").lower()
    if curp not in prov_opts:
        curp = "github"
    gr["provider"] = st.selectbox("Provider", prov_opts, index=prov_opts.index(curp))
    gr["repo"] = st.text_input("Repository (owner/name)", value=gr.get("repo") or "")
    gr["token"] = st.text_input(
        "API token",
        value=gr.get("token") or "",
        type="password",
    )
    gr["base_url"] = st.text_input(
        "Base URL (optional, GitLab/self-hosted)",
        value=gr.get("base_url") or "",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Test Git connection"):
            ok, msg = test_git_remote(gr)
            (st.success if ok else st.error)(msg)
    with c2:
        if st.button("Save Git settings"):
            save_settings(settings)
            st.toast("Saved Git settings.")


def render_settings(settings: dict) -> dict:
    st.subheader("Settings")
    t1, t2 = st.tabs(["LLM", "Git remote"])
    with t1:
        _llm_tab(settings)
    with t2:
        _git_tab(settings)
    return settings


def _gantt_chart_instructions() -> None:
    st.caption(
        "Click a **row label** (text on the left) or a **bar** to edit. "
        "Use **Done** after saving to close the editor."
    )
    with st.expander("PM view limits (drag-drop, insert between rows)"):
        st.markdown(
            """
Streamlit + Plotly cannot yet support **dragging** dependency arrows or
**hover-to-insert** rows the way a native PM desktop app would. Use **Edit**
for dependency lists, **Indent / Outdent** for parent changes, or edit roadmap
JSON chunks / `specy-road` CLI for structural inserts.
            """.strip(),
        )


def _queue_edit_from_chart_selection(sel: object, by_id: dict) -> None:
    """Open edit modal when user selects a bar or outline hit target."""
    selection = getattr(sel, "selection", None)
    if not isinstance(selection, dict) or not selection.get("points"):
        return
    pt0 = selection["points"][0]
    cu = pt0.get("customdata")
    if not cu:
        return
    nid = cu[0] if isinstance(cu, (list, tuple)) else cu
    if nid not in by_id:
        return
    st.session_state.edit_dialog_nid = str(nid)
    st.session_state.selected_node_id = str(nid)


def _open_edit_node_modal_impl(
    repo_root: Path,
    by_id: dict,
    ids_sorted: list[str],
    by_reg: dict,
    settings: dict,
) -> None:
    nid = st.session_state.get("edit_dialog_nid")
    if not nid or nid not in by_id:
        return
    if st.button("Done", key="edit_dialog_done", use_container_width=True):
        st.session_state.pop("edit_dialog_nid", None)
        st.rerun()
    render_node_editor(
        repo_root,
        by_id[nid],
        ids_sorted,
        by_reg,
        settings,
        apply_llm_env_from_settings,
        dialog_close_key="edit_dialog_nid",
    )


try:
    _open_edit_node_modal = st.dialog("Edit node", width="large")(
        _open_edit_node_modal_impl,
    )
except TypeError:
    _open_edit_node_modal = st.dialog("Edit node")(_open_edit_node_modal_impl)


def _plotly_theme() -> tuple[str, str, str, str]:
    """template, arrow_color, label_text_default, label_text_highlight."""
    try:
        theme = getattr(st.context, "theme", None)
        base = getattr(theme, "base", None) if theme is not None else None
        if base == "dark":
            return (
                "plotly_dark",
                "rgba(230, 230, 230, 0.65)",
                "rgba(236, 236, 236, 0.94)",
                "#ff8a80",
            )
    except Exception:
        pass
    return (
        "plotly_white",
        "rgba(45, 45, 45, 0.55)",
        "rgba(28, 28, 28, 0.9)",
        "#b71c1c",
    )


def _panel_bundle(
    repo_root: Path,
    nodes: list[dict],
    settings: dict,
) -> tuple[dict, list[tuple[dict, int]], list[str], dict, object]:
    by_id = {n["id"]: n for n in nodes}
    tree_rows = ordered_tree_rows(nodes)
    ordered = [t[0] for t in tree_rows]
    row_depths = [d for _, d in tree_rows]
    ids_sorted = sorted(by_id.keys())
    by_reg = registry_by_node_id(load_registry(repo_root))
    pr_hints = build_pr_hints(by_reg, settings["git_remote"])
    tpl, arrow, lbl_def, lbl_hi = _plotly_theme()
    hi = st.session_state.get("gantt_highlight_nid")
    if hi is not None and hi not in by_id:
        st.session_state.pop("gantt_highlight_nid", None)
        hi = None
    fig = build_gantt_figure(
        ordered,
        row_depths,
        compute_depths(nodes),
        dependency_edges(nodes),
        pr_hints,
        template=tpl,
        arrow_color=arrow,
        highlight_nid=hi,
        label_color=lbl_def,
        label_highlight=lbl_hi,
    )
    return by_id, tree_rows, ids_sorted, by_reg, fig


def _render_graph_and_detail(repo_root: Path, settings: dict) -> None:
    try:
        nodes = load_roadmap(repo_root)["nodes"]
    except Exception as e:
        st.error(f"Failed to load roadmap: {e}")
        return
    if not nodes:
        st.warning("No roadmap nodes loaded.")
        return

    by_id, tree_rows, ids_sorted, by_reg, fig = _panel_bundle(
        repo_root,
        nodes,
        settings,
    )
    ordered_ids = [t[0]["id"] for t in tree_rows]
    cur = st.session_state.get("selected_node_id")
    if cur not in by_id:
        st.session_state.selected_node_id = ordered_ids[0]

    sel = st.session_state.selected_node_id
    render_pm_toolbar(repo_root, by_id, nodes, sel)
    render_planning_lens(repo_root, by_id[sel], nodes)
    _gantt_chart_instructions()

    chart_sel = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="gantt_chart",
    )
    _queue_edit_from_chart_selection(chart_sel, by_id)

    if st.session_state.get("edit_dialog_nid"):
        _open_edit_node_modal(
            repo_root,
            by_id,
            ids_sorted,
            by_reg,
            settings,
        )


def _auto_refresh(repo_root: Path, poll: int) -> None:
    if "_bump" not in st.session_state:
        st.session_state._bump = [0.0]
    ensure_watchdog_thread(repo_root, st.session_state._bump)
    if "_fp" not in st.session_state:
        st.session_state._fp = roadmap_fingerprint(repo_root)
    if poll <= 0:
        return

    @st.fragment(run_every=timedelta(seconds=poll))
    def _poll() -> None:
        fp = roadmap_fingerprint(repo_root)
        bump = st.session_state._bump[0]
        last_bump = st.session_state.get("_last_bump_seen", 0.0)
        if fp != st.session_state._fp or bump > last_bump:
            st.session_state._fp = fp
            st.session_state._last_bump_seen = bump
            st.rerun()

    _poll()


def main() -> None:
    st.set_page_config(page_title="specy-road roadmap", layout="wide")
    repo_root = resolve_repo_root(_REPO_ROOT_FALLBACK)

    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()
    settings = st.session_state.settings

    poll = st.sidebar.slider("Auto-refresh seconds (0=off)", 0, 120, 5)
    st.sidebar.caption(f"Repo: `{repo_root}`")
    with st.sidebar.expander("Settings", expanded=False):
        settings = render_settings(settings)
        st.session_state.settings = settings

    apply_llm_env_from_settings(settings["llm"])
    _render_graph_and_detail(repo_root, settings)
    _auto_refresh(repo_root, poll)


if __name__ == "__main__":
    main()
