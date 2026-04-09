# Setup: installing specy-road for development

This guide covers first-time installation, the pre-commit hook, and optional IDE
command stubs. Once set up, see [dev-workflow.md](dev-workflow.md) for the day-to-day
task loop.

---

## Requirements

- Python 3.11+
- Git

---

## Install the package

From the repo root:

```bash
pip install -e ".[dev]"
```

This installs two CLI commands:

- `specy-road` — roadmap validation, briefs, export, and the dev task loop
- `specyrd` — optional IDE stub installer (see below)

Verify:

```bash
specy-road --help
```

---

## Install the pre-commit hook

Hooks mirror CI (without `pytest`): roadmap validation, markdown export drift check, and file line-count limits. Install once per clone:

```bash
pip install pre-commit
pre-commit install
```

If a commit fails validation, read the error output — it names the offending node ID,
field, or file. Do not bypass the hook with `--no-verify`.

---

## Optional: IDE command stubs (`specyrd`)

`specyrd init` writes thin slash-command stubs into your IDE's command directory so
you can invoke `specy-road` commands from the IDE command palette.

```bash
# For Claude Code
specyrd init . --ai claude-code

# For Cursor
specyrd init . --ai cursor

# Filter to role-relevant stubs only (omit --role for all command stubs)
specyrd init . --ai claude-code --role dev   # validate, brief, claim, finish, do-next-task
specyrd init . --ai claude-code --role pm    # validate, export, author, sync, list-nodes, …
specyrd init . --ai claude-code --role both  # same thirteen stubs as omitting --role
```

Default install writes **thirteen** `specyrd-*.md` files (including `sync`, `list-nodes`, `show-node`, `add-node`, `review-node`). Stubs are written to `.claude/commands/` or `.cursor/commands/` (or a custom path for `--ai generic`). They are thin
wrappers — the canonical behaviour lives in `specy-road` and `scripts/`, not the stubs.

Use `--dry-run` to preview what would be written, `--force` to overwrite existing stubs.

Additional flags:

- **`--extras`** — comma-separated optional installs: `review`, `gui` (runs `pip install specy-road[...]` after writing stubs, skipped when modules are already importable).
- **`--no-prompt`** — non-interactive: no stdin questions; **requires `--role`** (`pm`, `dev`, or `both`).
- **`--ai claude-code`** — if `CLAUDE.md` is missing at the repo root, it is created from the packaged template (skipped when the file exists unless `--force`).

When `gui` is included in `--extras`, a starter `~/.specy-road/gui-settings.json` is created if missing.

---

## Optional: PM roadmap GUI (Streamlit)

Install the GUI extra, then run from the repository root:

```bash
pip install "specy-road[gui]"
streamlit run scripts/roadmap_gui.py
```

The app shows a dependency-depth view of the roadmap, reads `roadmap/registry.yaml`, and can save LLM / git-remote settings under `~/.specy-road/gui-settings.json`. See `docs/pm-workflow.md` for LLM review environment variables (the GUI can inject the same names from saved settings).

## Optional: Gantt PM GUI (FastAPI + React)

For the split-pane outline and Gantt timeline, PMs install dependencies with **`specy-road init --install-gui`** (or `pip install 'specy-road[gui-next]'`), then **`specy-road gui`** from the project repo root — no `npm` required. See [pm-workflow.md](pm-workflow.md).

Contributors who edit the React app rebuild from `gui/pm-gantt` so `specy_road/pm_gantt_static/` stays current.

---

## CI

GitHub Actions runs the full validation suite on every push and PR to `main`/`dev`:

```
validate roadmap → export check → file limits → pytest
```

The workflow file is at [`.github/workflows/validate.yml`](../.github/workflows/validate.yml).
No additional setup is needed — it installs dependencies and runs the same commands
available locally.
