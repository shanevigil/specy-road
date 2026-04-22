# Release runbook (canonical)

> **Audience:** maintainers and the autonomous coding agent. This is the
> single source of truth for cutting any `specy-road` release. The
> [contributor guide](contributor-guide.md) defers here for release
> mechanics; the AI rules under [`.cursor/rules/`](../.cursor/rules/)
> cite this doc.

This file describes the **two release flows** end-to-end:

- **A. RC (release candidate) → TestPyPI.** Tag form `vX.Y.Z-rcN`,
  routed by [`release-publish.yml`](../.github/workflows/release-publish.yml)
  to **TestPyPI**.
- **B. Final release → PyPI.** Tag form `vX.Y.Z` (no suffix), routed
  to **PyPI**.

Both flows share the same step shape; the differences are pulled out
explicitly in each section.

The "what blew up last time" footguns are baked in as inline
**recovery callouts**, so the next operator does not re-discover them.

---

## 0. Decision tree (1 minute)

```text
Is the change publish-worthy at all?
├─ No  → land normal PRs to dev; no release needed.
└─ Yes:
    Does it need real-world install testing first?
    ├─ Yes → cut an RC (Section A). Land further fixes on dev as
    │        normal PRs; cut additional RCs as needed (rc1, rc2, …).
    └─ No  → cut the final (Section B).
```

Tag suffix encodes the routing — `release-publish.yml` decides
TestPyPI vs PyPI from `vX.Y.Z-…` vs `vX.Y.Z`. **The version inside
`pyproject.toml` MUST match the tag** (the `check_release_version.py`
gate refuses the publish otherwise — this is a feature; do not
weaken it).

---

## 1. Quick-reference command catalogue

These are the canonical strings the agent (and humans) should use
verbatim. Mismatches against any of these will fail CI:

| Item | Value (verbatim) |
|---|---|
| **Branch name (RC)** | `chore/release-vX-Y-Z-rcN` (kebab-cased; e.g. `chore/release-v0-2-0-rc1`) |
| **Branch name (final)** | `chore/release-vX-Y-Z` (e.g. `chore/release-v0-2-0`) |
| **PR title (RC)** | `release: vX.Y.Z-rcN` (e.g. `release: v0.2.0-rc1`) |
| **PR title (final)** | `release: vX.Y.Z` (e.g. `release: v0.2.0`) |
| **PR base** | `main` (always; `chore/release-...` PRs do **not** stop in `dev`) |
| **`pyproject.toml` `project.version` (RC)** | `X.Y.ZrcN` (PEP 440; **no dash**, e.g. `0.2.0rc1`) |
| **`pyproject.toml` `project.version` (final)** | `X.Y.Z` (e.g. `0.2.0`) |
| **CHANGELOG heading (RC)** | `## [vX.Y.Z-rcN] - YYYY-MM-DD` |
| **CHANGELOG heading (final)** | `## [vX.Y.Z] - YYYY-MM-DD` |
| **Tag created on merge** | `vX.Y.Z-rcN` or `vX.Y.Z` (with leading `v`, mirroring the title) |
| **Pre-flight check** | `python scripts/check_release_version.py vX.Y.Z[-rcN]` (must print `ok:`) |

