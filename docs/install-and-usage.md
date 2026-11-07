# Install and use specy-road

## Agent quickstart

**Use this doc when:** you install specy-road, scaffold or upgrade a consumer project, or need the everyday PM, developer and GUI command sequences.
**Not for:** toolkit-contributor topics — branching, PR workflow, npm build, audits ([`contributor-guide.md`](contributor-guide.md)) — or the detail behind each workflow ([`pm-workflow.md`](pm-workflow.md), [`dev-workflow.md`](dev-workflow.md)).

**Must know without reading on:**
- Python 3.11+ and git with a configured remote are required; there is no offline mode. `pip install specy-road` (extras: `[gui]`, `[gui-next]`, `[review]`); pipx and uv tool work too. An RC is one exact wheel from TestPyPI, sha256-checked, with dependencies from PyPI only; TestPyPI is never an index ([`install-release-candidates.md`](install-release-candidates.md)).
- New project: `specy-road init project` (it also writes `roadmap.md` and `roadmap-context.md`), set `integration_branch` / `remote` in `roadmap/git-workflow.yaml`, make the first commit, then `specy-road validate`.
- After `pip install -U specy-road`: `specy-road upgrade --prune` (runs `refresh-schemas`, `refresh-profiles`, copies missing load-order docs, `refresh-stubs`, then `validate`; `--dry-run` first); never `init project --force` for that.
- Add `--repo-root /path/to/consumer/repo` to every command run from outside the consumer repo.
- Dev loop: `specy-road do-next-available-task` → implement → `review-packet` + `mark-implementation-reviewed` → `specy-road finish-this-task --on-complete merge|pr`.

**Read further for:**
- prerequisites, PyPI, pipx and uv tool, TestPyPI RCs, `uv pip`, source checkout → "Requirements", "Install", "Install a release candidate (TestPyPI)", "Install from source (toolkit contributors)"
- several installs or a stale `specyrd` launcher on `PATH` → "Which install is running"
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

For application teams, install the published package from PyPI with the tool you prefer:

```bash
pip install specy-road        # into the active virtualenv
pipx install specy-road       # isolated CLI on PATH; preferred on a maintainer machine
uv tool install specy-road    # the same, with uv
```

Optional extras (pipx and uv tool take the same quoted spec):

```bash
pip install "specy-road[gui]"       # PM Gantt UI deps
pip install "specy-road[gui-next]"  # PM Gantt UI deps (same set as [gui])
pip install "specy-road[review]"    # LLM review (`specy-road review-node`)
```

Upgrade to a new final release with the tool that installed it: `pip install -U specy-road`, `pipx upgrade specy-road` or `uv tool upgrade specy-road`.
Commands (not `--version`) warn when running older than `.specyrd/manifest.json` / `AGENTS.md`.

### Which install is running

```bash
which -a specy-road specyrd            # every launcher on PATH; the first one runs
specy-road --version                   # the version that first launcher runs
readlink -f "$(command -v specyrd)"    # where a symlinked launcher (pipx, uv tool) really points
```

A repo virtualenv, `pip install --user`, pipx and uv tool can each put a `specy-road` and a `specyrd` on `PATH`, and the earlier `PATH` entry wins: if `which -a` lists more than one, or `--version` is older than you installed, remove the installs you do not want. `specy-road doctor` lists the launchers too once your version ships that check.

**Stale `specyrd` launcher.** A `specyrd` left behind by an earlier install (a `~/.local/bin/specyrd` from `pip install --user`, or one from an uninstalled tool) makes `pipx install` or `uv tool install` stop at `specyrd` after `specy-road` was already handled, so a second attempt fails the same way. Resolve it with `readlink -f` as above, uninstall the install it belongs to (`pip uninstall specy-road` in that environment, `pipx uninstall specy-road`, `uv tool uninstall specy-road`), or `rm` the launcher if its environment no longer exists, then install once more.

### Install a release candidate (TestPyPI)

