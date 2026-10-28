# Install and use specy-road

## Agent quickstart

**Use this doc when:** you install specy-road, scaffold or upgrade a consumer project, or need the everyday PM, developer and GUI command sequences.
**Not for:** toolkit-contributor topics — branching, PR workflow, npm build, audits ([`contributor-guide.md`](contributor-guide.md)) — or the detail behind each workflow ([`pm-workflow.md`](pm-workflow.md), [`dev-workflow.md`](dev-workflow.md)).

**Must know without reading on:**
- Python 3.11+ and git with a configured remote are required; there is no offline mode. `pip install specy-road` (extras: `[gui-next]`, `[review]`); an RC pins an exact version from TestPyPI with `--extra-index-url https://pypi.org/simple/`.
- New project: `specy-road init project`, set `integration_branch` / `remote` in `roadmap/git-workflow.yaml`, then `specy-road validate` and `specy-road export`.
- After `pip install -U specy-road`: `specy-road upgrade --prune` (runs `refresh-schemas`, `refresh-profiles`, `refresh-stubs`, then `validate`; `--dry-run` first); never `init project --force` for that.
- Add `--repo-root /path/to/consumer/repo` to every command run from outside the consumer repo.
- Dev loop: `specy-road do-next-available-task` → implement → `review-packet` + `mark-implementation-reviewed` → `specy-road finish-this-task --on-complete merge|pr`.

**Read further for:**
- prerequisites, PyPI, TestPyPI RCs, `uv pip`, source checkout → "Requirements", "Install", "Install from source (toolkit contributors)"
- what `init project` writes and the upgrade commands → "Initialize a new consumer project"
- command sequences → "Everyday workflow (PM)", "Everyday workflow (DEV / coding agent)", "Everyday workflow (GUI)"
- what a brief contains → "Brief generation"
- audits and the release pointers → "Optional dependency audit (consumer projects)", "Contributing & release process"

**Related:** [`contributor-guide.md`](contributor-guide.md), [`pm-workflow.md`](pm-workflow.md), [`dev-workflow.md`](dev-workflow.md), [`supply-chain-security.md`](supply-chain-security.md).

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

### Install a release candidate (TestPyPI)

Prereleases (`X.Y.ZrcN`) publish to **TestPyPI**, not PyPI. Pin the exact
version and keep real PyPI as an extra index so dependencies still resolve:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            "specy-road==0.3.1rc1"
```

**`--pre` is not needed when you pin an exact prerelease.** A specifier that
names the prerelease itself (`==0.3.1rc1`) already permits it. Add `--pre` only
when you are asking for *whatever the latest prerelease is* — an unpinned
install, or `pip index versions specy-road`, both of which hide prereleases
without it.

**`uv pip` needs one extra flag.** By default uv only considers versions from
the first index that contains a package at all — that is PyPI, which has no
RC — so it reports `No solution found`:

```bash
uv pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               --index-strategy unsafe-best-match \
               "specy-road==0.3.1rc1"
```

That default is uv's protection against dependency-confusion attacks, and
`unsafe-best-match` relaxes it for **every** package in the resolution, not just
this one. Prefer plain `pip` in a throwaway virtualenv for RC evaluation, and
keep RCs out of the environment that builds your product. See
[supply-chain-security.md](supply-chain-security.md).

**If the virtualenv has no pip** (`uv venv` and `uv sync` do not install one),
bootstrap it first:

```bash
.venv/bin/python -m ensurepip --upgrade
```

Then verify what you actually got:

```bash
specy-road --version
```

RCs are for evaluation. Pin a final release for day-to-day work, and expect an
RC to warn that IDE stubs and JSON schemas were written by an older version —
`specy-road upgrade` clears those once your team accepts the new pin.

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
specy-road --version          # confirm which build you are on
specy-road init project
# Edit roadmap/git-workflow.yaml so integration_branch and remote match
# your team's trunk (e.g. integration_branch: dev, remote: origin).
specy-road validate
specy-road export
```

