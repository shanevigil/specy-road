# Install and use specy-road

This is the **end-user** install and everyday usage guide. For toolkit-
contributor topics (branching, tagging, PR workflow, release gating, npm
build, supply-chain audits) see [contributor-guide.md](contributor-guide.md).

---

## Requirements

- **Python 3.11+**
- **git** with a configured remote (default: `origin`). specy-road requires
  git for sync, registry, and the do-next pickup loop. There is no offline
  / `--no-git` mode. For purely-local trials, point `origin` at a local
  bare repo (`git init --bare /tmp/<slug>.git`).
- **Node.js / npm** is **not** required to use the PM Gantt UI from a pip
  install — built static assets ship inside the wheel. npm is only needed
  to rebuild the SPA (toolkit contributors).

---

## Install

For application teams, install the published package from PyPI:

```bash
pip install specy-road
```

Optional extras:

```bash
pip install "specy-road[gui-next]"  # PM Gantt UI deps
pip install "specy-road[review]"    # LLM review (`specy-road review-node`)
```

## Install from source (toolkit contributors)

```bash
git clone https://github.com/shanevigil/specy-road.git
cd specy-road
git switch dev               # main is reserved for tagged releases
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui-next]"
# Optional extras:
#   - 'review'   : enables `specy-road review-node` (requires LLM API key)
```

You get two CLI commands:

- **`specy-road`** — validate, brief, export, init project, do-next loop, GUI.
- **`specyrd`** — optional IDE slash-command stubs (Cursor / Claude Code).

Verify the CLI from a source checkout. The `--repo-root` path below is this repository's dogfood test fixture; consumer projects validate their own initialized repo root instead.

```bash
specy-road --help
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
```

---

## Initialize a new consumer project

From your application repository root (or pass a path):

```bash
specy-road init project
# Edit roadmap/git-workflow.yaml so integration_branch and remote match
# your team's trunk (e.g. integration_branch: dev, remote: origin).
specy-road validate
specy-road export
```

`init project` writes `.gitignore`, `roadmap/`, `planning/`, `constitution/`,
`constraints/`, `shared/`, `schemas/`, `work/`, `vision.md`, and `AGENTS.md`.
It refuses to overwrite an existing scaffold unless you pass `--force`.
Preview without writing: `--dry-run`.

The bundled `.gitignore` ignores **only** the session-scoped files
(`work/.on-complete-*.yaml`, `work/prompt-*.md`,
`work/.milestone-session.yaml`); briefs and implementation summaries are
intentionally tracked because they document the work and belong on the
feature branch.

---

## Everyday workflow (PM)

```bash
# Author the roadmap (or edit JSON chunks under roadmap/ directly)
specy-road add-node --chunk phases/M1.json --id M1.2.1 --type task \
    --title "Add login form" --parent-id M1.2
# (codename auto-derives from --title if omitted)

# Validate (auto-heals: derives missing codenames, strips deprecated fields)
specy-road validate

# Refresh the human-readable index
specy-road export

# Optionally edit fields
specy-road edit-node M1.2.1 --set status=Complete

# Inspect the roadmap from the CLI
specy-road list-nodes
specy-road show-node M1.2.1

# Sync your local integration branch with origin
specy-road sync
```

Run all of these with `--repo-root /path/to/consumer/repo` if your shell is
not already inside the consumer repo (for example when you're working in
the toolkit clone and pointing at `playground/`).

---

## Everyday workflow (DEV / coding agent)

```bash
# Pick the next actionable leaf, sync integration, register the claim,
# create feature/rm-<codename>, write a self-contained brief + agent prompt.
specy-road do-next-available-task

# Implement the task on feature/rm-<codename>, then write the summary:
$EDITOR work/implementation-summary-<NODE_ID>.md

# Human review of the summary — gate before finish:
specy-road mark-implementation-reviewed

# Land the work. on_complete=pr opens a PR; on_complete=merge merges
# locally and pushes the integration branch (no PR needed).
specy-road finish-this-task --on-complete merge
```

When `--on-complete pr` (or `auto`) is used, `finish-this-task` also
writes a snapshot **PR body** to `work/pr-body-<NODE_ID>.md` containing
your implementation summary (visible up top) and the original
work-packet brief (in a collapsible `<details>` block) — see F-015. The
printed `gh pr create` / `glab mr create` command already references
the file via `--body-file` / `--description-file`, so reviewers see
both narratives without leaving the PR view. The snapshot does **not**
update if the roadmap evolves later; that's the point.

When something goes wrong mid-pickup, specy-road auto-rolls-back the stale
registry claim (F-014). If the auto-rollback itself fails, follow the
printed instructions or run `specy-road abort-task-pickup --force`.

---

## Everyday workflow (GUI)

The PM Gantt UI is a FastAPI server that serves a prebuilt React SPA.

```bash
specy-road gui --repo-root /path/to/consumer/repo
# Open the URL it prints (default http://127.0.0.1:8765/).
```

If you need to rebuild the SPA from source (toolkit contributors only),
follow the instructions in [contributor-guide.md](contributor-guide.md).
For end users, the wheel ships built assets and `specy-road gui` works out
of the box.

The UI surface and PM-facing usage details are in
[pm-workflow.md](pm-workflow.md) and [pm-gui.md](pm-gui.md). This document
covers only what's needed to install and start it.

---

## Brief generation

`specy-road brief <NODE_ID>` produces a comprehensive **work-packet brief**
(F-004): node metadata, ancestor context chain, every relevant planning
sheet inlined, every shared contract inlined, dependency list, and a
touch-zone discovery instruction for the implementing agent. Output is
deterministic — same inputs → same bytes.

```bash
specy-road brief M1.2.1                                # to stdout
specy-road brief M1.2.1 -o work/brief-M1.2.1.md        # to a file
```

`do-next-available-task` writes the brief automatically; you usually only
run `brief` directly when re-generating one or piping into another tool.

---

## Optional dependency audit (consumer projects)

Toolkit contributors should follow [contributor-guide.md](contributor-guide.md)
and [supply-chain-security.md](supply-chain-security.md) for the full
policy. Consumers wanting a one-off audit of their own clone can run:

```bash
pip install pip-audit
pip-audit
```

---

## Contributing & release process

A full contributor guide (branching, tagging, PR workflow, release gating,
PyPI publish) lives in **[contributor-guide.md](contributor-guide.md)**.
The README will link to it directly **post-release**; until then, open the
file from a clone of this repository.

Headlines:

- **Default development branch:** `dev`. The `main` branch is reserved
  for tagged releases (the `main-release-tag-gate.yml` workflow enforces
  this).
- **Branching:** feature work goes on `feature/<thing>` branches off `dev`.
- **Tagging:** semver `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`). Tags are cut
  from `dev` and merged to `main`.
- **PRs:** small and focused; drafts welcome; squash on merge.
- **Release:** PyPI publish will be automated on every tag (TODO; tracked
  in the README's top-of-file comment).