Release candidates (`X.Y.ZrcN`), with or without an extra, are installed from one sha256-checked wheel or its direct URL, never with TestPyPI as an index: see [install-release-candidates.md](install-release-candidates.md).

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
git add -A && git commit -m "Initialize specy-road"
specy-road validate
```

`init project` writes `.gitignore`, `.cursorindexingignore`, `roadmap/`, `planning/`, `constitution/`, `constraints/`,
`shared/`, `schemas/`, `work/`, `model-profiles/`, `research/`, `docs/` (`supply-chain-security.md`, `model-profiles-research-notes.md`), `vision.md`, the generated `roadmap.md` and `roadmap-context.md` (both committed; an existing one is left alone and neither is written, unless you pass `--force`), a specy-road stub in `AGENTS.md` (a managed block: an `AGENTS.md` you already have keeps everything outside the markers),
the rules it points at in `.specyrd/AGENTS.md`, and `.specyrd/AGENTS.team.md` for your team's own ([agent rules](optional-ai-tooling-patterns.md#agent-rules-agentsmd-and-specyrd)).
The roadmap starts with task M1.1, whose acceptance criteria and planning sheet are the setup steps above and more. It refuses to overwrite an existing scaffold unless you pass `--force` (`--dry-run` previews). Make the first commit before `validate`: until then it reports the untracked `vision.md` as an unknown touch zone.

### Keeping a consumer repo current after an upgrade

`pip install -U specy-road` (or `pipx upgrade specy-road`, `uv tool upgrade specy-road`) upgrades the CLI ([upgrading.md](upgrading.md): moving your text to the split rules files, previewing a version first, telling installs apart). What it copied into your repo
(schemas, model profiles, IDE skills, the managed blocks) does **not** follow
along. One command brings it up to date and then checks the result:

```bash
pip install -U specy-road         # or: pipx upgrade specy-road / uv tool upgrade specy-road

