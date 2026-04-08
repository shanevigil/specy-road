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
```

Default install writes **thirteen** `specyrd-*.md` files (including `sync`, `list-nodes`, `show-node`, `add-node`, `review-node`). Stubs are written to `.claude/commands/` or `.cursor/commands/` (or a custom path for `--ai generic`). They are thin
wrappers — the canonical behaviour lives in `specy-road` and `scripts/`, not the stubs.

Use `--dry-run` to preview what would be written, `--force` to overwrite existing stubs.

---

## CI

GitHub Actions runs the full validation suite on every push and PR to `main`/`dev`:

```
validate roadmap → export check → file limits → pytest
```

The workflow file is at [`.github/workflows/validate.yml`](../.github/workflows/validate.yml).
No additional setup is needed — it installs dependencies and runs the same commands
available locally.
