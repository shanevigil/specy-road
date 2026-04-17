# specy-road contributor guide

This guide is for **toolkit contributors** — people who hack on the
`specy-road` source itself. End users (consumers of the toolkit in their
own application repos) should read
[install-and-usage.md](install-and-usage.md) instead.

> The link from README to this guide will only be added **post-release**
> (per F-001 / F-002). Until then, open this file directly from the
> repository.

---

## Branching, tagging, and release process

### Default branch is `dev`

- All feature work targets **`dev`**.
- The **`main`** branch is reserved for tagged releases. The
  [`main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml)
  workflow rejects pushes to `main` that aren't annotated tags.
- `main` is intentionally minimal (README + the gate workflow) until v0.1.

### Feature branches

Use `feature/<short-slug>` off `dev` for changes that aren't a roadmap
node, and `feature/refine_<area>` for sweeping refactors.

For roadmap-driven work picked up via `specy-road do-next-available-task`,
the CLI creates `feature/rm-<codename>` automatically and registers the
claim on the integration branch first. See
[git-workflow.md](git-workflow.md) for the full ceremony (registry rows,
touch zones, PR vs merge, etc.).

### Tagging convention

Semver: `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`, `v0.2.0-rc1`). Tags are cut
from `dev` and merged to `main`. The `main-release-tag-gate.yml` workflow
verifies the tag matches `v\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?`.

### PR workflow

- Open PRs against `dev`. Drafts welcome.
- Keep PRs small and focused — one cluster of related findings or one
  feature.
- Squash on merge unless the commit history is meaningful (rare).
- Every PR should keep `pytest -q`, `specy-road validate`,
  `specy-road export --check`, and `specy-road file-limits` green
  against `tests/fixtures/specy_road_dogfood/`.

### Release process

1. Land all required PRs on `dev`.
2. Run the full local check (see *Local CI parity* below).
3. Cut a tag: `git tag -a v0.1.0 -m "v0.1.0"` from `dev`'s tip.
4. Merge `dev` into `main` (fast-forward) and push the tag.
5. **TODO (post-release):** automate PyPI build-and-publish on every
   tagged release. The README's top-of-file `TODO(post-release)` comment
   tracks this.

Until PyPI publish is automated, the canonical way to install is from
source on the `dev` branch (see [install-and-usage.md](install-and-usage.md)).

---

## Local CI parity

Run these from the toolkit repo root before pushing:

```bash
source .venv/bin/activate
pip install -e ".[dev,gui-next]"
pytest -q
specy-road validate    --repo-root tests/fixtures/specy_road_dogfood
specy-road export --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
```

For the PM Gantt SPA changes (under `gui/pm-gantt/`):

```bash
cd gui/pm-gantt
npm ci
npm run lint
npm test
npm run build
```

The CI workflow ([`.github/workflows/validate.yml`](../.github/workflows/validate.yml))
runs an extended pipeline including dependency audits and a PM bundle size
budget. Locally this is optional unless you changed dependencies or the SPA
bundle.

---

## PM Gantt UI: build and install

Architecture overview is in [pm-gui.md](pm-gui.md). For toolkit
contributors editing the React SPA:

```bash
# One-shot: install Python stack and rebuild the SPA
specy-road init gui --install-gui

# Just rebuild the SPA (no pip churn)
specy-road init gui --build-gui

# Or do it manually
cd gui/pm-gantt && npm ci && npm run build
```

The build writes assets into `specy_road/pm_gantt_static/`, which is
shipped inside the wheel. End users do not need npm.

For interactive frontend development with hot-reload, run the Vite dev
server from `gui/pm-gantt/` (port 5173) alongside a separate
`specy-road gui` Uvicorn process pointing at your sandbox repo.

---

## Updating an editable clone

```bash
specy-road update --install-gui-stack          # fast-forward + reinstall
specy-road update --dry-run --install-gui-stack
```

Use `--reset-to-origin` only when you intentionally want your tree to
match the server (it discards local commits and uncommitted changes; see
warning in `specy-road update --help`).

---

## Pre-commit hook

The repo ships with a `.pre-commit-config.yaml`. Install once per clone:

```bash
pip install pre-commit
pre-commit install
```

Hooks mirror CI minus `pytest` and supply-chain audits: roadmap validate,
markdown export drift, file line-count limits.

---

## IDE command stubs (`specyrd`)

`specyrd init` writes thin slash-command stubs into your IDE's command
directory so you can call `specy-road` from the command palette.

```bash
specyrd init . --ai cursor               # or --ai claude-code
specyrd init . --ai cursor --role dev    # validate, brief, claim, finish, …
specyrd init . --ai cursor --role pm     # validate, export, author, …
```

These are wrappers — the canonical behavior lives in `specy-road`, not
the stubs.

---

## Supply-chain & dependency audits

Full policy: [supply-chain-security.md](supply-chain-security.md).

Local audit (Python):

```bash
pip install -r requirements-ci.txt
pip install pip-audit
pip-audit -r requirements-ci.txt
```

The editable `specy-road` package will show as **skipped** when auditing
from a source checkout — that's expected (it's not on PyPI yet, see
F-001).

Local audit (npm, GUI):

```bash
cd gui/pm-gantt
npm ci
npm audit --omit=dev
```

Dependabot opens weekly PRs for pip, npm, and GitHub Actions; review
before merge.

---

## Trying `init project` safely

`specy-road init project` with no path uses the current git worktree
root. In **this** repository, that would scaffold consumer files next to
`pyproject.toml` — usually wrong. Use one of:

- `specy-road init project /tmp/specy-consumer-sandbox`
- The gitignored [`playground/`](../playground/README.md)

Then validate against that sandbox: `specy-road validate --repo-root /tmp/specy-consumer-sandbox`.

---

## Pointers to deeper docs

- [git-workflow.md](git-workflow.md) — branching, registry, touch zones,
  PR/MR ceremony, milestone rollups.
- [dev-workflow.md](dev-workflow.md) — the dev task loop in detail.
- [pm-workflow.md](pm-workflow.md) — PM-side workflow including the GUI.
- [pm-gui.md](pm-gui.md) — PM Gantt UI architecture.
- [roadmap-authoring.md](roadmap-authoring.md) — JSON chunk shape,
  manifest order, generated `roadmap.md`.
- [philosophy-and-scope.md](philosophy-and-scope.md) — what the toolkit
  promises and what it leaves to the consumer.
- [architecture.md](architecture.md) — code-level architecture for
  contributors.
- [supply-chain-security.md](supply-chain-security.md) — dependency
  policy.
