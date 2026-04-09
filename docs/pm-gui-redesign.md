# PM GUI redesign (Streamlit alternatives)

This document carries forward the decisions from the PM GUI stack review: **which interactions justify leaving Streamlit**, **recommended stack**, **packaging**, and **where to run the React Flow spike**.

## 1. Interaction spec (must-haves vs nice-to-haves)

Use this list to decide whether to invest in a client-side SPA (e.g. React) or stay on a Python-first UI (Streamlit, NiceGUI, Reflex).

### Tier A — native PM / graph editor (favors FastAPI + React or similar)

| Interaction | Notes |
|-------------|--------|
| **Drag-create or drag-edit dependency edges** | Connect handles between nodes; validate DAG / no cycles server-side. |
| **Reorder or insert rows on the canvas** | Hover gaps, drag reorder, without full page rerun. |
| **Multi-select + batch actions** | e.g. shift-click, box select, bulk status. |
| **Keyboard-first editing** | Focus management, shortcuts, escape to cancel. |
| **Undo / redo** | Client stack or operational transform; Streamlit is a poor fit. |
| **Optimistic UI** | Show change immediately; reconcile with server validation errors. |

If **two or more** of Tier A are must-haves, treat **Streamlit as a stopgap** and plan a **Python API + SPA**.

### Tier B — richer dashboard (Python-first may suffice)

| Interaction | Notes |
|-------------|--------|
| Better forms, validation messages, tabs | NiceGUI / Reflex / improved Streamlit. |
| Faster refresh, less flicker | WebSocket push (NiceGUI) or smaller reruns (Streamlit fragments). |
| Secondary panels (planning markdown, PR hints) | Mostly layout; any stack can do it. |

### Tier C — current Streamlit baseline

The existing app ([`scripts/roadmap_gui.py`](../scripts/roadmap_gui.py)) already provides: dependency-layer **Plotly** view, **click-to-select**, **dialog editor**, indent/outdent toolbar, settings, file-watch refresh. Documented limits: **no** drag dependency arrows or hover-insert rows in Plotly + Streamlit.

---

## 2. Stack choice and packaging

### Recommendation

| If you need… | Prefer… |
|--------------|---------|
| Tier A must-haves | **FastAPI** (or Starlette) **+** Vite **+** **React** (or Vue/Svelte). Graph: **@xyflow/react** (React Flow), Cytoscape.js, or ELK + canvas. |
| Tier B only, stay mostly Python | **NiceGUI** or **Reflex**, or keep **Streamlit** and narrow scope. |
| Desktop app distribution | **Tauri** or **Electron** + React (higher packaging cost for PMs). |

**Node.js role:** use Node for **frontend dev/build** (`npm`, Vite). The **runtime** for end users can remain **Python-only** if the wheel ships a **prebuilt `dist/`** and `specy-road gui` serves it via FastAPI + Uvicorn.

### Packaging sketch (target state, not all implemented yet)

1. Optional extra e.g. `specy-road[gui-next]` with `fastapi`, `uvicorn[standard]`.
2. Python package data includes `specy_road/gui_static/` (contents of `npm run build`).
3. CLI: `specy-road gui` → resolve repo root, start ASGI app that mounts static files and JSON API (roadmap load, node patch, LLM/git test — reusing `scripts/roadmap_*` modules).
4. **Contributors:** run `npm install && npm run dev` inside the spike/app folder for UI work; Python-only contributors skip npm until they touch the UI.

### Legacy GUI

`pip install "specy-road[gui]"` and `streamlit run scripts/roadmap_gui.py` remain documented until the new UI reaches parity; then deprecate or remove.

---

## 3. React Flow spike

A minimal **Vite + React + TypeScript** app lives under [`gui-spike/react-flow-spike/`](../gui-spike/react-flow-spike/). It loads a **merged** roadmap sample ([`public/sample-merged-roadmap.json`](../gui-spike/react-flow-spike/public/sample-merged-roadmap.json)) with the same shape as `load_roadmap()` output (`version` + `nodes`), lays nodes by **dependency depth** (same idea as [`scripts/roadmap_gui_gantt.py`](../scripts/roadmap_gui_gantt.py)), and draws **dependency edges** (`source` = dependency id, `target` = dependent id).

**Run locally (requires Node 18+):**

```bash
cd gui-spike/react-flow-spike
npm install
npm run dev
```

Open the printed local URL. This validates that **React Flow + roadmap JSON** is viable before a full API and editor port.

**Build static assets (for future embedding in Python):**

```bash
cd gui-spike/react-flow-spike
npm install
npm run build
```

Output: `gui-spike/react-flow-spike/dist/` (not committed; add to CI that builds the wheel if you ship the SPA inside the package).

---

## 4. Migration sequence (when you implement for real)

1. Extract or reuse pure functions: roadmap load, registry, `roadmap_edit_fields` / `roadmap_crud_ops`, LLM/git helpers (already largely outside Streamlit widgets).
2. Add JSON HTTP API + optional WebSocket for file-change events.
3. Implement SPA against the API; keep Streamlit until feature parity.
4. Wire `specy-road gui` and optional `[gui-next]` extra; document in [setup.md](setup.md) and [pm-workflow.md](pm-workflow.md).
