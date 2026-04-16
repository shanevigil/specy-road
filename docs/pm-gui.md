# PM Gantt UI — production architecture

The supported **PM dashboard** is a **FastAPI** server plus a **prebuilt React** single-page app. There is no alternate GUI tree in this repository.

## What ships

- **Server:** [`specy_road/gui_app.py`](../specy_road/gui_app.py) — JSON API for roadmap, planning files, and settings; serves the static UI from [`specy_road/pm_gantt_static/`](../specy_road/pm_gantt_static/) (package data in [`pyproject.toml`](../pyproject.toml)).
- **Frontend sources:** [`gui/pm-gantt/`](../gui/pm-gantt/) — Vite + React + TypeScript. Production assets are produced with `npm run build`, which writes into `specy_road/pm_gantt_static/` for inclusion in the wheel.
- **CLI:** `specy-road gui` starts Uvicorn with the FastAPI app. Install optional dependencies with `pip install 'specy-road[gui]'` or `'specy-road[gui-next]'` (same dependency sets; see `pyproject.toml`).

## How to use it and install it

- **Day-to-day PM usage** (browser workflow, what you see in the UI): [pm-workflow.md](pm-workflow.md).
- **First-time install, rebuild, and security checks** (including `specy-road init gui --install-gui`): [setup.md](setup.md) (section *Optional: Gantt PM GUI*).

Contributors editing React code: rebuild from `gui/pm-gantt/` or use the Vite dev server with a separate Uvicorn process; details are in [pm-workflow.md](pm-workflow.md) under the Gantt PM UI sections.

## Historical note

The older Streamlit-based dashboard was removed. The toolkit standard is the stack above only.