specy-road upgrade --dry-run      # what each refresh would write
specy-road upgrade --prune        # write, delete stubs this version dropped, validate
```

`upgrade` runs `refresh-schemas`, `refresh-profiles`, a copy of each shipped doc
the `.specyrd/AGENTS.md` load order names that you lack, and `refresh-stubs`, in that
order, then `validate` and `digest --check`, and ends with what is left for you:
review the diff and commit the new untracked files. When `validate` passes it
first writes `roadmap-context.md` if it is missing or out of date and
`roadmap.md` if it is tracked and out of date, one `wrote` line each (`would
write` in a dry run), and refuses a path with any symlink on it (in the project or out of it);
after a refusal, or when `validate` fails, it says to run `specy-road digest`
instead (not `specy-road sync`, which also fast-forwards your integration
branch from the remote). `--dry-run` runs its git calls in the temporary copy
with every `GIT_` variable dropped, no global or system git config, no hooks
and a timeout, so it is safe inside a git hook. It exits 2 when a git call it
depends on fails, and 1 when `validate` fails, and also, even when `validate`
passes, when a write is refused: before its first write, `upgrade` checks every
path it would change, and one that leads out of the checkout, or a schema, stub
directory or other path with any symlink on it, prints `error: <path> is a
symlink (to <target>), not <kind>` and writes nothing (`--dry-run` included).
`init project`, `refresh-schemas`, `refresh-stubs`, `specyrd init`, `export` and
`digest` refuse the same way and exit 1: any symlink on the path they write,
pointing out of the project or inside it, dangling or not, is refused rather than
followed. One exception: an agent skills directory itself may be a symlink to the other
one, with exactly this link text: `.claude/skills -> ../.agents/skills` or
`.agents/skills -> ../.claude/skills`, the other being a real directory; the
stubs are written into that directory. Any other skills link is refused: an
in-repository alias such as `.claude/skills -> ../tools/skills` (which earlier
releases accepted), an absolute or chained link, one through another link, a
dangling one, or one leaving the repository. Replace such a link with one of the
two values above or a real directory. Any other link on a stub's path is refused
too; the skill links made under
`.claude/skills/` are made on purpose. A stub, skill file, skill link or ignore
file refused this way prints `error:` and makes `refresh-stubs`, `upgrade` and
`upgrade --dry-run` exit 1; that path is left as it is and everything else is
still written. These stay report lines (`refused`, `skipped`) and do not change
the exit code: `AGENTS.md` or `CLAUDE.md` linked out of the repository (the two
may still link to each other), a shipped doc, a work template, and a model
profile. An explicit absolute
`digest -o` outside the checkout is written as given. Each refresh is also a command of its own; all three are
idempotent, take `--dry-run`, and never touch the roadmap, planning sheets, or
anything outside a managed block.

**`refresh-schemas` — `schemas/`.** `init project` copies the JSON schemas in
once, so a repo scaffolded against an older version can reject output the
current CLI legitimately produces (for example `type: gate` nodes, or the
`implementation_review` fields that `mark-implementation-reviewed` writes).
`specy-road validate` warns when it notices this. A schema new in this version
is reported as such, because it is an untracked file to add. The command
touches `schemas/` and nothing else.

**`refresh-profiles` — `model-profiles/`.** By default copies the missing
profiles that a roster entry in `roadmap/orchestration.yaml` names;
`--profiles all` copies every missing profile this version ships, and `--only`
adds one. It never overwrites one you have (`--force PATH` takes the toolkit's
copy of one profile).

**`refresh-stubs` — the skills from `specyrd init`, and the managed blocks.**
One skill per command under `.agents/skills/<name>/SKILL.md`, read natively by
Cursor and Codex and through a symlink per skill under `.claude/skills/` by
Claude Code (or a flat directory for `--ai generic`), plus `.specyrd/README.md`.
It rewrites exactly the paths `.specyrd/manifest.json` records as managed,
installs stubs that shipped since you initialized, re-applies the managed
blocks in `AGENTS.md`, `.gitignore`, `.cursorindexingignore` and `CLAUDE.md`, rewrites `.specyrd/AGENTS.md`, creates `.specyrd/AGENTS.team.md` when it is missing,
and bumps the recorded `specyrd_version`. `specy-road validate` warns while the
manifest lags. In a repo with no stub pack it still re-applies the managed
blocks, says no pack is installed, and creates no manifest.
When the `.gitignore` block changes, a real run lists the files git stopped showing (observed by git before and after the write) and the tracked files git now ignores that a rule the update added matches, even when an older rule also does; nothing is untracked. `--dry-run` prints an estimate, labelled as one, that can miss ignore inputs the scratch repository does not copy.

Stubs this version no longer installs for your recorded `--role` are **listed, not deleted**, unless you pass `--prune`. They are paths the
manifest recorded as the kit's, so `--prune` deletes exactly the list shown (and a directory it leaves empty).
Skills ship once, in `.agents/skills/` plus the `.claude/skills/` links; `specyrd init` writes nothing under `.cursor/` or `.codex/`. A `specyrd-*` copy of an installed skill under `.cursor/skills/`, `.codex/skills/` or `.cursor/commands/` makes Cursor or Codex, which already read `.agents/skills/`, load that skill twice: `validate` warns while one exists, and `--prune` also deletes each copy that is a link to the skill or a verbatim specyrd stub (one recorded for a `generic` pack is that pack's, not a copy). A copy you edited is named in the warning for you to delete.

Once the upgrade is committed, `specy-road validate --strict` (exit 1 on any warning) can gate CI next to `export --check` and `digest --check`.

`validate` also warns once per occurrence, naming the file line (`AGENTS.md:4`), when `AGENTS.md` or `CLAUDE.md` outside the managed block, or `.specyrd/AGENTS.team.md`, names an unregistered `specy-road` or `specyrd` subcommand. The same name on two lines is two warnings. A registered command never warns (`specy-road validate --strict`). A mention warns when it looks like a command invocation: inside a code span (a run of N backticks closed by the next run of exactly N) or a fenced block; on an open line after a run verb (run, exec, execute, invoke, uvx); as a command-led list item (the product name is the first token after the marker, optionally in code or emphasis, or only a run verb precedes it: `- specy-road frob --x`, `- Run specy-road frob`); or when the subcommand token is followed by a flag, a path, a quoted argument, an id-like argument, or the word command or subcommand (`Use the specy-road frob --flag`, `specy-road frob M1.2`). Plain prose does not warn (`trying specy-road here`, `when specy-road runs it`, `Then specy-road frob.`, `the specy-road toolkit is`, and a mid-sentence bullet such as "- **Adoption prompts** are kept aligned with other specy-road formats"). Scanning is line-based and best-effort: inline code spans on one line only; a fence closes only when the closing line uses the same fence character, is at least the opening length, and has nothing but whitespace after the run (" ```bash " does not close). Code spans that span lines are out of scope.

#### Upgrading from 0.2.x

- **Commands became skills.** 0.2.x installed `.cursor/commands/specyrd-*.md`
  and `.claude/commands/specyrd-*.md`; 0.3 installs one skill per command under
  `.agents/skills/`, which Cursor, Codex and Claude Code all read. Until the old
  files are gone each `/specyrd-…` command appears twice: `upgrade --prune`
  (or `refresh-stubs --prune`) removes them; `--dry-run` counts them first.
- **`AGENTS.md` has a managed block.** `refresh-stubs` inserts it, with or
  without a stub pack; your own text outside the markers stays. If your
  `AGENTS.md` repeats a load order of its own, trim it to what is specific to
  your project: the block carries the toolkit's. `validate` names any file its
  load order lists that you lack.
- **New files:** `schemas/orchestration.schema.json`, `model-profiles/`, and
  the skills are untracked after the upgrade; add them.
