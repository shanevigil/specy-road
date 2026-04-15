# Playground (local only)

Use this directory as a **fake consumer project** while you work in the **specy-road** repository: run `init project` here so the full bundled layout (roadmap JSON, `AGENTS.md`, `constitution/`, `constraints/`, `planning/`, `shared/`, `docs/supply-chain-security.md`, `work/`, …) lands under `playground/` instead of beside `pyproject.toml`. That matches what [`specy-road init project`](../README.md#new-project-consumer) writes for a real app repo.

**Maintainers:** automated validation and export checks in this repository use the dogfood tree [`tests/fixtures/specy_road_dogfood/`](../tests/fixtures/specy_road_dogfood/) (see root [`AGENTS.md`](../AGENTS.md)). **Playground** is for interactive trials of the **consumer** scaffold and the PM GUI, not the canonical toolkit roadmap.

**Git:** Everything under `playground/` is ignored except this file and [`.gitkeep`](.gitkeep). Scaffold output, briefs, and exports stay local. Remove contents when finished, or delete the whole folder; nothing here ships with the package.

---

## One-time setup

From the **toolkit repository root** (the directory that contains `pyproject.toml` and `specy_road/`):

```bash
# Editable install (typical for maintainers)
pip install -e ".[dev]"
```

Create or refresh the consumer layout:

```bash
specy-road init project playground
```

To **overwrite** an existing scaffold (for example after template changes), use:

```bash
specy-road init project playground --force
```

Preview without writing:

```bash
specy-road init project playground --dry-run
```

After the scaffold exists, set **`roadmap/git-workflow.yaml`** (integration branch and remote) so `specy-road sync`, registry flows, and the PM Gantt agree with your repository. See [`docs/git-workflow.md`](../docs/git-workflow.md).

---

## PM CLI: always pass `--repo-root`

Your shell can stay at the toolkit root; the CLI must know which tree to load. Use **`--repo-root playground`** (or an absolute path) for anything that reads `roadmap/`, `planning/`, or `shared/`:

```bash
specy-road validate --repo-root playground
specy-road export --repo-root playground
specy-road export --check --repo-root playground
specy-road brief M1.1 -o playground/work/brief-M1.1.md --repo-root playground
```

Add other subcommands the same way (`sync`, `scaffold-planning`, registry-aware flows, etc.). If you omit `--repo-root`, the default is the **git worktree root** (the specy-road clone), which is usually wrong for this workflow.

---

## PM GUI (Gantt UI)

Install or upgrade the FastAPI stack and optional frontend build **once** from the toolkit root (so `gui/pm-gantt/` is picked up when present):

```bash
specy-road init gui --install-gui
```

Run the server against the playground tree:

```bash
specy-road gui --repo-root playground
```

Open the Gantt UI at the URL printed on startup (by default **`http://127.0.0.1:8765/`**). Use **`--host`** and **`--port`** on `specy-road gui` if you need a different bind address.

`--repo-root` sets the GUI’s project root for that process (same as `SPECY_ROAD_REPO_ROOT`); it overrides repo discovery from the current directory, so you can keep your shell at the toolkit root.

**Settings sanity check:** In the GUI sidebar → **Settings**, confirm **Open repository:** points at your **`…/playground`** path (not only the parent specy-road clone). File-backed credentials (LLM, Git remote) and browser-only chart options are both scoped to that resolved path; if the path is wrong, restart with `specy-road gui --repo-root playground` (see [docs/pm-workflow.md](../docs/pm-workflow.md) for global vs per-repo inheritance).

After you **pull** changes to this clone, you can refresh the editable install and GUI build with **`specy-road update --install-gui-stack`** (same idea as `init gui --install-gui`; see "Update an editable clone" in [`docs/setup.md`](../docs/setup.md)).

After you change sources under **`gui/pm-gantt/`**, rebuild bundled assets, then restart the GUI:

```bash
specy-road init gui --build-gui
specy-road gui --repo-root playground
```

---

## Quick sanity check

```bash
specy-road validate --repo-root playground
specy-road export --check --repo-root playground
specy-road file-limits --repo-root playground
```