`init project` writes `.gitignore`, `roadmap/`, `planning/`, `constitution/`,
`constraints/`, `shared/`, `schemas/`, `work/`, `model-profiles/`, `vision.md`, and a
specy-road section in `AGENTS.md` (a managed block: an `AGENTS.md` you already
have keeps everything outside the markers).
It refuses to overwrite an existing scaffold unless you pass `--force`.
Preview without writing: `--dry-run`.

### Keeping a consumer repo current after an upgrade

`pip install -U specy-road` upgrades the CLI. What it copied into your repo
(schemas, model profiles, IDE skills, the managed blocks) does **not** follow
along. One command brings it up to date and then checks the result:

```bash
pip install -U specy-road

specy-road upgrade --dry-run      # what each refresh would write
specy-road upgrade --prune        # write, delete stubs this version dropped, validate
```

`upgrade` runs `refresh-schemas`, `refresh-profiles` and `refresh-stubs` in
that order, then `validate` and `digest --check`, and ends with what is left for
you: review the diff, commit the new untracked files, and run `specy-road
digest` if the digest is missing or out of date (not `specy-road sync`, which
also fast-forwards your integration branch from the remote). It exits non-zero
only when `validate` fails. Each refresh is also a command of its own; all
three are idempotent, take `--dry-run`, and never touch the roadmap, planning
sheets, or anything outside a managed block.

**`refresh-schemas` — `schemas/`.** `init project` copies the JSON schemas in
once, so a repo scaffolded against an older version can reject output the
current CLI legitimately produces (for example `type: gate` nodes, or the
`implementation_review` fields that `mark-implementation-reviewed` writes).
`specy-road validate` warns when it notices this. A schema new in this version
is reported as such, because it is an untracked file to add. The command
touches `schemas/` and nothing else.