The leading **`v` is mandatory** in the PR title and tag — the
[`main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml)
regex rejects `release: 0.2.0`. Do not write the bare form anywhere.

The branch-name pattern `chore/...` is also load-bearing: it
satisfies the **[issue-link exemption](../.github/workflows/pr-conventions.yml)**
in `pr-conventions.yml`, so the release PR does not need a `Refs #N`
line in the body.

---

## 2. Agent vs human matrix

When the user asks the agent (me) to *"publish vX.Y.Z[-rcN]"*, the
agent owns every step in this matrix **except** the two explicitly
flagged "user runs this".

| # | Step | Owner | Why |
|---|------|-------|-----|
| 2.1 | `git fetch && git checkout dev && git pull --ff-only` | agent | sync. |
| 2.2 | Decide RC vs final, choose version number | agent (with user) | needs user intent. |
| 2.3 | Cut `chore/release-vX-Y-Z[-rcN]` branch | agent | naming is load-bearing. |
| 2.4 | Bump `pyproject.toml` `project.version` to PEP 440 form | agent | exact format matters. |
| 2.5 | Add `## [vX.Y.Z[-rcN]] - YYYY-MM-DD` to `CHANGELOG.md` | agent | uses today's UTC date. |
| 2.6 | Run `python scripts/check_release_version.py vX.Y.Z[-rcN]` locally | agent | must print `ok:`. |
| 2.7 | Run gate suite (validate, export --check, file-limits, pytest, gui-pm-gantt build, pip-audit, npm audit) | agent | identical to CI. |
| 2.8 | Commit, push branch, open PR to `main` titled `release: vX.Y.Z[-rcN]` | agent | uses `ManagePullRequest` or `gh`. |
| 2.9 | Wait for CI; resolve any failures | agent | runbook §6 covers each footgun. |
| 2.10 | Merge the PR (when CI is CLEAN/MERGEABLE) | agent | `gh pr merge --merge` is allowed for release PRs the agent opened. |
| 2.11 | Wait for `main-release-tag-gate.yml` `tag-main-commit` job | agent | watch the workflow. |
| 2.12 | **Manually re-push the tag** so `release-publish.yml` triggers | **user** | GitHub anti-recursion: the tag created by `GITHUB_TOKEN` does **not** fire downstream workflows. The agent prints the exact two-line command; the user runs it from their local clone. See §6, footgun ④. |
| 2.13 | Verify `release-publish.yml` ran and `Publish to PyPI` (or `TestPyPI`) succeeded | agent | `gh run watch` on the new tag. |
| 2.14 | Smoke-install from PyPI/TestPyPI in a fresh venv; verify `__version__` | agent | catches bad wheels. |
| 2.15 | If a final: open the README cleanup PR if the workflow couldn't | agent | runbook §6, footgun ⑥. |
| 2.16 | Back-merge `main → dev` | agent | mirror of `7236352` from rc4. |
| 2.17 | Cleanup: delete the `chore/release-...` branch + any `cursor/...` session aliases | agent | leave only `main`, `dev`, and active feature branches. |
| 2.18 | **Confirm the release is live** (final: PyPI page; RC: TestPyPI page) | **user** | the agent reports the URLs and waits for the user's "looks good" before signing off. |

---

## A. RC release to TestPyPI

Use case: "I want to test a candidate end-to-end before the real
publish." Result: a `vX.Y.Z-rcN` artifact on **TestPyPI**, installable
via:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            specy-road==X.Y.ZrcN
```

(The `--extra-index-url` is required so transitive deps still resolve
from real PyPI.)

### A.1 Pre-flight verification (the verify-then-cut pattern)

Before bumping any version: confirm both registries are still serving
known-good artifacts. This is the "verify-then-cut" pattern documented
in §0; it gives both registries a fresh-known-good signal without
mirroring finals to TestPyPI.

```bash
# 1. Latest stable from PyPI installs cleanly
python -m venv /tmp/verify-pypi
/tmp/verify-pypi/bin/pip install -q --upgrade pip
/tmp/verify-pypi/bin/pip install -q specy-road
/tmp/verify-pypi/bin/specy-road --help | head -5
/tmp/verify-pypi/bin/python -c "import specy_road; print(specy_road.__version__)"

# 2. Latest prerelease from TestPyPI installs cleanly (skip if no
#    previous RC exists yet)
python -m venv /tmp/verify-testpypi
/tmp/verify-testpypi/bin/pip install -q --upgrade pip
/tmp/verify-testpypi/bin/pip install -q --pre \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  specy-road
/tmp/verify-testpypi/bin/specy-road --help | head -5
```

If either install fails, **stop**: investigate before cutting another
release. The agent reports both versions and asks the user how to
proceed.

### A.2 Author the release commit

```bash
git checkout dev && git pull --ff-only
git checkout -b chore/release-v0-2-0-rc1   # adjust version
```

Bump `pyproject.toml`:

```toml
[project]
version = "0.2.0rc1"   # PEP 440: NO dash between Z and rc
```

Add a CHANGELOG block at the top (above `## [Unreleased]`):

```markdown
## [v0.2.0-rc1] - YYYY-MM-DD

First prerelease for v0.2.0. Routed to TestPyPI by
release-publish.yml. Smoke install:

    pip install --index-url https://test.pypi.org/simple/ \
                --extra-index-url https://pypi.org/simple/ \
                specy-road==0.2.0rc1

### Headline changes vs v0.1.0

- ...
```

Local pre-flight (mirrors what CI will run):

```bash
python scripts/check_release_version.py v0.2.0-rc1
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export   --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest -q
( cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build )
pip-audit
( cd gui/pm-gantt && npm audit --omit=dev )
```

All green → commit, push, open PR.

```bash
git add -A
git commit -m "release: v0.2.0-rc1"
git push -u origin chore/release-v0-2-0-rc1
```

PR (via `gh` or the agent tool):

- **Base:** `main`
- **Head:** `chore/release-v0-2-0-rc1`
- **Title:** `release: v0.2.0-rc1` (the leading `v` is mandatory)
- **Body:** focused notes; the GitHub Release body comes from the
  `## [v0.2.0-rc1]` block in CHANGELOG.

### A.3 Watch CI, merge, manage the tag

The PR will run:

- `validate-release-intent` (from `main-release-tag-gate.yml`):
  asserts the title carries the `v`-prefixed marker and the version
  matches `pyproject.toml`. Phase B.1 of this runbook (the pre-merge
  check) catches the version mismatch *here*, before merge.
- `roadmap` (from `validate.yml`): the full validation pipeline.
- `branch-naming` + `issue-link` (from `pr-conventions.yml`): the
  `chore/...` prefix auto-exempts the issue-link gate.

When all are green:

```bash
gh pr merge <N> --merge
```

After the merge:

1. **`main-release-tag-gate.yml` `tag-main-commit`** runs and
   *creates* tag `v0.2.0-rc1` on the merge commit. **GitHub policy:
   tags created by `GITHUB_TOKEN` do NOT trigger downstream
   workflows** (anti-recursion). So `release-publish.yml` does **not**
   fire automatically.

2. **The user manually re-pushes the tag.** The agent prints the
   commands and waits:

   ```bash
   git fetch origin --tags
   git push origin :refs/tags/v0.2.0-rc1
   git push origin v0.2.0-rc1
   ```

   This is the **one mandatory human step in every release** until
   the harness's Layer 2 hardening lands. It uses your local
   credentials, not `GITHUB_TOKEN`, so the tag push fires
   `release-publish.yml`.

3. **The agent verifies** `release-publish.yml` ran successfully:

   ```bash
   gh run list --workflow release-publish.yml --branch v0.2.0-rc1 --limit 1
   gh run watch <run-id> --exit-status
   ```

4. **Smoke-install from TestPyPI** in a fresh venv:

   ```bash
   python -m venv /tmp/smoke
   /tmp/smoke/bin/pip install --upgrade pip
   /tmp/smoke/bin/pip install --pre \
     --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ \
     specy-road==0.2.0rc1
   /tmp/smoke/bin/specy-road --help
   /tmp/smoke/bin/python -c "import specy_road; print(specy_road.__version__)"
   ```

   The version printed must be `0.2.0rc1`.

### A.4 Cleanup

```bash
git push origin --delete chore/release-v0-2-0-rc1
git branch -D chore/release-v0-2-0-rc1
```

Back-merge to `dev` is **NOT required for an RC** in the common case
where the `chore/release-...` branch was cut from `dev` and contained
nothing `dev` does not also contain — `main` is then a fast-forward of
`dev`, and `dev`'s tip is the parent of `main`'s tip, so `git merge
main` into `dev` is a fast-forward of one commit (the merge commit
itself). Run it anyway for record-keeping:

```bash
git checkout dev
git pull --ff-only
git merge --no-ff origin/main -m "chore: back-merge main (v0.2.0-rc1 release commit + tag history) into dev"
git push origin dev
```

---

## B. Final release to PyPI

Same shape as Section A. Differences:

- `pyproject.toml` version is `X.Y.Z` (no `rc`).
- Tag is `vX.Y.Z` (no suffix).
- Routes to **PyPI**.
- The `followup-readme-cleanup` job in `release-publish.yml`
  attempts to open a README post-release cleanup PR (Phase B.2 of
  this runbook ensures the workflow exits SUCCESS even when the PR
  creation is blocked by the repo's "Actions cannot create PRs"
  setting; the step summary will print the exact `gh pr create`
  command).

### B.1 Pre-flight verification (verify-then-cut)

Same as A.1: confirm `pip install specy-road` and the latest
TestPyPI prerelease both still install cleanly. If you cut RCs
leading up to this final, the most recent RC's version should match
your final's planned semver (e.g. final `v0.2.0` follows `v0.2.0-rc1`,
`v0.2.0-rc2`, …).

