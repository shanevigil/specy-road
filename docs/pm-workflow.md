# PM workflow: roadmap, dashboard, and day-to-day use

This guide is for **product managers, program leads, and tech leads** who shape what gets built and in what order. You do not need to be a developer; you need a copy of the project on your machine and a way to run a few commands (or use the visual dashboard).

Developers follow [dev-workflow.md](dev-workflow.md). First-time machine setup (Python, git clone, optional IDE stubs) is in [setup.md](setup.md).

---

## What you are working with

- The **roadmap** is a set of structured files in the repo under `roadmap/`. They describe milestones, tasks, dependencies, and status (**JSON chunk files** listed in `manifest.json`, plus `registry.yaml` for active claims).
- **Git** is how the team shares changes. You pull updates before you edit, and you commit when you save roadmap changes.
- You can work in two ways: a **visual dashboard** in the browser (recommended if you prefer clicking to typing), or the **command line** (`specy-road` …) for quick edits and scripts.

There is no “import from Word” flow: the source of truth is the **chunk files** under `roadmap/` and the manifest order in `manifest.json`. Root `[roadmap.md](../roadmap.md)` is a **generated index** — refresh it with `specy-road export` or `specy-road sync`.

### PM glossary (graph `type` values)

Roadmap nodes keep stable machine `type` values for validation. In everyday terms:

| `type` in files | Typical PM meaning |
|-----------------|--------------------|
| `vision` | Program narrative or north star |
| `phase` | Time-bounded arc or release train |
| `milestone` | Shippable slice or feature milestone |
| `task` | Sub-feature or work item under a milestone |

---

## Before you start

