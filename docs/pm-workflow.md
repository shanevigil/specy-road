# PM workflow: roadmap, dashboard, and day-to-day use

This guide is for **product managers, program leads, and tech leads** who shape what gets built and in what order. You do not need to be a developer; you need a copy of the project on your machine and a way to run a few commands (or use the visual dashboard).

Developers follow [dev-workflow.md](dev-workflow.md). First-time machine setup (Python, git clone, optional IDE stubs) is in [setup.md](setup.md).

---

## What you are working with

- The **roadmap** is a set of structured files in the repo under `roadmap/`. They describe milestones, tasks, dependencies, and status (**JSON chunk files** listed in `manifest.json`, plus `registry.yaml` for active claims).
- **Git** is how the team shares changes. You pull updates before you edit, and you commit when you save roadmap changes.
- You can work in two ways: a **visual dashboard** in the browser (recommended if you prefer clicking to typing), or the **command line** (`specy-road` …) for quick edits and scripts.

There is no “import from Word” flow: the source of truth is the **chunk files** under `roadmap/` and the manifest order in `manifest.json`. Root `roadmap.md` (in your project) is a **generated index** — refresh it with `specy-road export` or `specy-road sync`.

### Establish the constitution (purpose and principles)

[Spec-Kit](https://github.com/github/spec-kit) popularized an early **constitution** step for spec discipline. In specy-road, that maps to **two Markdown files** in the repo (not the roadmap graph): [`constitution/purpose.md`](../specy_road/templates/project/constitution/purpose.md) (**why** the effort exists) and [`constitution/principles.md`](../specy_road/templates/project/constitution/principles.md) (**how** you decide). They are **human judgment** — not machine-validated like the merged roadmap. Enforceable caps live under `constraints/`; the execution **graph** lives under `roadmap/` JSON, and **feature sheets** (flat `planning/*.md` per node with `planning_dir`) live under [`planning/`](../specy_road/templates/project/planning/README.md). See [philosophy-and-scope.md](philosophy-and-scope.md) and [`AGENTS.md`](../AGENTS.md) (consumer projects use the file from `init project`; this repository’s [`AGENTS.md`](../AGENTS.md) is for toolkit contributors).

**When:** Early when adopting the kit (before or alongside first roadmap authoring) so people and agents share the same north star.

**Via CLI** (from the repository root):

```bash
specy-road scaffold-constitution
```

Creates starter files if they are missing. Existing files are left unchanged unless you pass **`--force`** (overwrites both). Use **`specy-road scaffold-constitution --repo-root /path/to/repo`** when the project is not the current directory. This does not replace `specy-road validate` for roadmap data; it only lays down prose templates.

**Via Gantt PM UI:** After `specy-road gui`, open **Constitution** in the toolbar. You can edit both files and **Save both**, or use **Create starter files** if either file is missing (same behavior as the CLI scaffold).

**Via IDE (optional):** Run `specyrd init …` so your editor gets slash-command stubs; the PM-oriented set includes **`specyrd-constitution`**, which points at `specy-road scaffold-constitution` and this doc. **specyrd** is not [Spec Kit](https://github.com/github/spec-kit)’s `specify` CLI — canonical artifacts remain these paths plus the roadmap/registry model ([README.md](../README.md)).

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
3. A **terminal** open **in that folder** (the project root — where you see `roadmap/`, `AGENTS.md`, and your app sources).

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

**Gantt PM UI (recommended for most PMs):** after `pip install specy-road`, run once from the **repository root**:

```bash
specy-road init gui --install-gui
specy-road gui
```

`--install-gui` sets up the FastAPI/uvicorn dependencies **and**, when `gui/pm-gantt/` is present (typical git clone), builds the SPA so the UI matches the tree. You do not need a second `--build-gui` flag. Safe to repeat when you pull updates.

If the Python stack is corrupted, use **`specy-road init gui --reinstall-gui`**. To upgrade Python deps **without** running npm (faster), use **`specy-road init gui --install-gui --skip-npm-build`**. To **only** rebuild the frontend, **`specy-road init gui --build-gui`** (requires Node.js).

For a full developer install (tests, editable package), see [setup.md](setup.md).

---

## Open and use the roadmap dashboard

Use the **Gantt PM UI** (split outline + dependency timeline, drag-drop sibling reorder, double-click planning editor and markdown workspace).

### Gantt PM UI (FastAPI + React)

**Working directory:** run `specy-road gui` from your **project repository root** (the folder that contains `roadmap/`). The UI discovers that root the same way as other CLI commands (git worktree from the current directory, or the current directory if not in git). If that resolves to the wrong tree—nested checkouts, monorepos—pass `--repo-root /path/to/repo` or set `SPECY_ROAD_REPO_ROOT`.

**One-time setup:** the wheel ships a built UI; from a **clone** with `gui/pm-gantt/`, `init gui --install-gui` also compiles that tree. After `pip install specy-road`:

```bash
specy-road init gui --install-gui
```

Run the same command later to **upgrade** the stack when you update the package. Without Node on `PATH`, npm is skipped and the packaged UI is still used. Use **`specy-road init gui --reinstall-gui`** if the environment looks corrupted. Equivalent manual install: `pip install --upgrade 'specy-road[gui-next]'`.

**Every session:**

```bash
specy-road gui
```

The terminal prints the URL (default **[http://127.0.0.1:8765](http://127.0.0.1:8765)**). Options: `specy-road gui --help` for `--host`, `--port`, and `--repo-root`. If **address already in use** on port 8765, stop the other process or run `specy-road gui --port 8766` and open that port in the browser.

**Contributors / UI development** (git clone, hot reload): install extras from the clone (`pip install -e ".[gui-next]"`), rebuild the Vite app when you change React code (`cd gui/pm-gantt && npm install && npm run build` — output goes to `specy_road/pm_gantt_static/`). For local dev with reload: in one terminal, `PYTHONPATH=scripts python -m uvicorn specy_road.gui_app:app --reload --port 8765` from the repo root; in another, `cd gui/pm-gantt && npm run dev` (Vite proxies `/api` to the Python server).

### What you see

- **Dependency view** — A picture of roadmap items as boxes arranged by **dependency depth** (what must finish before what). Lines show dependencies.
- **Colors** — Roughly: not started (gray), in progress (blue), complete (green), blocked (red), cancelled (muted). Exact shades may vary.
- **Registry** — When a developer has claimed work, you may see **branch names** or **timestamps** on the relevant item (from `roadmap/registry.yaml`). When they finish their task, that overlay usually clears after the next refresh.
- **Dev column** — Shows **who** is associated with the work when the server can resolve it: explicit **`owner`** in the registry row; else **PR/MR author** from GitHub/GitLab when configured; else the **last commit author** on the **remote-tracking** branch (`refs/remotes/<remote>/<registered-branch>`) after `git fetch`; else **local `git config user.name`** only when your **current branch** matches that row’s registered branch (typical for **developers** on `feature/rm-*`, not for **PMs** who stay on the integration branch). See [design-notes/pm-gantt-registry-checkout.md](design-notes/pm-gantt-registry-checkout.md).
- **Git workflow status** — Next to the **settings** (gear) icon, a **read-only label** shows trunk/remote and current branch when healthy (**green**). **Red** means missing or invalid `roadmap/git-workflow.yaml`. **Yellow** means the folder is not a git clone, or the integration branch ref is not present locally yet (hover the label for details: edit the YAML, run `git fetch`, or set `SPECY_ROAD_REPO_ROOT` if the GUI resolved the wrong tree). When your **current branch** matches a task’s registered feature branch **in the `roadmap/registry.yaml` present in this checkout**, that outline row gets a **green left accent** (hover the row for the exact rule).

### Monitoring in-progress work while on the integration branch

The PM Gantt loads **`roadmap/registry.yaml` from the working tree** used by the server (the repo root from your cwd, or `SPECY_ROAD_REPO_ROOT` / `--repo-root`). Developers typically add their first registry row on **`feature/rm-<codename>`** only; until that commit merges, your **integration branch** checkout often still has **`entries: []`** even while work is progressing on the feature branch.

- **Remote registry overlay (optional):** in **Settings**, enable **“Merge registry from remote feature branches”** so **`GET /api/roadmap`** merges `roadmap/registry.yaml` blobs from **`git show refs/remotes/<remote>/feature/rm-*:<path>`** (after **`git fetch`**) into the payload. HEAD entries win on the same **`node_id`**; remote rows fill gaps. See [design-notes/registry-hydration-remote-refs.md](design-notes/registry-hydration-remote-refs.md).
- The outline **green left accent** compares **`git branch --show-current`** to each row’s registered **`branch`** field in **that** `registry.yaml`. It does **not** follow registrations that exist only on another branch or in another clone.
- Without overlay: to see registry-driven rows and the green accent for in-flight work, **check out the feature branch**, add a **second git worktree** checked out to that branch, or run the GUI against a clone where that branch is **HEAD**. Run **`git fetch`** so `refs/remotes/<remote>/feature/rm-*` refs exist locally.

If you stay on the integration branch with an empty local registry while remote-tracking feature branches exist, the UI may show a short **dismissible notice** explaining this. To disable the extra payload fields, set **`SPECY_ROAD_GUI_REGISTRY_VISIBILITY=0`** for the GUI process.

See [git-workflow.md](git-workflow.md) and [design-notes/pm-gantt-registry-checkout.md](design-notes/pm-gantt-registry-checkout.md).

### Pick an item

- **Click** a box on the chart, or use the **“Select node”** dropdown below it.  
- A **detail panel** shows title, status, dependencies, touch zones, checklist fields (when present), acceptance criteria, and risks.

### When the picture updates

- Use the sidebar **“Auto-refresh seconds”** slider. Set it above zero so the app checks for file changes on a timer (for example every 30 seconds).
- Saving roadmap files on disk (by you or by tooling) updates what the app reads on the next load or refresh.

### Change status from the dashboard

In the detail panel, choose a **status** from the dropdown and click **Save status**. The tool writes the roadmap **JSON** chunk file and runs validation — if something is invalid, you will see an error message instead of a silent failure.

### Optional: AI review of one item

**Run LLM review** asks an AI (OpenAI, Azure OpenAI, Anthropic Claude, or an OpenAI-compatible endpoint) to comment on readiness — checklist gaps, unclear specs, risks. It is **advisory only**; it does not change files by itself.

Configure credentials in **Settings** (gear area in the sidebar) under the **LLM** tab, or set the same **environment variables** your team documents (see below). Use **Test LLM** before relying on it.

---

## Optional dashboard settings (sidebar → Settings)

Settings are stored on **your** computer only, not in the repo:

`~/.specy-road/gui-settings.json`  
(On Windows, that is under your user profile; the tool creates the folder if needed.)

The file is a **versioned** JSON document: **global** defaults (shared across repositories unless you override) plus optional **per–git-worktree** overlays keyed by a hash of the repository root path. Older installs used a flat file with only top-level `llm` and `git_remote`; that shape is **migrated automatically** on first read into `version` 2 with a `global` section and an empty `projects` map.

In **Settings**, use **This repository** toggles:

- **Use global LLM settings for this repository** — when on, LLM fields you edit are saved as **global** defaults. When off, only fields that differ from those defaults are stored for **this** checkout (so you can use one API key everywhere, or a different key per project).
- **Use global Git remote settings for this repository** — same idea for GitHub/GitLab **repo** name, token, and related fields (useful when each codebase has its own remote but you share one token).

| Tab            | What it is for                                                                                                                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **LLM**        | API keys and model for the optional reviewer (OpenAI, Azure OpenAI, Anthropic Claude, or a compatible OpenAI-style API). **Test LLM** checks the connection. Changes save automatically with simple obfuscation (not encryption).                                                                  |
| **Git remote** | Optional. If you add a **GitHub** or **GitLab** token and repository name, the dashboard can try to show open **pull/merge requests** for branches that appear in the registry. If you skip this, you still see registry info. |

**Security note (saved secrets):** Values you save for LLM keys and the Git remote token are written to `gui-settings.json` with Base64 encoding (a `__b64__:` prefix) so they are not stored as raw plaintext in the file. That is **obfuscation, not encryption**: anyone who can read the file—local users with access to your home directory, backups, folder sync, or compromised tooling on the same machine—can recover the secret. Treat the file like a credential; prefer **environment variables** or org-approved secret storage if your policy needs stronger guarantees (pre-set env vars still override empty saved fields).

If your company already set **environment variables** for the CLI reviewer, those still work and usually override empty fields in the saved file.

**LLM environment variables (CLI and GUI):**

- **Azure OpenAI:** `SPECY_ROAD_AZURE_OPENAI_ENDPOINT`, `SPECY_ROAD_AZURE_OPENAI_API_KEY`, `SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT`, and optionally `SPECY_ROAD_OPENAI_API_VERSION` (default `2024-02-15-preview`).
- **OpenAI or compatible:** `SPECY_ROAD_OPENAI_API_KEY`, optional `SPECY_ROAD_OPENAI_BASE_URL`, optional `SPECY_ROAD_OPENAI_MODEL` (default `gpt-4o-mini`). Use a compatible **base URL** for OpenAI-shaped proxies (for example OpenRouter or a gateway); for Anthropic’s direct API, use the **Anthropic** backend below instead.
- **Anthropic (Claude):** `SPECY_ROAD_ANTHROPIC_API_KEY`, optional `SPECY_ROAD_ANTHROPIC_MODEL` (default in the reviewer is `claude-sonnet-4-20250514` when unset).

Do not commit API keys into the repository. Review any data-handling policy before sending content to an external model.

---

## Command line: when and what to run

Use the terminal in the **repo root**. The main program is `**specy-road`** followed by a **command**.

### Commands you will use most


| Command                                            | In plain English                                                                                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `specy-road sync`                                  | Fast-forward your integration branch from the remote (defaults from `roadmap/git-workflow.yaml`, else `main`/`origin`), then validate and refresh the Markdown export. Use before a big editing session. |
| `specy-road scaffold-constitution`                 | Create starter `constitution/purpose.md` and `constitution/principles.md` if missing (`--force` overwrites).                               |
| `specy-road validate`                              | Check that roadmap and registry files follow the rules. Run after edits if you want a quick sanity check.                                   |
| `specy-road export`                                | Regenerate `roadmap.md` from the merged graph — shareable index for stakeholders.                                            |
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

1. Check depth via `roadmap.md` or the dashboard.
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
specy-road scaffold-constitution   # starter purpose.md + principles.md if missing
specy-road list-nodes
specy-road show-node <NODE_ID>
specy-road edit-node <NODE_ID> --set status=Complete
specy-road brief <NODE_ID>
specy-road review-node <NODE_ID>   # needs LLM configured
specy-road gui                       # PM Gantt (FastAPI + React)
```

Deeper manifest and chunk rules: [roadmap-authoring.md](roadmap-authoring.md).