### B.2 Author the release commit

Identical to A.2 with the version stripped of the `rcN` suffix:

```toml
[project]
version = "0.2.0"
```

CHANGELOG:

```markdown
## [v0.2.0] - YYYY-MM-DD

First stable v0.2.0 release. Promotes the work landed in `vX.Y.Z-rcN`
candidates plus any post-RC fixes that landed on dev between the
last RC and this final.

### Headline (vs v0.1.0)

- ...
```

Branch + PR:

```bash
git checkout -b chore/release-v0-2-0
git add -A
git commit -m "release: v0.2.0"
git push -u origin chore/release-v0-2-0
```

PR title: `release: v0.2.0`. Same base/body shape as A.2.

### B.3 Merge, manual tag re-push, verify

Identical to A.3 with these adjustments:

- The tag is `v0.2.0` (not `-rcN`).
- After `release-publish.yml` succeeds, **also check the
  `followup-readme-cleanup` job result**:
  - SUCCESS → the workflow opened (or re-opened, idempotently) the
    README PR. Find it under "Pull requests" on the repo.
  - SKIPPED → not a final release; no action.
  - **FAILURE / step-summary fallback** → the repo blocks Actions
    from opening PRs. The workflow's run summary prints the exact
    `gh pr create` command; the agent runs it.

