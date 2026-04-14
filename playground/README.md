# Playground (local only)

Use this directory as a **fake consumer project** while you work in the **specy-road** repository: run `init project` here so roadmap JSON, `AGENTS.md`, `planning/`, and the rest land under `playground/` instead of beside `pyproject.toml`.

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

`--repo-root` sets the GUI’s project root for that process (same as `SPECY_ROAD_REPO_ROOT`); it overrides repo discovery from the current directory, so you can keep your shell at the toolkit root.

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
```