**`refresh-profiles` — `model-profiles/`.** Copies the profiles this version
ships that you lack, and never overwrites one you have (`--force PATH` takes
the toolkit's copy of one profile).

**`refresh-stubs` — the skills from `specyrd init`, and the managed blocks.**
One skill per command under `.agents/skills/<name>/SKILL.md`, read natively by
Cursor and Codex and through a symlink per skill under `.claude/skills/` by
Claude Code (or a flat directory for `--ai generic`), plus `.specyrd/README.md`.
It rewrites exactly the paths `.specyrd/manifest.json` records as managed,
installs stubs that shipped since you initialized, re-applies the managed
blocks in `AGENTS.md`, `.gitignore`, `.cursorindexingignore` and `CLAUDE.md`,
and bumps the recorded `specyrd_version`. `specy-road validate` warns while the
manifest lags. In a repo with no stub pack it still re-applies the managed
blocks, says no pack is installed, and creates no manifest.

Stubs this version no longer installs for your recorded `--role` are
**listed, not deleted**, unless you pass `--prune`. They are paths the
manifest recorded as the kit's, so `--prune` deletes exactly the list shown
(and a directory it leaves empty).

Once the upgrade is committed, `specy-road validate --strict` (exit 1 on any
warning) can gate CI next to `export --check` and `digest --check`.

#### Upgrading from 0.2.x

- **Commands became skills.** 0.2.x installed `.cursor/commands/specyrd-*.md`
  and `.claude/commands/specyrd-*.md`; 0.3 installs one skill per command under
  `.agents/skills/`, which Cursor, Codex and Claude Code all read. Until the old
  files are gone each `/specyrd-…` command appears twice: `upgrade --prune`
  (or `refresh-stubs --prune`) removes them.
- **`AGENTS.md` has a managed block.** `refresh-stubs` inserts it, with or
  without a stub pack; your own text outside the markers stays. If your
  `AGENTS.md` repeats a load order of its own, trim it to what is specific to
  your project: the block carries the toolkit's.
- **New files:** `schemas/orchestration.schema.json`, `model-profiles/`, and
  the skills are untracked after the upgrade; add them.
- **Text outside the managed blocks** (your `CLAUDE.md`, docs pinning a version
  or naming `.cursor/commands/`) is yours: search it for the old version.

**Neither `--force` is the tool for this.** `init project --force` overwrites
every scaffold file, including `roadmap/manifest.json` and your phase chunks
(only `.gitignore` and `AGENTS.md` keep your content).
`specyrd init --force` overwrites the stubs the manifest records; it is fine,
but `refresh-stubs` is narrower and needs no flag. Neither one will touch
anything outside a `>>> specy-road managed block <<<` in a file you own.

The bundled `.gitignore` ignores **only** the session-scoped files
(`work/.on-complete-*.yaml`, `work/prompt-*.md`, `work/pr-body-*.md`,
`work/.milestone-session.yaml`); briefs and implementation summaries are
intentionally tracked because they document the work and belong on the
feature branch. The PR-body snapshot is ignored because it is a regenerated
copy of those two.

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

Shape the roadmap before authoring it: `specy-road brainstorm start --topic "…" --under <ID>`, hand the prompt to your agent, `next-round`, `recommend`, `evidence` + `verify`, then `accept` / `reject --reason` / `park` and `promote` ([brainstorming.md](brainstorming.md)).

---

## Everyday workflow (DEV / coding agent)

```bash
# Pick the next actionable leaf, sync integration, register the claim,
# create feature/rm-<codename>, write a self-contained brief + agent prompt.
specy-road do-next-available-task

# Implement the task on feature/rm-<codename>, then write the summary:
$EDITOR work/implementation-summary-<NODE_ID>.md

# Review gate before finish: reviewers read the packet and record verdicts
# (docs/orchestration.md); under the default policy one interactive human
# approval here is enough.
specy-road review-packet <NODE_ID>
specy-road mark-implementation-reviewed

# Coordinating from a chat: hand a claimed leaf to a session on another
# harness and read its events back next turn (docs/orchestration-workers.md).
specy-road worker delegate <NODE_ID> --model <roster id>
specy-road worker sync --ack

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

The snapshot is a regenerated copy of two files that are already on the
branch, so `specy-road init project` ignores `work/pr-body-*.md` and
`specy-road file-limits` never reports it. If your repo predates that
ignore rule, `finish-this-task` prints a one-time pointer to add it.

When something goes wrong mid-pickup, specy-road auto-rolls-back the stale
registry claim (F-014). If the auto-rollback itself fails, follow the
printed instructions or run `specy-road abort-task-pickup --force`.

One case is deliberately **not** a rollback: if the feature branch already
exists, pickup checks it out instead of creating it, and keeps the claim. A
branch outlives its claim whenever a claim is released without deleting the
branch — a crashed finish, a hand-edited registry — and rolling back there put
the node straight back on the available list with the branch still in the way,
so the next pickup failed the same way forever. The command says so when it
happens, and tells you how far behind the integration branch you are.

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
(F-004): node metadata with the node's `goal` and its `acceptance` criteria
numbered `A1..An` (review records cite those ids), ancestor context chain,
every relevant planning
sheet inlined, `shared/README.md` plus only the shared contracts the
planning chain cites under `## References` (the rest are listed as paths;
`--all-contracts` restores full inlining), a git-derived history section
(`--no-history` skips it), dependency list, and a touch-zone discovery
instruction for the implementing agent. Output is
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
- **Tagging:** semver `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`). `dev` is
  promoted to `main` by a release PR, and the tag is created on the merged
  `main` commit — see [contributor-guide.md](contributor-guide.md).
- **PRs:** small and focused; drafts welcome; squash on merge.
- **Release:** [`release-publish.yml`](../.github/workflows/release-publish.yml)
  publishes on a release tag — finals to PyPI, `-rcN` prereleases to
  TestPyPI. The full procedure is
  [`docs/release-runbook.md`](release-runbook.md).