- Smoke install from real PyPI:

  ```bash
  python -m venv /tmp/smoke
  /tmp/smoke/bin/pip install --upgrade pip
  /tmp/smoke/bin/pip install specy-road==0.2.0
  /tmp/smoke/bin/specy-road --help
  /tmp/smoke/bin/python -c "import specy_road; print(specy_road.__version__)"
  ```

### B.4 Back-merge + cleanup

Back-merge is **mandatory for finals** so `dev` carries the release
commit + tag history. Mirror the rc4 commit `7236352`:

```bash
git checkout dev
git pull --ff-only
git merge --no-ff origin/main -m "chore: back-merge main (v0.2.0 release commit + tag history) into dev"
git push origin dev
```

Then delete the `chore/release-v0-2-0` branch and any `cursor/*`
session aliases. The remote should be back to `main` + `dev` +
active feature branches only.

---

## 6. Recovery: "If something goes wrong"

Each entry maps a real failure mode observed in production to its fix.

### ① PR title doesn't match the regex

**Symptom:** `validate-release-intent` job fails:

> PRs targeting main must declare exactly one release version. Use a
> title like 'release: v0.1.0'…

**Cause:** The title is `release: 0.1.0` (missing `v`) or `release vX.Y.Z` (missing colon) or has extra punctuation.

**Fix:** edit the PR title to exactly `release: vX.Y.Z` (or
`release: vX.Y.Z-rcN`). Re-run the workflow.

### ② `issue-link` check fails on a release PR

**Symptom:** `pr-conventions.yml` `issue-link` job fails:

> Non-chore PRs must reference an issue in the body — e.g. 'Fixes #123' or 'Refs #123'.

**Cause:** The branch is not `chore/release-...`. The release PR was
opened from a `cursor/...` or `feature/...` branch.

