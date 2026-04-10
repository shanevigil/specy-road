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
specyrd init . --ai claude-code --role pm    # validate, export, author, constitution, sync, list-nodes, …
specyrd init . --ai claude-code --role both  # same fourteen stubs as omitting --role
```

Default install writes **fourteen** `specyrd-*.md` files (including `constitution`, `sync`, `list-nodes`, `show-node`, `add-node`, `review-node`). Stubs are written to `.claude/commands/` or `.cursor/commands/` (or a custom path for `--ai generic`). They are thin
wrappers — the canonical behaviour lives in `specy-road` and `scripts/`, not the stubs.

Use `--dry-run` to preview what would be written, `--force` to overwrite existing stubs.

Additional flags:

- **`--extras`** — comma-separated optional installs: `review`, `gui` (runs `pip install specy-road[...]` after writing stubs, skipped when modules are already importable).
- **`--no-prompt`** — non-interactive: no stdin questions; **requires `--role`** (`pm`, `dev`, or `both`).
- **`--ai claude-code`** — if `CLAUDE.md` is missing at the repo root, it is created from the packaged template (skipped when the file exists unless `--force`).

When `gui` is included in `--extras`, a starter `~/.specy-road/gui-settings.json` is created if missing.

---

## Optional: Gantt PM GUI (FastAPI + React)

For the split-pane outline and Gantt timeline, use one command from the repo root:

```bash
specy-road init --install-gui
```

That **installs or upgrades** the Python stack (`pip install --upgrade …[gui-next]`). If this tree contains **`gui/pm-gantt/`** (a git checkout), it **also** runs `npm ci` / `npm install` and `npm run build` so the bundled static UI matches the repo — then **`specy-road gui`** works without extra steps. If you only have a PyPI install (no `gui/pm-gantt/`), pip is enough; the wheel already includes built assets.

Use **`specy-road init --reinstall-gui`** when the Python env looks broken (adds `pip --force-reinstall`). Use **`specy-road init --install-gui --skip-npm-build`** when you only want faster pip upgrades and will not change the frontend. Use **`specy-road init --build-gui`** alone to rebuild the SPA without touching pip.

Equivalent manual installs: `pip install --upgrade 'specy-road[gui-next]'` and, from `gui/pm-gantt`, `npm install && npm run build`. See [pm-workflow.md](pm-workflow.md).

The init npm step does **not** start the Vite dev server (port 5173). A first `npm install` can take several minutes. The CLI skips npm’s automatic audit and runs non-interactively.

---

## CI

GitHub Actions runs the full validation suite on every push and PR to `main`/`dev`:

```
validate roadmap → export check → file limits → pytest
```

The workflow file is at [`.github/workflows/validate.yml`](../.github/workflows/validate.yml).
No additional setup is needed — it installs dependencies and runs the same commands
available locally.
