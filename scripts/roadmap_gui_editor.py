"""Streamlit form to edit whitelisted roadmap node fields (scripts/roadmap_gui.py)."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from roadmap_crud_ops import edit_node_set_pairs
from roadmap_edit_fields import (
    DECISION_STATUS,
    EXEC_MILESTONES,
    EXEC_SUBTASKS,
    NODE_TYPES,
    title_to_codename,
)
from review_node import ReviewError, run_review

STATUSES = [
    "Not Started",
    "In Progress",
    "Complete",
    "Blocked",
    "Cancelled",
]


def _pairs_from_editor_merge(m: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = [
        ("title", m["title"].strip()),
        ("type", m["ntype"]),
        ("status", m["status"]),
        ("parent_id", m["parent_id"].strip()),
        ("codename", title_to_codename(m["title"])),
        ("goal", m["goal"].strip()),
        ("notes", m["notes"]),
        ("dependencies", m["deps"]),
        ("touch_zones", m["zones"]),
        ("acceptance", m["acc"]),
        ("risks", m["risks"]),
    ]
    if m["parallel_tracks"].strip():
        pairs.append(("parallel_tracks", m["parallel_tracks"].strip()))
    pairs.append(("planning_dir", m["planning_dir"].strip()))
    pairs.append(("execution_milestone", m["exec_m"].strip()))
    pairs.append(("execution_subtask", m["exec_s"].strip()))
    if m["use_decision"]:
        pairs.append(("decision.status", m["dec_status"]))
        pairs.append(("decision.decided_date", m["dec_date"].strip()))
        pairs.append(("decision.adr_ref", m["dec_adr"].strip()))
    if m["exec_s"] == "agentic":
        pairs.extend(
            [
                ("agentic_checklist.artifact_action", m["ac_art"].strip()),
                ("agentic_checklist.contract_citation", m["ac_spec"].strip()),
                ("agentic_checklist.interface_contract", m["ac_iface"].strip()),
                ("agentic_checklist.constraints_note", m["ac_cons"].strip()),
                ("agentic_checklist.dependency_note", m["ac_dep"].strip()),
                ("agentic_checklist.success_signal", m["ac_succ"].strip()),
                ("agentic_checklist.forbidden_patterns", m["ac_forb"].strip()),
            ],
        )
    return pairs


def _inject_kebab_live_sync(dom_safe: str) -> None:
    """Browser JS: mirror Title input into codename display while typing."""
    sid = json.dumps(dom_safe)
    components.html(
        f"""<script>