**Fix:** Push the same commit to a `chore/release-vX-Y-Z[-rcN]`
branch and re-open the PR from there. Alternatively, add `Refs #N`
to the PR body (where `#N` is a tracking issue) — but the
`chore/...` branch is the canonical fix.

### ③ Pre-merge version-vs-marker mismatch

**Symptom:** new pre-merge `check-release-version-vs-marker` job
(added in Phase B.1) fails:

> error: pyproject version 'X.Y.Z' does NOT match tag 'vA.B.C'…

**Cause:** `pyproject.toml`'s `project.version` is out of sync with
the PR title. Most common when an RC PR is repurposed as a final
without re-bumping the version.

**Fix:** edit `pyproject.toml` to match the PR title (PEP 440 form;
RCs are `X.Y.ZrcN`, no dash). Push the fix to the same branch.

### ④ The release tag does not trigger `release-publish.yml`

**Symptom:** PR merged, `tag-main-commit` succeeded with notice
`Created release tag 'vX.Y.Z'…`, but **no run** of
`release-publish.yml` appears in the Actions tab.

**Cause:** GitHub policy: refs created by `GITHUB_TOKEN` do **not**
trigger workflow runs (anti-recursion guard). The tag exists on the
remote but `on.push.tags` did not fire.

**Fix (the user runs this from a local clone):**

```bash
git fetch origin --tags
git push origin :refs/tags/vX.Y.Z   # or vX.Y.Z-rcN
git push origin vX.Y.Z              # re-push from your local credentials
```

This pushes the tag with the user's git credentials (not
`GITHUB_TOKEN`), which DOES fire the workflow. The agent will print
this exact two-line block and wait for the user's "done" before
proceeding.