1. **Python 3.11+** installed ([python.org](https://www.python.org/downloads/) or your IT-provided install).
2. A **clone of the repository** on your computer (same folder the developers use).
3. A **terminal** open **in that folder** (the repo “root” — where you see `roadmap/`, `scripts/`, and `README.md`).

**Windows users:** If you use **WSL**, open a Linux terminal, `cd` to the project there, and run all commands below inside WSL. Then open the dashboard in your normal browser at `http://localhost:8501`.

---

## Install the PM dashboard (one-time)

Install the `specy-road` CLI once per machine (use a virtual environment if your team uses one):

```bash
pip install specy-road
```

Confirm the CLI is available:

```bash
specy-road --help
```

**Gantt PM UI (recommended for most PMs):** you do not run `npm` or build the frontend. After `pip install specy-road`, run:

```bash
specy-road init --install-gui
specy-road gui
```

**Streamlit dashboard (optional):** install the Streamlit extra and run the script from the repository root:

```bash
pip install "specy-road[gui]"
```

For a full developer install (tests, editable package), see [setup.md](setup.md).

---

## Open and use the roadmap dashboard

You can use either the **Gantt PM UI** (split outline + dependency timeline, drag-drop sibling reorder, double-click planning editor) or the **Streamlit** dashboard.

### Gantt PM UI (FastAPI + React)

**Working directory:** run `specy-road gui` from your **project repository root** (the folder that contains `roadmap/` and `scripts/`), or pass `--repo-root /path/to/repo` so the server loads the correct roadmap.

**One-time (PM path — no Node.js):** the built UI ships inside the `specy-road` package. After `pip install specy-road`:

```bash
specy-road init --install-gui
```

Equivalent manual install: `pip install 'specy-road[gui-next]'`.

**Every session:**

```bash
specy-road gui
```

The terminal prints the URL (default **[http://127.0.0.1:8765](http://127.0.0.1:8765)**). Options: `specy-road gui --help` for `--host`, `--port`, and `--repo-root`. If **address already in use** on port 8765, stop the other process or run `specy-road gui --port 8766` and open that port in the browser.

**Contributors / UI development** (git clone, hot reload): install extras from the clone (`pip install -e ".[gui-next]"`), rebuild the Vite app when you change React code (`cd gui/pm-gantt && npm install && npm run build` — output goes to `specy_road/pm_gantt_static/`). For local dev with reload: in one terminal, `PYTHONPATH=scripts python -m uvicorn specy_road.gui_app:app --reload --port 8765` from the repo root; in another, `cd gui/pm-gantt && npm run dev` (Vite proxies `/api` to the Python server).

### Streamlit dashboard

From the **repository root**:

```bash
pip install "specy-road[gui]"
streamlit run scripts/roadmap_gui.py
```

Your terminal will show a local address (usually **[http://localhost:8501](http://localhost:8501)**). Open that link in **Chrome, Edge, or Safari**. Keep the terminal window open while you use the app; closing it stops the dashboard.

To stop the app: in the terminal, press **Ctrl+C**.

### What you see

- **Dependency view** — A picture of roadmap items as boxes arranged by **dependency depth** (what must finish before what). Lines show dependencies.
- **Colors** — Roughly: not started (gray), in progress (blue), complete (green), blocked (red), cancelled (muted). Exact shades may vary.
- **Registry** — When a developer has claimed work, you may see **branch names** or **timestamps** on the relevant item (from `roadmap/registry.yaml`). When they finish their task, that overlay usually clears after the next refresh.

### Pick an item

- **Click** a box on the chart, or use the **“Select node”** dropdown below it.  
- A **detail panel** shows title, status, dependencies, touch zones, checklist fields (when present), acceptance criteria, and risks.

### When the picture updates

- Use the sidebar **“Auto-refresh seconds”** slider. Set it above zero so the app checks for file changes on a timer (for example every 30 seconds).
- Saving roadmap files on disk (by you or by tooling) updates what the app reads on the next load or refresh.

### Change status from the dashboard

In the detail panel, choose a **status** from the dropdown and click **Save status**. The tool writes the roadmap **JSON** chunk file and runs validation — if something is invalid, you will see an error message instead of a silent failure.

### Optional: AI review of one item

**Run LLM review** asks an AI (OpenAI or Azure OpenAI) to comment on readiness — checklist gaps, unclear specs, risks. It is **advisory only**; it does not change files by itself.

Configure credentials in **Settings** (gear area in the sidebar) under the **LLM** tab, or set the same **environment variables** your team documents (see below). Use **Test LLM** before relying on it.

---

## Optional dashboard settings (sidebar → Settings)

Settings are stored on **your** computer only, not in the repo:

`~/.specy-road/gui-settings.json`  
(On Windows, that is under your user profile; the tool creates the folder if needed.)


| Tab            | What it is for                                                                                                                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **LLM**        | API keys and model for the optional reviewer (OpenAI, Azure OpenAI, or a compatible API). **Test LLM** checks the connection. **Save** stores values locally.                                                                  |
| **Git remote** | Optional. If you add a **GitHub** or **GitLab** token and repository name, the dashboard can try to show open **pull/merge requests** for branches that appear in the registry. If you skip this, you still see registry info. |


If your company already set **environment variables** for the CLI reviewer, those still work and usually override empty fields in the saved file.

**LLM environment variables (CLI and GUI):**

- **Azure OpenAI:** `SPECY_ROAD_AZURE_OPENAI_ENDPOINT`, `SPECY_ROAD_AZURE_OPENAI_API_KEY`, `SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT`, and optionally `SPECY_ROAD_OPENAI_API_VERSION` (default `2024-02-15-preview`).
- **OpenAI or compatible:** `SPECY_ROAD_OPENAI_API_KEY`, optional `SPECY_ROAD_OPENAI_BASE_URL`, optional `SPECY_ROAD_OPENAI_MODEL` (default `gpt-4o-mini`).

Do not commit API keys into the repository. Review any data-handling policy before sending content to an external model.

---

## Command line: when and what to run

Use the terminal in the **repo root**. The main program is `**specy-road`** followed by a **command**.

### Commands you will use most


| Command                                            | In plain English                                                                                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `specy-road sync`                                  | Download the latest from the team’s main branch (default), then validate and refresh the Markdown export. Use before a big editing session. |
| `specy-road validate`                              | Check that roadmap and registry files follow the rules. Run after edits if you want a quick sanity check.                                   |
| `specy-road export`                                | Regenerate `[roadmap.md](../roadmap.md)` from the merged graph — shareable index for stakeholders.                                            |
| `specy-road list-nodes`                            | Table of all items with type, status, title, and which file they live in.                                                                   |
| `specy-road show-node M0.1.1`                      | Print one item as JSON (replace `M0.1.1` with a real id).                                                                                   |
| `specy-road edit-node M0.1.1 --set status=Blocked` | Change allowed fields without hand-editing the chunk file. Validation runs after the save.                                                  |
| `specy-road add-node`                              | Add a new item; run `specy-road add-node -h` for options.                                                                                   |
| `specy-road archive-node M0.1.1`                   | Mark cancelled; add `--hard-remove` only when your team agrees to delete the row.                                                           |
| `specy-road brief M0.1.1`                          | Show the same “brief” a developer sees for that item (good for spot checks).                                                                |


**Global option:** `--repo-root DIR` (must come **before** the command) if the project is not the current folder.

Examples:

```bash
specy-road sync
specy-road list-nodes
specy-road show-node M0.1.1
specy-road edit-node M0.1.1 --set status=Complete
```

### Sync flags (detail)

```bash
specy-road sync
specy-road sync --no-git    # validate + export only, no git fetch/merge
```

Also: `--base <branch>`, `--remote <name>` if your integration branch or remote name is non-default.

### Optional: LLM review from the terminal

```bash
pip install "specy-road[review]"   # if you did not already install [gui]
specy-road review-node M0.1.1 -o work/review-M0.1.1.md
```

Same environment variables as in the dashboard LLM section.

---

## Your role in the system

Agentic development moves fast. Your job is **not** to approve every pull request — it is to **stay ahead** so developers and agents are never blocked waiting for a contract, decision, or node.

**Target horizon:** keep enough ready-to-execute `agentic` nodes ahead of the team. Rough rule: `(tasks per day per developer) × (number of developers)` nodes deep.


| You own                                        | You hand off entirely                  |
| ---------------------------------------------- | -------------------------------------- |
| Roadmap chunk authoring                        | Implementation                         |
| Human-led gate decisions (resolved in advance) | Branch, test, merge                    |
| Shared contracts under `shared/`               | CI failures                            |
| Maintaining the execution runway               | Registry housekeeping during execution |
| Stakeholder views via export                   | Code review                            |


---

## Runway maintenance (ongoing)

**Signs the runway is too short:**

- People wait on a contract or decision before starting a node
- `agentic` nodes missing `agentic_checklist` fields
- `human-gate` tasks not resolved before execution reaches them

**Suggested batch cadence:**

1. Check depth via `[roadmap.md](../roadmap.md)` or the dashboard.
2. Add or refine nodes in chunk files; fill all five `agentic_checklist` fields for agentic tasks.
3. Resolve `human-gate` items before you stop for the day.
4. `specy-road validate`, then `specy-road export`.
5. Commit with something like: `chore(roadmap): short description of change`

---

## Human-gate decisions

Resolve these **before** developers reach them:

1. Open the node with `execution_subtask: human-gate`.
2. Record the outcome in the node’s `decision` block and, if needed, an ADR under `docs/adr/` and updates under `shared/`.
3. Set the task status to `Complete`, then validate and export.

---

## Monitoring execution (not approving PRs)

- `**roadmap/registry.yaml`** — Who claimed what and which areas of the repo are “in use.” Stale entries may mean a blocked branch; check with the developer.
- `**specy-road validate**` — Warns about overlapping touch zones when multiple claims touch the same paths.
- `**specy-road export**` and `**roadmap.md**` — Stakeholder-friendly snapshot of status.

---

## Human-led vs agentic (short guide)


| Situation                           | Tag                          |
| ----------------------------------- | ---------------------------- |
| Write an ADR or feature spec        | `human`                      |
| Choose between architecture options | `human-gate` (resolve early) |
| Implement from a complete spec      | `agentic`                    |
| CI-verifiable generation            | `agentic`                    |


Set `execution_milestone` on the parent to the dominant mode (`Human-led`, `Agentic-led`, or `Mixed`). Full rules: [roadmap-authoring.md](roadmap-authoring.md#rules-for-authoring-sub-tasks).

---

## Writing implementable contracts

Before marking work ready, the `shared/` contract should answer: **what** is produced, **inputs/outputs**, **constraints**, and **success criteria**. If not, keep the task `Not Started` and note the gap under `risks`. See [Spec crosswalk](roadmap-authoring.md#spec-crosswalk).

---

## Quick reference (copy-paste)

```bash
specy-road sync
specy-road validate
specy-road export
specy-road list-nodes
specy-road show-node <NODE_ID>
specy-road edit-node <NODE_ID> --set status=Complete
specy-road brief <NODE_ID>
specy-road review-node <NODE_ID>   # needs LLM configured
```

```bash
streamlit run scripts/roadmap_gui.py
```

Deeper manifest and chunk rules: [roadmap-authoring.md](roadmap-authoring.md).