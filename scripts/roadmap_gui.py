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

from roadmap_crud_ops import edit_node_set_pairs
from roadmap_load import load_roadmap
from review_node import ReviewError, run_review

from roadmap_gui_lib import (
    apply_llm_env_from_settings,
    build_figure,
    ensure_watchdog_thread,
    load_registry,
    load_settings,
    registry_by_node_id,
    layout_nodes,
    resolve_repo_root,
    roadmap_fingerprint,
    save_settings,
)
from roadmap_gui_remote import build_pr_hints, test_git_remote, test_llm_connection

STATUSES = [
    "Not Started",
    "In Progress",
    "Complete",
    "Blocked",
    "Cancelled",
]


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
    opts = ["openai", "azure", "compatible"]
    cur = (llm.get("backend") or "openai").lower()
    if cur not in opts:
        cur = "openai"
    llm["backend"] = st.selectbox("Backend", opts, index=opts.index(cur))
    if llm["backend"] == "azure":
        _llm_azure_fields(llm)
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


def _sync_plotly_selection(sel: object, current: str | None) -> str | None:
    selection = getattr(sel, "selection", None)
    if not isinstance(selection, dict) or not selection.get("points"):
        return current
    pts = selection["points"]
    if not pts:
        return current
    pt0 = pts[0]
    if "customdata" in pt0 and pt0["customdata"]:
        return pt0["customdata"][0]
    if "text" in pt0:
        return pt0["text"]
    return current


def _detail_left(selected: str, n: dict, by_reg: dict) -> None:
    st.markdown(f"### {selected}: {n.get('title', '')}")
    st.write("**Type:**", n.get("type"))
    st.write("**Status:**", n.get("status"))
    st.write("**Dependencies:**", ", ".join(n.get("dependencies") or []) or "—")
    st.write("**Touch zones:**", ", ".join(n.get("touch_zones") or []) or "—")
    if selected in by_reg:
        st.json(by_reg[selected])
    ac = n.get("agentic_checklist")
    if ac:
        st.markdown("**Agentic checklist**")
        st.json(ac)


def _detail_right(
    selected: str,
    n: dict,
    repo_root: Path,
    settings: dict,
) -> None:
    acc = n.get("acceptance") or []
    if acc:
        st.markdown("**Acceptance**")
        for a in acc:
            st.write(f"- {a}")
    risks = n.get("risks") or []
    if risks:
        st.markdown("**Risks**")
        for r in risks:
            st.write(f"- {r}")
    idx = (
        STATUSES.index(n["status"])
        if n.get("status") in STATUSES
        else 0
    )
    status_choice = st.selectbox(
        "Set status (writes YAML + validates)",
        STATUSES,
        index=idx,
        key=f"st_{selected}",
    )
    if st.button("Save status", key=f"save_{selected}"):
        try:
            edit_node_set_pairs(repo_root, selected, [("status", status_choice)])
            st.success("Updated and validated.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    if st.button("Run LLM review", key=f"rev_{selected}"):
        try:
            apply_llm_env_from_settings(settings["llm"])
            st.session_state[f"report_{selected}"] = run_review(selected, repo_root)
        except (ReviewError, ValueError) as e:
            st.error(str(e))
    rep = st.session_state.get(f"report_{selected}")
    if rep:
        st.markdown(rep)


def _render_graph_and_detail(repo_root: Path, settings: dict) -> None:
    try:
        nodes = load_roadmap(repo_root)["nodes"]
    except Exception as e:
        st.error(f"Failed to load roadmap: {e}")
        return

    reg = load_registry(repo_root)
    by_reg = registry_by_node_id(reg)
    pos, edges = layout_nodes(nodes)
    pr_hints = build_pr_hints(by_reg, settings["git_remote"])
    fig = build_figure(nodes, pos, edges, pr_hints)

    selected = st.session_state.get("selected_node_id")
    st.subheader("Dependency view")
    sel = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="roadmap_chart",
    )
    selected = _sync_plotly_selection(sel, selected)
    if selected:
        st.session_state.selected_node_id = selected

    ids = [n["id"] for n in sorted(nodes, key=lambda x: x["id"])]
    pick = st.selectbox(
        "Select node (or click chart)",
        ids,
        index=ids.index(selected) if selected in ids else 0,
    )
    if pick != selected:
        st.session_state.selected_node_id = pick
        selected = pick

    by_id = {n["id"]: n for n in nodes}
    if selected and selected in by_id:
        st.divider()
        c1, c2 = st.columns((1, 1))
        with c1:
            _detail_left(selected, by_id[selected], by_reg)
        with c2:
            _detail_right(selected, by_id[selected], repo_root, settings)


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