> **Note:** This is a permanent step in every release until the
> Layer 2 hardening (Option 1: PAT, Option 2: GitHub App, both
> documented in the workspace's `PLAN.md`) is provisioned. The user
> has chosen **Option 3 (manual)** for now.

### ⑤ `tag-main-commit` "No PR found for commit" race

**Symptom:** `main-release-tag-gate.yml` `tag-main-commit` job fails
on `push` to `main` with:

> No PR found for commit \<sha\>. main requires PR-based release
> merges with release markers.

**Cause:** GitHub's commit→PR association sometimes lags 10–30s
after merge. The job ran before the API was eventually-consistent.

**Fix:** Re-run the failed workflow from the Actions UI. The Phase
B.3 hardening (added in this same PR) makes the job retry up to 3
times with a 30s sleep between attempts, so this should be
self-healing going forward.

### ⑥ `release-publish.yml` `followup-readme-cleanup` fails to open PR

**Symptom:** After a successful PyPI publish (final release only),
the `followup-readme-cleanup` job fails on the
`peter-evans/create-pull-request` step with:

> GitHub Actions is not permitted to create or approve pull requests.

**Cause:** Repo Settings → Actions → "Workflow permissions" has
"Allow GitHub Actions to create and approve pull requests"
disabled.

**Fix (Phase B.2 hardening):** the cleanup job is now
`continue-on-error` for the PR-create step **and** writes a fallback
to `$GITHUB_STEP_SUMMARY` containing:

- the cleanup branch name (`chore/readme-post-release-vX.Y.Z`),
- a one-line `gh pr create` invocation,
- a compare URL.

The agent reads the step summary, runs the printed `gh pr create`
command (or uses `ManagePullRequest`), and confirms the PR is open.

### ⑦ `check_release_version.py` rejects the publish

**Symptom:** `release-publish.yml` `Build distribution / Verify
pyproject version matches tag` step fails with:

> error: pyproject version 'X.Y.Zrc4' does NOT match tag 'vA.B.C'…

**Cause:** A bad merge landed the wrong commit on `main` — typically
because a tool re-used a stale head ref (this happened in the v0.1.0
release). The tag points at a `main` commit whose `pyproject.toml`
still carries the previous version.

**Fix:** This is the canary the workflow is supposed to be. **PyPI
was not polluted.** Recovery:

1. Delete the bad tag: `git push origin :refs/tags/vX.Y.Z`.
2. Inspect `main` HEAD's `pyproject.toml`. If the wrong commit is on
   `main`, a follow-up release PR with the correct version bump is
   the cleanest fix — `main` already has the bad merge, and rewriting
   `main` history is forbidden by branch protection.
3. Re-run the runbook from §A.2 / §B.2 with a fresh release PR that
   bumps the version *correctly* on top of the current `main`.

The pre-merge check added in Phase B.1 is designed to catch this
*before* the merge happens, so this footgun should be a one-time
v0.1.0 thing.

### ⑧ Stale `cursor/*` session aliases accumulate

**Symptom:** After a release, the remote has `cursor/release-...-f3d0`
or similar branches lingering.

**Cause:** The `ManagePullRequest` tool the agent uses pushes the
working branch under a fixed session ref. Multiple opens-and-aborts
across a session can leave several of these.

**Fix:** End-of-release cleanup script:

```bash
# List candidate session aliases (review before deleting)
git ls-remote --heads origin | grep 'cursor/' | awk '{print $2}' | sed 's|refs/heads/||'

# Delete each one once you've confirmed it's session debris
for b in cursor/foo-f3d0 cursor/bar-f3d0; do
  git push origin --delete "$b"
done
```

The agent does this automatically at the end of every release per the
matrix step 2.17.

---

## 7. After the release: README cleanup (final only)

For a final release, `release-publish.yml`'s `followup-readme-cleanup`
attempts to open a PR that:

- Removes the `> ## ⚠️ Pre-release notice` block from `README.md`.
- Removes the `<!-- TODO(post-release): … -->` comment.
- Swaps the `## Install` block from clone+editable-install to
  `pip install specy-road`.

Targets `dev` (NOT `main`); merge it like any other doc PR.

If the workflow's PR-create step is blocked (footgun ⑥), the agent
opens it manually using the step-summary command.

> If the README still has stale wording **after** the cleanup PR
> merges (e.g. a "Getting started" sentence still says "cloning,
> editable install"), open a small follow-up `chore/readme-...` PR
> to `dev` to fix it. Do NOT direct-push to `main`; the
> branch-protection rule rejects direct pushes, and a dedicated
> release-marker PR for a doc-only line is overkill — wait for the
> next legitimate release to carry the change forward.

---

## 8. Pre-release verification gate (always run, locally and in CI)

These are the gates `release-publish.yml` already runs in CI; the
agent runs them **locally first** to catch issues before opening the
PR.

```bash
# Python / roadmap
python scripts/check_release_version.py vX.Y.Z[-rcN]
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export   --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest -q

# PM Gantt frontend
( cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build )

# Supply-chain audits
pip install pip-audit && pip-audit
( cd gui/pm-gantt && npm audit --omit=dev )
```

All eight commands must exit 0. The PM Gantt build is reproducible
byte-for-byte against `specy_road/pm_gantt_static/`; if `git status`
shows changes after the build, **commit them** as part of the release
PR (the bundle ships inside the wheel).

---

## 9. Where this runbook lives in the docs graph

| Doc | Role |
|---|---|
| **`docs/release-runbook.md`** (this file) | the canonical release playbook for humans + agents |
| [`docs/contributor-guide.md`](contributor-guide.md) | general contributor doc; the "Release process" section defers here |
| [`AGENTS.md`](../AGENTS.md) | agent entry point; cites this runbook for any release task |
| [`.cursor/rules/030-git-workflow-management.mdc`](../.cursor/rules/030-git-workflow-management.mdc) | repo-policy rule for PR discipline; says "see release-runbook" for release flow |
| [`.github/workflows/main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml) | enforces the marker; this runbook documents how to satisfy it |
| [`.github/workflows/release-publish.yml`](../.github/workflows/release-publish.yml) | does the actual publish; this runbook documents its inputs |
| [`scripts/check_release_version.py`](../scripts/check_release_version.py) | the version-vs-tag gate; this runbook documents what it checks |
| [`scripts/post_release_readme_cleanup.py`](../scripts/post_release_readme_cleanup.py) | does the README cleanup; this runbook documents §7 |

If you change any of these files, audit this runbook for staleness
in the same PR.