const SID = {sid};
function kebab(s) {{
  let t = (s || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-");
  t = t.replace(/-+/g, "-").replace(/^-|-$/g, "");
  return t || "";
}}
function tick() {{
  const root = window.parent.document;
  const el = root.getElementById("pm_kebab_display_" + SID);
  if (!el) return;
  const modal = root.querySelector('[data-testid="stModal"]');
  const scope = modal || root;
  const blocks = scope.querySelectorAll('[data-testid="stTextInput"]');
  let v = "";
  for (const b of blocks) {{
    const lab = b.querySelector("label");
    const inp = b.querySelector("input");
    if (!lab || !inp) continue;
    if (lab.innerText.trim().startsWith("Title")) {{
      v = inp.value;
      break;
    }}
  }}
  el.textContent = kebab(v);
}}
setInterval(tick, 100);
tick();
</script>""",
        height=0,
    )


def _render_title_and_autocodename(nid: str, node: dict) -> str:
    """Title outside the form so session state updates; codename is derived on save."""
    title_key = f"pm_title_{nid}"
    if title_key not in st.session_state:
        st.session_state[title_key] = str(node.get("title", ""))
    st.text_input("Title", key=title_key)
    dom_safe = re.sub(r"[^0-9A-Za-z_]", "_", nid)
    derived = title_to_codename(st.session_state[title_key])
    st.markdown(
        f'<code id="pm_kebab_display_{html.escape(dom_safe)}">'
        f"{html.escape(derived)}</code>",
        unsafe_allow_html=True,
    )
    _inject_kebab_live_sync(dom_safe)
    return title_key


def _editor_form_identity(
    node: dict,
    parent_opts: list[str],
    p_idx: int,
    t_idx: int,
    s_idx: int,
) -> dict[str, Any]:
    c1, c2, c3 = st.columns(3)
    with c1:
        ntype = st.selectbox("Type", options=sorted(NODE_TYPES), index=t_idx)
    with c2:
        status = st.selectbox("Status", STATUSES, index=s_idx)
    with c3:
        parent_id = st.selectbox("Parent node", parent_opts, index=p_idx)
    goal = st.text_input("Goal", value=str(node.get("goal", "")))
    notes = st.text_area("Notes", value=str(node.get("notes", "")), height=68)
    parallel_tracks = st.text_input(
        "Parallel tracks (integer, blank to leave unchanged)",
        value=(
            ""
            if node.get("parallel_tracks") is None
            else str(node["parallel_tracks"])
        ),
    )
    planning_dir = st.text_input(
        "planning_dir (repo-relative, e.g. planning/M1.2; blank clears)",
        value=str(node.get("planning_dir") or ""),
        help="Planning folder: overview.md, plan.md, tasks.md and/or tasks/*.md — see planning/README.md",
    )
    return {
        "ntype": ntype,
        "status": status,
        "parent_id": parent_id,
        "goal": goal,
        "notes": notes,
        "parallel_tracks": parallel_tracks,
        "planning_dir": planning_dir,
    }


def _editor_form_exec_collections(node: dict) -> dict[str, Any]:
    st.markdown("**Execution**")
    em_opts = [""] + sorted(EXEC_MILESTONES)
    cur_em = node.get("execution_milestone") or ""
    em_i = em_opts.index(cur_em) if cur_em in em_opts else 0
    es_opts = [""] + sorted(EXEC_SUBTASKS)
    cur_es = node.get("execution_subtask") or ""
    es_i = es_opts.index(cur_es) if cur_es in es_opts else 0
    e1, e2 = st.columns(2)
    with e1:
        exec_m = st.selectbox("Execution milestone", em_opts, index=em_i)
    with e2:
        exec_s = st.selectbox("Execution sub-task", es_opts, index=es_i)
    deps = st.text_area(
        "Dependencies (node ids, comma or space separated)",
        value=", ".join(node.get("dependencies") or []),
        height=60,
    )
    zones = st.text_area(
        "Touch zones (one path per line)",
        value="\n".join(node.get("touch_zones") or []),
        height=68,
    )
    acc = st.text_area(
        "Acceptance criteria (one per line; empty clears list)",
        value="\n".join(node.get("acceptance") or []),
        height=80,
    )
    risks = st.text_area(
        "Risks (one per line; empty clears list)",
        value="\n".join(node.get("risks") or []),
        height=68,
    )
    return {
        "exec_m": exec_m,
        "exec_s": exec_s,
        "deps": deps,
        "zones": zones,
        "acc": acc,
        "risks": risks,
    }


def _editor_form_decision(node: dict, dec: dict) -> dict[str, Any]:
    has_dec = bool(node.get("decision"))
    use_decision = st.checkbox("Include decision block", value=has_dec)
    d1, d2, d3 = st.columns(3)
    with d1:
        ds_opts = sorted(DECISION_STATUS)
        ds_i = (
            ds_opts.index(dec.get("status", "pending"))
            if dec.get("status") in ds_opts
            else 0
        )
        dec_status = st.selectbox("Decision status", ds_opts, index=ds_i)
    with d2:
        dec_date = st.text_input(
            "Decided date (ISO)",
            value=str(dec.get("decided_date", "") or ""),
        )
    with d3:
        dec_adr = st.text_input(
            "ADR reference",
            value=str(dec.get("adr_ref", "") or ""),
        )
    return {
        "use_decision": use_decision,
        "dec_status": dec_status,
        "dec_date": dec_date,
        "dec_adr": dec_adr,
    }


def _agentic_checklist_help_expander() -> None:
    with st.expander("What is the agentic checklist? (not the same as the constitution)"):
        st.markdown(
            """
These fields exist so an **automation/agent** can implement the task **without**
clarifying questions. They complement normal PM fields (`goal`, `acceptance`,
`dependencies`): goal states *why*, acceptance states *done*, and the checklist
states *what to build*, *which spec wins*, and *I/O shape*.

| Field | Role |
|-------|------|
| **Artifact action** | Concrete deliverable: file, route, component, migration, … |
| **Spec citation** | Authoritative doc/section (`shared/…`, `docs/…`) the work must follow. |
| **Interface contract** | Inputs → outputs (payloads, responses, props) at a glance. |
| **Constraints note** | Task-local rules (security, logging, perf). **Not** an override of repo constitution — cite ADR/spec if it duplicates global policy. |
| **Dependency note** | Ordering context: stubs, prior merges, env — *not* a replacement for `dependencies` ids. |
| **Success signal** (optional) | Observable check beyond acceptance lines (e.g. idempotent API behavior). |
| **Forbidden patterns** (optional) | Task-specific “do not” (e.g. no live calls in CI). **Not** constitutional; narrow scope. |

Full detail: `docs/roadmap-authoring.md` → *Writing implementable agentic tasks*.
            """.strip(),
        )


def _editor_form_agentic(ac: dict) -> dict[str, Any]:
    st.markdown("**Agentic checklist** (required when sub-task is agentic)")
    _agentic_checklist_help_expander()
    ac_art = st.text_input(
        "Artifact action — what is built or changed",
        value=str(ac.get("artifact_action", "") or ""),
    )
    ac_spec = st.text_input(
        "Contract citation — doc path / section (source of truth)",
        value=str(ac.get("contract_citation", "") or ""),
    )
    ac_iface = st.text_input(
        "Interface contract — inputs → outputs",
        value=str(ac.get("interface_contract", "") or ""),
    )
    ac_cons = st.text_input(
        "Constraints note — task-local rules (security, logging, …)",
        value=str(ac.get("constraints_note", "") or ""),
    )
    ac_dep = st.text_input(
        "Dependency note — ordering / stubs (see also Dependencies field)",
        value=str(ac.get("dependency_note", "") or ""),
    )
    ac_succ = st.text_input(
        "Success signal (optional) — observable extra check",
        value=str(ac.get("success_signal", "") or ""),
    )
    ac_forb = st.text_input(
        "Forbidden patterns (optional) — task-scoped prohibitions",
        value=str(ac.get("forbidden_patterns", "") or ""),
    )
    return {
        "ac_art": ac_art,
        "ac_spec": ac_spec,
        "ac_iface": ac_iface,
        "ac_cons": ac_cons,
        "ac_dep": ac_dep,
        "ac_succ": ac_succ,
        "ac_forb": ac_forb,
    }


def _editor_apply_save(
    repo_root: Path,
    nid: str,
    m: dict[str, Any],
    *,
    dialog_close_key: str | None,
    title_key: str | None,
) -> None:
    pairs = _pairs_from_editor_merge(m)
    if not m["parallel_tracks"].strip():
        pairs = [p for p in pairs if p[0] != "parallel_tracks"]
    if not m["use_decision"]:
        pairs = [p for p in pairs if not p[0].startswith("decision.")]
    try:
        edit_node_set_pairs(repo_root, nid, pairs)
        if dialog_close_key:
            st.session_state.pop(dialog_close_key, None)
        if title_key:
            st.session_state.pop(title_key, None)
        st.success("Saved and validated.")
        st.rerun()
    except ValueError as e:
        st.error(str(e))


def _editor_post_form(
    repo_root: Path,
    nid: str,
    by_reg: dict,
    settings: dict,
    apply_llm_env,
) -> None:
    if nid in by_reg:
        st.caption("Active branch (registry — read-only here)")
        st.json(by_reg[nid])
    if st.button("Run LLM review", key=f"llm_{nid}"):
        try:
            apply_llm_env(settings["llm"])
            st.session_state[f"report_{nid}"] = run_review(nid, repo_root)
        except (ReviewError, ValueError) as e:
            st.error(str(e))
    rep = st.session_state.get(f"report_{nid}")
    if rep:
        st.markdown(rep)


def render_node_editor(
    repo_root: Path,
    node: dict,
    all_ids_sorted: list[str],
    by_reg: dict,
    settings: dict,
    apply_llm_env,
    *,
    dialog_close_key: str | None = None,
) -> None:
    nid = node["id"]
    parent_opts = [""] + [i for i in all_ids_sorted if i != nid]
    cur_parent = node.get("parent_id") or ""
    p_idx = parent_opts.index(cur_parent) if cur_parent in parent_opts else 0
    t_idx = sorted(NODE_TYPES).index(node["type"]) if node["type"] in NODE_TYPES else 0
    s_idx = STATUSES.index(node["status"]) if node.get("status") in STATUSES else 0
    dec = node.get("decision") if isinstance(node.get("decision"), dict) else {}
    ac = (
        node.get("agentic_checklist")
        if isinstance(node.get("agentic_checklist"), dict)
        else {}
    )
    title_key = _render_title_and_autocodename(nid, node)
    with st.form(f"edit_{nid}"):
        a = _editor_form_identity(node, parent_opts, p_idx, t_idx, s_idx)
        b = _editor_form_exec_collections(node)
        c = _editor_form_decision(node, dec)
        d = _editor_form_agentic(ac)
        save = st.form_submit_button("Save all fields")
    title_live = str(st.session_state.get(title_key, ""))
    merged = {"title": title_live, **a, **b, **c, **d}
    if save:
        _editor_apply_save(
            repo_root,
            nid,
            merged,
            dialog_close_key=dialog_close_key,
            title_key=title_key,
        )
    _editor_post_form(repo_root, nid, by_reg, settings, apply_llm_env)
