# specy-road contributor guide

This guide is for **toolkit contributors** — people who hack on the
`specy-road` source itself. End users (consumers of the toolkit in their
own application repos) should read
[install-and-usage.md](install-and-usage.md) instead.

> The link from README to this guide will only be added **post-release**
> (per F-001 / F-002). Until then, open this file directly from the
> repository.

---

## Project stewardship

`specy-road` is maintained by [@shanevigil](https://github.com/shanevigil).
The maintainer reserves the **right of refusal**: any PR may be closed
for any reason, with or without explanation. Out-of-scope changes,
contested architecture, undisclosed conflicts of interest, or low-effort
contributions are all valid grounds for closure. Don't take it
personally; it's a small project and direction matters.

### Issues come first

Before opening a non-trivial PR, **open or reference an existing
issue**. The PR body must include a closing-keyword link:

```
Closes #123
Fixes #45
Refs #67
```

This is enforced by [`pr-conventions.yml`](../.github/workflows/pr-conventions.yml).
Two exemptions exist:

1. **`chore/<...>` branches** — housekeeping (typo fixes, lint cleanup,
   doc tidying, dependency bumps) does not require an issue.
2. **The `no-issue-required` label** — applied at the maintainer's
   discretion when a contribution warrants an exception (e.g. emergency
   security fix).

### Malicious code policy

specy-road is a coordination tool that runs on contributor laptops and
in CI environments. Any pull request found to contain **malicious code**
— including but not limited to: cryptominers, data-exfiltration shims,
backdoor commits, supply-chain attacks (typosquatting in
`requirements-ci.txt` or `package-lock.json`, lockfile substitution,
post-install hooks that fetch arbitrary code, tampering with the
trusted-publisher config, attempts to weaken the validate / file-limits
/ audit pipeline) — will result in:

1. Immediate closure of the PR.
2. Permanent ban of the contributor from this repository.
3. **Reporting** to GitHub Trust & Safety
   (`https://github.com/contact/report-abuse`) and, where applicable,
   to PyPI (security@pypi.org), npm (security@npmjs.com), CISA, and
   any downstream consumer the maintainer can identify.
4. Public audit-trail preservation — the offending commits and PR
   metadata remain available so other maintainers can recognize the
   pattern.

By submitting a PR you accept this policy. If you spot suspicious
activity in someone else's PR, please report it privately to the
maintainer rather than commenting publicly on the PR thread.

---

## Branching, tagging, and release process

### Default branch is `dev`

- All feature work targets **`dev`**.
- The **`main`** branch is reserved for tagged releases. The
  [`main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml)
  workflow rejects pushes to `main` that aren't release-marker PRs and
  auto-tags merge commits.
- `main` is intentionally minimal (README + workflows) until v0.1.

### Branch-naming convention (enforced)

Branch names **must** match one of these prefixes followed by a kebab-case
description:

```
feature/<kebab-description>     # new functionality
fix/<kebab-description>          # bug fix
chore/<kebab-description>        # housekeeping (no issue link required)
```

The regex enforced by
[`pr-conventions.yml`](../.github/workflows/pr-conventions.yml) is:

```
^(feature|fix|chore)/[a-z0-9]+(-[a-z0-9]+)*$
```

CI-managed branches (`cursor/...`, `dependabot/...`, `ci/...`) are
exempt. Roadmap-driven `feature/rm-<codename>` branches created by
`specy-road do-next-available-task` automatically satisfy the
`feature/...` prefix.

### Tagging convention

Semver tags with a `v` prefix:

- Final releases: `v0.1.0`, `v1.2.3`.
- Pre-releases: `v0.1.0-rc1`, `v0.2.0-beta1`. PEP 440 normalization is
  handled automatically (`-rc1` ↔ `rc1`).

You **don't tag manually**. Instead, open a PR from `dev` to `main` with
the title `release: v0.1.0` (or apply the `release:v0.1.0` label). The
leading `v` is **required** — the bare `0.1.0` form is rejected so the
project carries exactly one canonical version representation. The
[main-release-tag-gate.yml](../.github/workflows/main-release-tag-gate.yml)
workflow:

1. Validates the marker on the PR.
2. On merge to `main`, auto-creates the `vX.Y.Z` tag at the merge
   commit.
3. The tag push triggers
   [release-publish.yml](../.github/workflows/release-publish.yml),
   which publishes to PyPI (final tags) or TestPyPI (prerelease tags)
   via OIDC trusted publishing.

### Automated release process (what humans do, what machines do)

**Humans:**

1. Bump `pyproject.toml`'s `project.version` on `dev`. This is the
   canonical version: `specy_road.__version__` prefers that field when the
   package is imported from a checkout (sibling `pyproject.toml` with
   `name = "specy-road"`), otherwise uses installed package metadata.
   **`specyrd init`** command stubs and `.specyrd/manifest.json`
   (`specyrd_version`) substitute that runtime version — do not add a second
   hardcoded package version string elsewhere.
2. Update `CHANGELOG.md` — add a `## [vX.Y.Z]` section with the body
   that should appear on the GitHub Release.
3. Open a release PR from `dev` to `main` with title
   `release: vX.Y.Z` (the leading `v` is required). Body explains what's
   in the release.
4. Get the PR reviewed; merge it.

**Machines (no further human action required):**

5. `main-release-tag-gate.yml` validates the marker and (on merge)
   creates the tag `vX.Y.Z` on the merge commit.
6. `release-publish.yml` is triggered by the tag push and:
   - Reuses [`validate.yml`](../.github/workflows/validate.yml) as a
     prereq job to re-run the full validation pipeline against the
     tagged commit.
   - Builds sdist + wheel; runs
     [`scripts/check_release_version.py`](../scripts/check_release_version.py)
     to assert pyproject's version matches the tag.
   - Runs
     [`scripts/verify_wheel_contents.py`](../scripts/verify_wheel_contents.py)
     to assert the wheel contains the bundled PM Gantt UI assets.
   - Smoke-installs the wheel in a fresh venv and runs
     `specy-road --help` + `validate` + `export --check` against
     the dogfood fixture.
   - Publishes to **TestPyPI** (prerelease tags) or **PyPI** (final
     tags) via OIDC trusted publishing — no API tokens. Sigstore
     attestations are emitted (PEP 740).
   - Creates a GitHub Release using the `## [vX.Y.Z]` section of
     `CHANGELOG.md` as the body, with the sdist + wheel attached.
   - On the **first PyPI publish only**, opens a follow-up PR
     (`chore/readme-post-release-X.Y.Z`) that strips the README's
     pre-release notice + TODO and swaps the install-from-source
     block for `pip install specy-road`.

The PyPI Trusted Publisher OIDC trust is bound to **this exact workflow
file** (`release-publish.yml`) and **these exact environments**
(`pypi` and `testpypi`). Renaming the file or environments will break
publishing until you update the trust on `pypi.org` and
`test.pypi.org`.

### Trust & environment setup (one-time, off-repo)

1. **PyPI:** at `https://pypi.org/manage/account/publishing/` add a
   pending trusted publisher with owner `shanevigil`, repo `specy-road`,
   workflow `release-publish.yml`, environment `pypi`.
2. **TestPyPI:** same thing at
   `https://test.pypi.org/manage/account/publishing/` with environment
   `testpypi`.
3. **GitHub:** Settings → Environments → create `pypi` (deployment tag
   rule `v[0-9]+.[0-9]+.[0-9]+`; required reviewer optional but
   recommended) and `testpypi` (tag rule
   `v[0-9]+.[0-9]+.[0-9]+-*`; no reviewers).

### Manual smoke (no publish)

The release workflow accepts a `workflow_dispatch` trigger with
`dry_run: true`. This builds the package and runs all verification but
does NOT publish or create a release. Useful when refactoring the
workflow itself.

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