- **Text outside the managed blocks** (your `CLAUDE.md`, docs pinning a version
  or naming `.cursor/commands/`) is yours: search it for the old version.
- **`AGENTS.md` keeps only a stub now.** The rules move to `.specyrd/AGENTS.md`; `upgrade` prints a `migration:` line and does it once ([what changes](optional-ai-tooling-patterns.md#agent-rules-agentsmd-and-specyrd)).
- **A pointer-only `AGENTS.md` section; your own copy of the rules; context totals.** The default section (`"agents_block": "full"`) repeats the seven floor rules of `.specyrd/AGENTS.md`, so an agent that reads only `AGENTS.md` (Codex) still has them; set `"agents_block": "minimal"` in the git root's `.specyrd/manifest.json` and `refresh-stubs` and `upgrade` write a 3-line section instead (one line between the markers) that only points at `.specyrd/AGENTS.md` and the two addenda. When either command first creates `.specyrd/AGENTS.md`, it prints that file's headings and a `rules:` line for each heading in your `AGENTS.md`, outside the specy-road section, that matches one (case and spacing ignored; a hint: ATX headings indented up to three spaces, outside fenced code and HTML comments, and no setext or other CommonMark forms), then says to compare them and drop the copy that is stale; it edits nothing outside the section. Each `context:` line of `validate` ends with that harness's total lines and bytes; a file Claude Code reaches twice (loaded directly or `@`-imported by two of its files, such as `.specyrd/AGENTS.team.md` imported by both `CLAUDE.md` and `.specyrd/AGENTS.md`) is counted once and named: `(… imported twice, counted once)`.

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

Run all of these with `--repo-root /path/to/consumer/repo` if your shell is not already inside the consumer repo (for example when you're working in the toolkit clone and pointing at `playground/`).

`validate` ends with one `context:` line per harness: the lines and bytes of each instruction file it injects into every session started in the project root, and of the specy-road section inside it. Claude Code's line includes each file a counted file pulls in with an `@path` import (outside code spans and fenced blocks, relative to the importing file, up to four hops), such as the `.specyrd/AGENTS.md` the `CLAUDE.md` stub imports; an import outside the git root, and `.specyrd/AGENTS.local.md` (personal, gitignored) whether imported or not, are machine-local notes, never counted. Codex reads, in each directory from the git root down, the first non-empty of `AGENTS.override.md` then `AGENTS.md` (none of the `.specyrd/` files), and truncates them at its 32 KiB `project_doc_max_bytes` budget; Claude Code reads `CLAUDE.md`, `.claude/CLAUDE.md` and `CLAUDE.local.md` from the working directory up to the filesystem root (or `AGENTS.md` and `.claude/AGENTS.md` when none of those is present), plus every `.md` under `.claude/rules/` (recursively) from the git root down whose frontmatter does not set `paths` (a path-scoped rule loads only when Claude works on a matching file, so it is not counted), and documents a target of under 200 lines per file. Claude Code skips an instruction file over 4 MiB and loads none of it, so such a file is never counted: inside the git root it is a warning, outside it a note. Cursor reads `AGENTS.md` and `CLAUDE.md` from the git root down plus the rules under `.cursor/rules/` whose frontmatter sets `alwaysApply: true` (a rule scoped by glob or description loads only when it matches, so it is not counted); a nested `AGENTS.md` elsewhere below the git root applies only when the agent edits a file below it, so those get a note, found with `git ls-files` (ignored directories are not searched), and are not counted; Copilot reads `AGENTS.md` and `.claude/CLAUDE.md` in the git root and the working directory plus `.github/copilot-instructions.md` and the path-specific `.github/instructions/**/*.instructions.md`. Neither documents a size limit, so their lines report a total and never warn. Only files inside the git root count toward those limits, so exceeding one there is a warning and `validate --strict` fails on it. Files outside the git root — ancestor instructions, `~/.claude/CLAUDE.md`, and `AGENTS.override.md` or `AGENTS.md` in the Codex home (`$CODEX_HOME`, else `~/.codex`) — are notes labelled user-level / machine-local and are never a warning. So is Claude Code's auto memory, `~/.claude/projects/<repo>/memory/MEMORY.md` (`<repo>` is the main checkout's path with each non-alphanumeric character replaced by `-`, so every worktree shares it): the note gives the file's size and the part Claude Code loads, its first 200 lines or 25 KB, whichever comes first. A global `AGENTS.override.md` in the Codex home gets a note of its own: every Codex session on the machine reads it in place of the `AGENTS.md` beside it.

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
