# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The release-publish workflow extracts the section for the release tag
(matched by `## [vX.Y.Z]` heading) and uses it as the GitHub Release
body. Keep section bodies focused; link to PRs for detail.

## [Unreleased]

### Added

- **Agent context: `specy-road digest` and `specy-road search`.** A long-running
  project generates far more documentation than its roadmap describes, and most
  of the volume is duplicated — on a real 48-node repo, `work/` is 58% of the
  bytes and roughly 70% of it is a copy, because a brief inlines its ancestor
  planning sheets and every `shared/*.md` verbatim and a pr-body re-inlines the
  whole brief. An IDE index built over that returns the same passage from a dozen
  near-identical files, while archived work — the material most likely to be
  settled — has left the live graph entirely.
  - **`specy-road digest`** writes `roadmap-context.md`: one generated,
    git-tracked file with the live outline and rolled-up status, decisions taken,
    open gates, dependencies that were removed, what is archived, and what is
    claimed. About 6 KB for a 48-node roadmap, against the ~800 KB it stands in
    for. `--check` is a CI drift gate, like `export --check`.
  - **`specy-road search`** is ranked, deduplicated search over planning sheets,
    shared contracts, governance docs, roadmap-node prose, implementation
    summaries and archived work. Output is a pointer plus a snippet, never file
    contents, so an agent pulls the rest only if it needs it.
  - **No embeddings, deliberately.** The backend is SQLite FTS5 with BM25 from
    the standard library — no new dependency — with an in-memory fallback for
    builds without FTS5. Vector search brings staleness, privacy and reliability
    problems to a corpus that changes on every commit, and the identifiers people
    search for here (`M1.2`, a codename, a `node_key`) are exactly what lexical
    matching does best.
  - **Context is derived, not generated.** Contextual Retrieval pays an LLM to
    write a per-chunk summary because generic prose has no structure to read.
    Every sheet here already maps to a node, so the context line — id, title,
    type, status, codename, ancestor chain, archive state — is derived: free,
    exact, and unable to drift. It is indexed as its own weighted column, which
    is why "payments backoff" finds a section whose body never says "payments".
  - Ranking fuses BM25 with structural identifier matches via Reciprocal Rank
    Fusion, so `specy-road search M1.2` needs no special code path. Archived hits
    are demoted rather than hidden — often they are the *final* decision.
  - The index at `.specyrd/cache/search-index.sqlite3` is gitignored and
    disposable, rebuilt incrementally from `(mtime, size)` per file and tracking
    the **working tree** rather than `HEAD`, so uncommitted edits are searchable.
    296 chunks, 0.3s cold build, ~9ms per query on the repo above.
  - How much the ignore block removes depends on the repo's `.gitignore`, since
    an index already skips what git ignores. With the shipped scaffold, which
    tracks briefs on purpose, excluding them takes the indexed corpus from
    ~351 KB to ~205 KB (42%) on a 48-node project; a repo that already ignores
    briefs sees little until it starts archiving.
  - **`specyrd init` now maintains a marked block** in `.cursorindexingignore`
    (`roadmap/archive/`, `work/brief-*.md`, `roadmap.md`) and in `.gitignore`
    (`.specyrd/cache/`). Content outside the markers is never touched and
    re-running is a no-op. `.cursorindexingignore` — not `.cursorignore` — because
    it removes files from Cursor's index while leaving them readable when
    referenced; blocking reads would break every path search returns. Claude Code
    gets no read-denials: it builds no index, and deny rules would break the same
    pointers.
  - **Fixes an upgrade gap:** `init project` skips a `.gitignore` that already
    exists, so a repo scaffolded before these caches existed would have shown
    `.specyrd/cache/` as untracked forever. The managed block repairs that.
  - New stubs `specyrd-search`, `specyrd-digest` and the previously missing
    `specyrd-history`, installed for both `pm` and `dev` roles. A test now
    cross-checks the command templates against the install registry, which
    nothing did before — a template with no entry shipped in the wheel and never
    installed.
  - The `##`-section parser is lifted out of `brief_dependency_context` into
    `specy_road.text_sections`, shared with the index; brief output is unchanged.
  - Docs: [`docs/agent-search.md`](docs/agent-search.md).

- **Roadmap history, derived from git.** `specy-road history [NODE_ID]` answers
  how the roadmap got to its current shape: status transitions, dependency edges
  added and later dropped, renumbering, planning-sheet revisions, and archived
  work. Without it an agent re-derives decisions that were already made and
  unmade, and archived subtrees look like work that was never done.
  - **Events are keyed by `node_key`, not `id`.** An `id` is a position in the
    outline and renumbers freely, so an id-keyed history would lose a node's past
    every time a milestone was inserted above it. Renumbering is recorded as an
    ordinary event and the node's story stays continuous across it.
  - An id that several nodes have held, and none holds now, **exits 2 and lists
    the candidates** rather than guessing which node's past to show.
  - **Nothing is committed.** The index is cached at
    `.specyrd/cache/roadmap-history.json` (gitignored; `.specyrd/manifest.json`
    stays tracked) and rebuilt whenever git disagrees with it — a moved `HEAD`
    appends only the new commits, a rewritten history rebuilds, and an
    unrecognised `cache_version` rebuilds, so there is no migration to write.
  - Cost is one `git log --raw` pass plus one long-lived `git cat-file --batch`
    process for the whole history, with parsed chunks memoised by blob SHA.
    Planning-sheet events are free: the flat-`planning/` naming rule puts the
    `node_key` in the filename.
  - The walk follows `--first-parent`, so each step is a state the integration
    branch actually passed through and a merged branch arrives as one step.
    Walking `--no-merges` instead interleaves parallel branches and manufactures
    flip-flop events.
  - `specy-road brief` gains a `## 9. History` section from the same index,
    including archived work on the node's branch of the outline. Suppress it
    with `--no-history`.
  - Docs: [`docs/roadmap-history.md`](docs/roadmap-history.md).

- **Archive completed roadmap subtrees.** Long-running roadmaps accumulate
  finished milestones that keep loading, validating, exporting and rendering
  forever, eventually pushing chunks toward `roadmap_json_chunk_max_lines`.
  `specy-road archive <NODE_ID>` now moves a subtree whose rollup status is
  `Complete` out of the live graph into `roadmap/archive/`, with
  `list-archives`, `show-archive`, and `restore-archive` alongside it, plus
  `archive --auto [--older-than-days N]` to sweep everything finished longer
  than a threshold. This is unrelated to the PM GUI's **Hide Complete** button,
  which remains a pure view filter, and to the legacy destructive
  `archive-node --hard-remove`.
  - The live/archived boundary is `manifest.json`'s existing `includes` list,
    which the roadmap loader already treats as authoritative — archiving needs
    no loader change.
  - **Live nodes may keep depending on archived work.**
    `validate_dependency_ids` would otherwise hard-fail on the dangling
    `node_key`. Rather than rewriting dependency edges, `roadmap/archive/index.json`
    records every archived key and validation accepts it as satisfied
    (archived implies Complete). Live `dependencies` arrays are left untouched,
    which is what makes restore lossless. **That index is not disposable** —
    deleting it turns every such edge into a validation error.
  - Restore replays each node's recorded chunk **and index within that chunk**,
    so an archive/restore round trip leaves no diff, including when the subtree
    shared a chunk with live nodes or spanned several chunks. A chunk the
    archive emptied is recreated and re-added to `includes`.
  - Archived planning sheets land under `roadmap/archive/planning/`, not
    `planning/archive/`: `validate` rejects any subdirectory or nested `.md`
    under `planning/`.
  - Records capture best-effort git provenance (rollup branch, integration
    branch, merge commit, nearest tag, `closed_at`) read from
    `milestone_execution` and existing refs. **No git objects are created.**
  - An active `milestone_execution` blocks archiving its subtree and `--force`
    does not override that, since moving files out from under an in-flight
    rollup would strand the branch.
  - New bundled schema `specy_road/schemas/archive.schema.json`, validated from
    the wheel rather than from `<repo_root>/schemas/`, so adopters pick up new
    archive fields by upgrading the package instead of hand-editing a
    consumer-owned schema. `scripts/verify_wheel_contents.py` and
    `tests/test_package_data_schemas.py` guard that it ships.
  - Docs: [`docs/archiving.md`](docs/archiving.md).

- **Deep archive tier.** `specy-road archive <NODE_ID> --deep` (or
  `deepen-archive <ARCHIVE_ID>` afterwards) folds an archived chunk and its
  planning sheets into a single capsule file,
  `roadmap/archive/deep/<archive_id>.json`, removes the loose files, and leaves
  a standalone `roadmap/archive/refs/<archive_id>.json` naming the nodes and the
  git refs they were delivered on. Deep archives are not browsable in the PM
  GUI; their reference file is.
  - **The capsule is uncompressed text, deliberately.** The tier exists to cut
    file count, not bytes. Git already zlib-compresses and delta-compresses
    blobs, so a compressed archive would be opaque to that — stored in full on
    every change, with `diff`, `blame`, `log -p` and `git grep` all lost on
    content someone would later want to read. Canonical JSON formatting also
    makes the capsule byte-reproducible, which a gzipped tarball could not be
    (gzip headers carry a timestamp; tar headers carry per-file mtime/uid/gid).
  - The index record keeps its `node_keys` and `nodes_summary` through
    deepening, so a deep archive stays listable and keeps satisfying live
    dependencies without opening the capsule.
  - `restore-archive` handles both tiers in one command — on a deep archive it
    unfolds and then restores.
  - **The capsule `sha256` is verified before anything unfolds.** A mismatch is
    refused outright rather than partially restored; the archive stays deep and
    the live roadmap is untouched.

- **Last-worked-on for roadmap nodes, derived from git.** The PM GUI shows a
  **Last worked** column on leaf rows. It is computed from commit dates on
  demand and **never stored**, so an existing repo is fully populated the first
  time it is opened — there is no seeding step, no migration, and no file added
  to the consumer repo.
  - Per node: the last commit touching its planning sheet (precise), falling
    back to its roadmap chunk only when the sheet was never committed. The two
    are not blended — a chunk holds many nodes, so crediting its date to all of
    them would make every sibling look freshly worked whenever one node's
    status changed.
  - Merge commits do not count as a touch, or every node would look freshly
    worked after each integration merge.
  - Reflects **committed work only**, so it is a lower bound; the Dev column
    and `roadmap/registry.yaml` show active claims.
  - One `git log --name-only` walk per roadmap, memoized on `HEAD` (commit
    dates cannot move while `HEAD` is still). Asking git per node is linear in
    node count: ~31s on a 400-node roadmap against ~0.17s for a single walk.
  - `archive --auto` uses the same derived date when a subtree has no
    `milestone_execution.closed_at`, so it now reaches work that never went
    through a rollup.

- **PM GUI archive surface.** An **Archive** toolbar button opens a drawer that
  lists archived subtrees, offers eligible ones, previews a plan before
  committing to it, and restores or deep-archives in one click. Eligibility is
  computed server-side from the same gate the CLI uses, so the drawer never
  offers something `specy-road archive` would refuse. Every write carries the
  usual `X-PM-Gui-Fingerprint` token — archiving moves roadmap files, so a stale
  tab must not be able to fire one.
  - New `pm_gui` preferences under **Settings → Completed work**:
    `auto_hide_completed` (seeds the Hide Complete filter — a **view filter**,
    no files move), `auto_archive_completed` and `auto_archive_after_days`
    (which **do** move files, always bounded by the age threshold).
  - **`Hide Complete` is unchanged.** It remains a pure view filter; the new
    preference only sets its initial state.
  - The outline gains a **Last worked** column on leaf rows, with the exact
    timestamp and the reason in the cell tooltip.

### Fixed

- **Archived files no longer trip the roadmap chunk line limit.**
  `validate_roadmap_line_limits` scans every `*.json` under `roadmap/`, so
  `roadmap/archive/` was checked against `roadmap_json_chunk_max_lines` (500).
  Archiving writes a whole subtree into one file and the ledger grows per
  record, so **one archive of a 31-node phase was enough to make `validate`,
  `export --check` and every CRUD command exit 1** — on exactly the repositories
  archiving exists to help, with no way to split the files. `file-limits`
  reported OK throughout, because only the other scanner had been exempted.
- **Archiving an ancestor of a locked milestone is refused.** The milestone
  lock marks a milestone and its descendants, so a root-only check passed when
  archiving an *ancestor* and carried the locked subtree out from under an
  in-flight rollup branch.
- **Archiving the last live subtree is refused.** It would leave
  `manifest.json` with `"includes": []`, which the loader reads as the legacy
  "nodes live in the manifest" layout — a repository that cannot load at all.
- **`restore-archive` validates before destroying the archive.** It previously
  deleted the chunk, planning sheets and ledger record and only then validated,
  so a validation failure destroyed the only copy on the way to reporting the
  error.
- **Dependencies can still be edited on a node that depends on archived work.**
  Every dependency write sends the full set, and the edit path rejected keys
  absent from the live graph — so one archived dependency made a node's
  `dependencies` permanently uneditable from both the CLI and the PM GUI.
- **Archiving a node with an open registry claim is refused.** It used to
  apply fully and only then fail validation (`registry: entry … references
  unknown node_id`), leaving the repository failing `validate` with no hint why
  and stranding the claimant's feature branch. Now caught before anything moves.
- **`specy-road brief` names archived dependencies** instead of reporting "no
  effective dependencies" for a node that visibly lists one.
- **`list-dependencies` labels an archived dependency as archived** rather than
  "missing node_key in roadmap", which pointed the PM at the one edit that
  breaks restore.
- **Last worked is populated when the roadmap is not the git repo root.**
  `git log --name-only` prints repository-relative paths while roadmap paths are
  project-relative, so in a monorepo — or any `SPECY_ROAD_REPO_ROOT` pointing at
  a subdirectory — every lookup missed and the column went silently blank.
- **The outline's drag-drop rows span the full table again.** `TABLE_COLS` was
  left at 5 when the sixth column was added, truncating the root drop zone and
  every gap row.
- **The auto-archive preferences now do something.** `auto_archive_completed`
  and `auto_archive_after_days` were saved and read back but consumed by
  nothing. The Archive drawer now surfaces subtrees past the threshold with a
  one-click action — surfaced, never applied on its own, because archiving
  moves files.

### Changed

- **Archive and restore is now net-zero.** Restoring the last archive removes
  `roadmap/archive/` instead of leaving an empty ledger behind for the user to
  explain in review.
- **`file-limits` skips archived material.** `roadmap/archive/**` is added to
  the session-artifact skip list: a scaffold's `**/*.md` glob would otherwise
  keep flagging planning sheets for milestones that shipped years ago, which
  defeats much of the point of archiving.
- **The destructive `archive-node --hard-remove` error message now points at
  `specy-road archive`** for retiring completed work. The path itself lives in
  `specy_road/bundled_scripts/roadmap_crud_delete.py` (split out in v0.1.4) and
  keeps its atomic behavior; the two commands remain unrelated despite the
  similar names.


## [v0.1.4] - 2026-08-31

First stable **v0.1.4** release on **PyPI**. Promotes the work validated in
`v0.1.4-rc1`, `v0.1.4-rc2`, and `v0.1.4-rc3` with no post-rc3 code changes.
Smoke install:

    pip install specy-road==0.1.4

**Adopters upgrading from any earlier version:** if `specy-road init project`
scaffolded your repository before this release, run **`specy-road
refresh-schemas`** once. Repos created from `v0.1.4-rc2` or later should also
ensure `.gitignore` includes the `work/` session-artifact rules from
[`specy_road/templates/project/.gitignore`](specy_road/templates/project/.gitignore).

### Headline (vs v0.1.3)

- **`specy-road grind-session`** — agent-driven task-loop orchestration with
  read-only `--plan` waves/batches for parallel dispatch
  ([docs/grind-session.md](docs/grind-session.md)).
- **`specy-road refresh-schemas`** — refresh consumer `schemas/` from the
  installed toolkit without touching roadmap files.
- **Atomic roadmap mutations** — refused `add-node` / `edit-node` no longer
  leave orphan sheets or half-written chunks; PM GUI routes share the same
  staging.
- **Dependency satisfaction follows rollup status** — a finished phase no
  longer silently blocks downstream leaves.
- **Base-install dev loop works again** — `requests` is a core dependency so
  `do-next-available-task` and `grind-session` run after `pip install specy-road`.
- **Packaging and hygiene** — wheel ships `.gitignore` / `work/.gitkeep`;
  `file-limits` respects `.gitignore` and skips toolkit session artifacts;
  `specy-road --version` works.

See the `v0.1.4-rc1` … `v0.1.4-rc3` sections below for full detail.

## [v0.1.4-rc3] - 2026-08-27

Third release candidate for v0.1.4. Routed to **TestPyPI** by
release-publish.yml. Smoke install:

    pip install --index-url https://test.pypi.org/simple/ \
                --extra-index-url https://pypi.org/simple/ \
                specy-road==0.1.4rc3

Closes the three defects an adopter reported after an autonomous grind on
`v0.1.4-rc2`, plus two release blockers the pre-release pass found on top of
them. Every item is a case of specy-road doing damage on the way out of a
*refused* operation, or of two parts of the toolkit disagreeing about what
"complete" means. The analysis behind the adopter items, including the ones
deliberately not changed, is in
[`docs/design-notes/rc2-adopter-feedback-triage.md`](docs/design-notes/rc2-adopter-feedback-triage.md).

**Adopters upgrading from any earlier version:** if `specy-road init project`
scaffolded your repository before this release, run **`specy-road
refresh-schemas`** once. `init project` copies `schemas/` in and never revisits
it, so an older copy rejects output the current CLI legitimately produces
(`type: gate` nodes, the `implementation_review` fields
`mark-implementation-reviewed` writes). `specy-road validate` now warns when it
notices this. Do **not** use `init project --force` for it — that rewrites every
scaffold file, including `roadmap/manifest.json` and your phase chunks.

### Fixed

- **A refused `edit-node` no longer leaves the invalid edit on disk.**
  `edit_node_set_pairs` wrote its chunk and renamed the node's planning sheet
  *before* validating. On rejection it exited 1 and left behind the invalid
  chunk, a deleted sheet and a renamed one, so every later command failed
  validation and a multi-`--set` batch was impossible to reason about. The chunk
  write, any overflow relocation, and the planning-sheet rename are now staged
  in one atomic plan that only lands if the prospective graph validates. Same
  function backs the PM GUI's edit, sibling-reorder, and delete routes.
- **A refused `add-node` no longer leaves an orphan planning sheet.** The chunk
  rollback already worked, but the sheet was scaffolded outside the transaction,
  and an ownerless sheet is a *fatal* validation error — so a rejected add left
  a repo that could not validate at all. The sheet now travels with the chunk.
- **The self-heal pass no longer runs inside a mutation's transaction.** It
  rewrites chunks and renames sheets, and it ran from each mutation's validation
  callback, outside the atomic plan's snapshot. For a task with no codename
  (every PM GUI add) it renamed the just-staged sheet, so the rollback unlinked
  a path that no longer existed and the renamed sheet survived as an orphan.
  Mutations now heal first and validate without healing, and new tasks get their
  codename derived up front on every add path.
- **A finished phase no longer silently blocks everything downstream of it.**
  `roadmap.md`, `brief` and the PM GUI read the F-013 rollup, but dependency
  satisfaction read a parent's own `status` field, which nothing updated when
  its last leaf closed. Downstream leaves became permanently unpickable with no
  error: `validate` said OK, `reconcile-milestone-status` was a no-op (it only
  looks at nodes carrying `milestone_execution`), and rc2 had removed the one
  warning that used to hint at it. `grind-session --plan` disagreed with itself,
  counting such a leaf as ready while leaving it out of every wave. Satisfaction
  now reads the rollup, in `do_next_available` and in the three places
  `session_plan` had reimplemented it.
- **`pip install specy-road` can run the dev loop again.** `do_next_available`
  imports `roadmap_gui_remote` for the MR-rejected pickup tier, that module
  imports `requests` at module scope, and `requests` was declared only in the
  `gui` / `gui-next` / `dev` extras — so `do-next-available-task` and
  `grind-session` died on `ModuleNotFoundError` before printing anything on a
  base install. Reproduced against the published `0.1.4rc2` wheel, so this
  shipped in rc1 and rc2. A new test walks the module-scope import graph from
  every CLI entry script and fails when it reaches a package that is not a base
  dependency.
- **Mutation commands stop printing validation's `OK: roadmap and registry
  validate.` into their own output**, and a refused mutation no longer relabels
  unrelated warnings under its `error:` prefix. Between them, that is what made
  `add-node` look as though it had reported success and failure at once.

### Added

- **`specy-road refresh-schemas`** — updates a consumer repo's `schemas/` from
  the installed toolkit and touches nothing else (`--dry-run` to preview).
  `validate` warns when a consumer schema differs structurally from the bundled
  one; the comparison ignores description text, so rewording is not drift.
- **`finish-this-task` closes rolled-up ancestors** in the same bookkeeping
  commit (`[ok] M9 status -> Complete (all leaf descendants complete)`), so the
  authored graph stops drifting from what every reader computes. Ancestors
  carrying `milestone_execution` are left to the milestone-rollup state machine,
  which closes them only once the rollup branch is proven merged.

### Changed

- **`validate` reports parent status that disagrees with its rollup** again, as
  a warning that names the `edit-node` command to fix it. It never fails: the
  rollup is authoritative for readers *and* for dependency satisfaction. rc2
  removed this warning while leaving satisfaction on own-status, which is what
  made the stall silent.
- **`list-nodes` prints a header and separate `STATUS` / `ROLLUP` columns.** One
  unlabelled column let a parent row contradict `roadmap.md` with no way to tell
  which number was which.
- **The oversized-chunk error names `specy-road rebalance-chunks`**, which
  re-packs chunks and updates the manifest. The old wording ("split or reduce to
  a single node per file") sent adopters off to hand-split JSON.
- **`do-next-available-task -h` documents the two selection rules that read
  backwards without it**: a `Blocked` leaf is promoted to the top of the queue
  rather than skipped (pickup now prints `status: Blocked` on the leaf it hands
  over), and `execution_milestone` is advisory metadata that does not gate
  pickup — a `type: gate` dependency is the enforcing mechanism. The top-level
  usage text also lists `--on-complete`, which existed but was undocumented
  there.

## [v0.1.4-rc2] - 2026-08-21

Second release candidate for v0.1.4. Routed to **TestPyPI** by
release-publish.yml. Smoke install:

    pip install --index-url https://test.pypi.org/simple/ \
                --extra-index-url https://pypi.org/simple/ \
                specy-road==0.1.4rc2

Acts on adopter feedback gathered while running the `v0.1.4-rc1` prerelease on a
real project, plus five further defects the pre-release pass found on top of it.
Almost every item is a case of specy-road tripping over its own output, shipping
an incomplete artifact, or leaving a mode implicit that its own docs call
unusable.

**Adopters upgrading from `v0.1.4-rc1` or earlier:** if `specy-road init project`
scaffolded your repository, it did not write a `.gitignore` (see the packaging
fix below). Copy the rules from
[`specy_road/templates/project/.gitignore`](specy_road/templates/project/.gitignore)
into yours, then `git rm --cached` any `work/prompt-*.md`,
`work/pr-body-*.md`, `work/.on-complete-*.yaml`, or `work/.milestone-session.yaml`
that got committed.

### Fixed

- **`specy-road init project` now scaffolds its `.gitignore` for pip-installed
  users.** `[tool.setuptools.package-data]` covered the template tree with
  `templates/project/**/*`, and those globs are `fnmatch`-style, where `*` does
  not match a leading dot — so `.gitignore` and `work/.gitkeep` were dropped
  from the wheel with no warning. `init project` copies whatever is on disk, so
  an editable checkout scaffolded correctly and only `pip install specy-road`
  users were affected: they got a consumer repo with **no ignore rules at all**
  and started committing `work/prompt-*.md`, `work/.on-complete-*.yaml`,
  `work/.milestone-session.yaml`, and the PR-body snapshot. This is the actual
  origin of the tracked session artifacts reported against `v0.1.4-rc1`. Both
  paths are now declared explicitly, `scripts/verify_wheel_contents.py` asserts
  they are in the built wheel, and a test asserts every template dotfile is
  declared. **Existing consumer repos need the ignore rules added by hand** —
  copy them from `specy_road/templates/project/.gitignore`.
- **`specy-road abort-task-pickup` works immediately after a pickup.** It
  refused whenever `git status --porcelain` was non-empty, and
  `do-next-available-task` always leaves untracked files behind — the brief is
  deliberately not gitignored — so the documented escape hatch failed in its
  most common invocation and the user had to hand-delete the toolkit's own
  output first. The check now skips the untracked `work/` artifacts belonging to
  the pickup being aborted (the ones abort deletes anyway). A modified tracked
  file still blocks, and the error now lists what is dirty.
- **`specy-road file-limits` no longer fails on the toolkit's own output.**
  `finish-this-task` writes `work/pr-body-<NODE>.md` (the F-015 snapshot of the
  brief plus the implementation summary) and cannot delete it, because the
  printed `gh pr create --body-file` command still needs it. It is several
  thousand lines, is matched by the scaffold's `**/*.md` glob, and was not
  ignored — so a default `init project` scaffold failed `file-limits` after its
  first finish. `file-limits` now skips the session artifacts specy-road itself
  writes under `work/` (`brief-`, `prompt-`, `implementation-summary-`,
  `pr-body-`, `.on-complete-`, `.milestone-session.yaml`), the `init project`
  `.gitignore` covers `work/pr-body-*.md`, and `finish-this-task` points repos
  that already track the snapshot at the ignore rule.
- **`specy-road file-limits` respects `.gitignore`.** The scan walked every
  directory outside a hardcoded eight-entry skip list, reporting violations for
  files CI can never see; one adopter repo reported 1,579 untracked violations
  out of 1,610. Inside a git worktree, ignored paths are now skipped. Tracked
  files are still always checked, even when an ignore rule matches them. Use
  `specy-road file-limits --no-respect-gitignore` for the old behavior.
- **A tracked `work/.on-complete-<NODE>.yaml` is now removed properly.** The
  sidecar was unlinked without staging, unlike its brief/prompt/summary
  siblings, so a committed copy left a dirty worktree that the next checkout
  restored. `finish-this-task` now removes it during its bookkeeping phase, so
  a tracked copy is staged into that commit. The other callers (abort, milestone
  rollup, the `on_complete` tail) run after their command's last commit, where
  staging would only leave a dirty index, so they still plainly unlink.
- **`specy-road --version` / `-V` works** (also `specyrd --version`). It
  previously fell through to `unknown command: --version` and exited 2, while
  `specy_road.__version__` resolved correctly.
- **A new phase node gets its own chunk.** A phase has no phase *ancestor*, so
  it bypassed the router's locality pass and landed in whichever chunk had
  room — typically a sibling phase's file. Everything added under it then
  followed it there, so one misrouted phase root pulled its whole subtree into
  a misnamed chunk. `add-node --type phase M2` now creates `phases/M2.json`. An
  explicit `--chunk` hint still wins.

### Changed

- **`specy-road grind-session` refuses to run in `pr` mode.** `pr` never merges
  between cycles, so each finish stays stranded on its feature branch where the
  next pickup — which syncs to the integration branch first — cannot see it.
  `pr` is also the fallback when nothing declares a mode, so an unattended grind
  in a repo whose `git-workflow.yaml` omitted `on_complete` degraded silently.
  The loop now resolves the mode up front and exits 1 with the fix; `--plan`
  stays allowed. `init project` writes `on_complete` explicitly so the mode is
  never implicit.
- **Empty-queue diagnostics name the integration-branch rule.** Pickup syncs to
  the integration branch before selecting, so a node added on an unmerged branch
  is invisible and reads as "no actionable leaves". The diagnostics now say so
  and name the configured branch.

## [v0.1.4-rc1] - 2026-06-07

Release candidate (routes to **TestPyPI**). Adds the agent-driven task-loop
orchestration command **`specy-road grind-session`** (loop + read-only
dependency/wave planner) and makes `roadmap/registry.yaml` writes
yamllint-clean so unattended pickup does not trip a default yamllint
pre-commit hook.

### Added

- **`specy-road grind-session` — agent-driven task-loop orchestration.** A new
  command that wraps the existing primitives (`do-next-available-task` →
  implement → optional `--pre-finish-cmd` → `finish-this-task`) over many leaves
  until a stop condition (`--until` / `--under` / `--max-leaves` / no work). It
  never edits `roadmap/registry.yaml` itself — it shells out to the approved
  commands. Provides stable exit codes (0/1/2/3/4/5), `--json` events, and
  `--implement-mode {manual,hook}` (manual signal file or autonomous
  `--implement-cmd`). See [docs/grind-session.md](docs/grind-session.md).
- **`grind-session --plan` — read-only dependency/wave planner.** Reports ready /
  blocked / active leaves plus dependency **waves** and **parallel batches**
  (with `--json`), so a sub-agent orchestrator can dispatch independent work and
  avoid spawning a sub-agent for a wave whose dependencies are not yet met. Blocked
  leaves carry `waiting_on` (display ids) and a dependency-vs-gate reason.
- **IDE stub `/specyrd-grind-session`.** Installed for the dev role by
  `specyrd init`.

### Changed

- **Registry writes are yamllint-clean.** `roadmap/registry.yaml` is now written
  with indented block sequences (new `specy_road.registry_yaml` helper used by
  pickup, finish, abort, self-heal, and mark-reviewed), so unattended pickup no
  longer trips a default `yamllint` pre-commit hook.
- **Docs:** new [docs/grind-session.md](docs/grind-session.md); pointers from
  `dev-workflow.md` and `README.md`; clarified in `docs/toolkit-development.md`
  and `CLAUDE.md` that WIP→`dev` needs no PR for a solo maintainer (PRs required
  for `dev`→`main`).

## [v0.1.3] - 2026-04-25

Patch release. Publishes the post-`v0.1.2` release-readiness hardening:
the restored pre-release validation runbook, the completed three-app
user-testing pass, and a docs cleanup found by that pass. Routes to
**PyPI** via OIDC trusted publisher.

### Changed

- **Release runbook pre-release validation.** Restores the mandatory
  `WIP/pre-release-checks` branch before any `chore/release-*` branch,
  requires `suggested_prompts/` compliance + cleanup review before fix
  branches, and documents the three-app user-testing harness (ToDo,
  Calculator, personal notes) with PM CLI, dev CLI, and desktop PM GUI
  evidence requirements.
- **Install guide post-PyPI wording.** Removes stale "Stable PyPI
  pending" / TODO prose and makes `pip install specy-road` the primary
  end-user install path.

### Validation

- Completed the restored pre-release validation pass against the
  `v0.1.1..v0.1.2` delta plus current `dev` process-hardening changes.
- Exercised three disposable consumer repos with local bare remotes:
  ToDo, Calculator, and personal notes.
- Ran PM CLI authoring/validation flows, dev CLI pickup/finish/abort
  flows, and desktop PM GUI editing on the moderate Calculator roadmap.

## [v0.1.2] - 2026-04-25

Patch release. Ships the accumulated `WIP/improvements-0-1-2` work
since `v0.1.1`: PM Gantt modal/workspace usability improvements,
local-first roadmap refresh behavior, milestone-gate validation fixes,
task-list layout cleanup, and maintainer workflow documentation updates.
Routes to **PyPI** via OIDC trusted publisher.

### Added

- **Shared document editing from the PM Gantt UI.** Adds the shared
  markdown editor modal plus workspace-file API plumbing so shared docs
  can be opened and edited from the dashboard.
- **Window-like PM Gantt modals.** Task/shared-doc modals can be tiled,
  untiled, minimized, restored, resized from edges/corners, and use more
  of the viewport. The task editor also collapses the planning path block
  by default and tightens title/dependency header layout.
- **Local-first PM Gantt refresh behavior.** Roadmap responses support
  local-first updates and `view_fingerprint` polling so the UI can refresh
  view state without treating unrelated activity as an edit conflict.
- **PM Gantt remote-help affordance.** Adds Git remote help text focused
  on least-privilege PAT setup.

### Changed

- **Maintainer workflow docs.** Agent/docs/rules now clarify that the
  dogfood roadmap is a fixture and that topic work should branch from an
  active `WIP/improvements-x-y-z` line when one is in use.
- **PM Gantt parent-row presentation.** Parent rows use theme-aware grey
  styling and refreshed semantic rollup helpers.

### Fixed

- **Milestone gate validation.** Gates are allowed under milestones again,
  and PM API error text is aligned with the validated contract.
- **PM Gantt modal and task-list layout.** Fixes modal body scrolling,
  minimized dock alignment, the Untile label, and TipTap task-list checkbox
  alignment/CSS selectors; trims now-dead task-list DOM/CSS weight.

### Maintenance

- Refreshes bundled PM Gantt static assets and adds/updates coverage for
  workspace file editing, gate validation, parent status rollups, Gantt bar
  semantics, and `view_fingerprint` refresh behavior.

## [v0.1.1] - 2026-04-22

Patch release. Adds **automatic JSON chunk routing** so PMs and devs no
longer have to pick a chunk file by hand, plus the
**`specy-road rebalance-chunks`** power-user command for deterministic
re-packing. Backward compatible: repos that never overflow are
byte-identical. Includes README polish (post-PyPI install language) and
a small dead-code cleanup. Routes to **PyPI** via OIDC trusted publisher.

### Added

- **Automatic JSON chunk management.** Every roadmap write path
  (`specy-road add-node`, the PM Gantt's add-task action, and
  `edit-node` when growth would overflow) now goes through a
  deterministic chunk router. PMs and devs no longer have to pick a
  chunk file or split full chunks by hand: when the target chunk
  would exceed `roadmap_json_chunk_max_lines`, the router auto-routes
  to the smallest valid chunk in the same phase subtree, then
  anywhere in the manifest, then auto-creates a new chunk whose
  filename is derived from the new node's `node_key`
  (`<base-stem>__<6hex>.json`). Two PMs creating overflow chunks on
  parallel branches therefore never collide on chunk filenames —
  only the manifest gets a clean two-line addition. All chunk +
  manifest writes are snapshotted and rolled back atomically if
  validation rejects the result. `--chunk` on `add-node` is now
  optional (still honored when supplied). Backward compatible:
  repos that never overflow are byte-identical.
  (`feature/automat-json-chunking`)

- **`specy-road rebalance-chunks`** (optional power-user command).
  Re-packs chunks deterministically: groups nodes by phase ancestor
  in tree order, first-fit packs them into chunks of
  `<= roadmap_json_chunk_max_lines`, and applies the result
  atomically through the same plan/rollback machinery. Idempotent
  and not required for routine authoring. Supports `--dry-run`.
  (`feature/automat-json-chunking`)

### Changed

- **Milestone-lock awareness for chunk routing.** `specy-road add-node`
  now refuses to add a child under a parent that lives inside an
  `active` or `pending_mr` milestone subtree (matches the existing
  `cmd_edit` / `cmd_set_gate_status` / API guards — adding new work
  mid-milestone is a silent scope expansion). `specy-road rebalance-chunks`
  refuses with exit 1 when ANY milestone is in-flight (the cross-chunk
  reorganization is functionally a mutation under any locked subtree).
  Both errors point at `specy-road reconcile-milestone-status --apply`.
  (`fix/automat-chunking-finish`)

- **`specy-road add-node` lock-guard centralization.** The duplicated
  `assert_pm_nodes_not_milestone_locked → SystemExit(1)` block in
  `cmd_add` / `cmd_edit` / `cmd_set_gate_status` is consolidated
  into one helper (`_refuse_if_milestone_locked`) so the lock contract
  has one place to maintain. No behavior change for the existing
  guards.

### Fixed

- **`specy-road rebalance-chunks` idempotency** now reports
  `(repo is already balanced; nothing to do)` correctly in **both**
  dry-run and apply paths. Previous behavior fired the no-op message
  only when `plan.chunk_writes` was empty, but `build_pack_plan`
  always populates `chunk_writes` from scratch — so a balanced repo
  printed the per-chunk plan with `(N nodes, unchanged)` markers but
  not the no-op footer. Replaced with a content-equality check
  (`_is_noop_plan`) that compares each staged chunk write against the
  on-disk bytes plus the manifest ordering. Caught by Phase C.2 of
  the v0.1.1 e2e walk.

- **README post-PyPI staleness.** The "Getting started" sentence
  (line 23) still pointed at the clone+editable-install path even
  after v0.1.0 published the package to PyPI. The
  `post_release_readme_cleanup` script swapped the dedicated
  `## Install` block but missed this conversational sentence above
  it. Now reads: "follow `[Install](#install)` and
  `docs/install-and-usage.md` to `pip install specy-road` and run
  `specy-road init project` …"

### Maintenance

- Test suite: 513 → **534 passing** (+19 from the chunk-routing /
  rebalance feature, +2 from the milestone-lock gap audit).
- File-limits: one new override (`roadmap_crud_tests` to 600 lines)
  for `tests/test_roadmap_crud.py` — the 17 tests share helpers and
  splitting would force duplicating `_fixture_repo` / `_run_crud`
  across files. The runbook override (`release_runbook` at 800
  lines) from v0.1.0's Layer 1 is unchanged.
- Removed dead `run_validate()` in `roadmap_crud_ops.py` (its only
  caller was the cmd_add overhaul; the new `cmd_add` validates
  through the chunk router).
- `docs/roadmap-authoring.md` cross-references the chunk router and
  the milestone-lock interaction so the connection is discoverable
  the moment a PM reads about routing.

## [v0.1.0] - 2026-04-22

First **stable release** of `specy-road`. Promotes the work landed
across `v0.1.0-rc1` … `v0.1.0-rc4` plus the post-rc4 milestone-delivery
lifecycle, version-resolution policy, PM-Gantt UX improvements, and a
review-driven graceful-error-handling pass. Tagged `v0.1.0` on `main`;
the `release-publish` workflow routes the wheel to **PyPI** via OIDC.

### Added

- **Milestone delivery lifecycle (`milestone_execution`).** Roadmap
  parents may now carry an executable milestone state written to the
  chunk JSON: **`active`** (rollup branch open, subtree being worked),
  **`pending_mr`** (every structural leaf is `Complete`, awaiting the
  rollup MR), **`closed`** (rollup branch merged into integration,
  parent `status` synced to `Complete`). `start-milestone-session`
  writes the `active` block on the parent chunk so the lock is
  team-visible the moment it is committed. `finish-this-task` on the
  milestone rollup path auto-promotes `active → pending_mr` when the
  last leaf completes.

- **PM subtree lock.** While `milestone_execution.state` is `active`
  or `pending_mr`, both the CLI (`edit-node`, `set-gate-status`) and
  the PM Gantt API (`PATCH /api/nodes/{id}`, `DELETE`,
  `POST /api/outline/{reorder,move}`, `POST /api/nodes/{id}/{indent,outdent}`)
  refuse mutations under that subtree with a clear error / **409
  Conflict** that points the user at `specy-road reconcile-milestone-status`.

- **`specy-road reconcile-milestone-status`** CLI. Dry-run by default;
  `--apply` writes; `--fallback-head-delivery` accepts HEAD as the
  source of truth when remote-tracking refs cannot prove the rollup
  merge (typically: local-only merges or detached integration-branch
  flows). Each per-node application is isolated — one failing parent
  prints a structured warning and the loop continues; under `--apply`
  the script exits non-zero so orchestration can detect partial
  failure.

- **PM Gantt: Tiptap task lists** in the markdown editor with a new
  toolbar button and nested-checkbox CSS for both the editor surface
  and the rendered preview. Constitution modal markdown editors now
  size to content (no more 0-height collapse).

### Changed

- **`specy_road.__version__`** resolution policy: when the package is
  loaded from a tree that contains a sibling `pyproject.toml`
  declaring `name = "specy-road"`, the version is taken from that
  file — so editable checkouts and `specyrd init` stubs match
  `project.version` even when install metadata is stale. If there is
  no such file (e.g. a wheel-only install), use
  `importlib.metadata.version("specy-road")`. Otherwise the sentinel
  `0.0.0+unknown`. The lookup is hardened against a malformed
  `pyproject.toml` (catches `OSError` **and**
  `tomllib.TOMLDecodeError` / `ValueError`); `import specy_road`
  cannot crash on a broken file. Maintainer docs and Cursor rules now
  call out keeping tags, `pyproject.toml`, and `CHANGELOG.md` in
  lockstep.

- **Natural numeric sort for roadmap display ids.** `M1.2 < M1.10`
  (and any nested digit run) on every surface that orders roadmap
  rows: the export `roadmap.md` index, the `list-nodes` CLI, the PM
  Gantt outline, and the optimistic in-browser sort. Python and
  TypeScript implementations share the same key shape so the wire
  ordering matches the in-process ordering exactly.

### Fixed

- **`POST /api/outline/move` with an unknown `node_key`** is once
  again **400** with `unknown node_key '…'`. The
  milestone-lock-guard pre-lookup added during rc4 had regressed it
  to **404**; the original 400 contract (and the test that asserts
  it) is restored.

- **PM API milestone-lock guard** survives a transiently-broken
  roadmap. If `load_roadmap` fails (corrupt chunk, missing manifest,
  unreadable file) inside the lock-check, the route returns **409**
  with a "run `specy-road validate`" hint instead of leaking a bare
  500. The PM UI's transparent retry contract is wired for 4xx; a
  500 used to halt the retry loop.

- **PM Gantt mutation-fingerprint guard** survives an unreadable
  manifest. A corrupt `roadmap/manifest.json` now produces a
  **409** with `{message, error, retryable: false}` from the
  optimistic-concurrency dependency; previously it raised a
  `JSONDecodeError` and surfaced as a 500.

- **`start-milestone-session` re-entry guard.** Running the script a
  second time on a parent already in `active`/`pending_mr` refuses
  cleanly with the documented `reconcile-milestone-status` hint
  instead of silently overwriting the in-flight rollup metadata.

### Maintenance

- File-limits compliance: refactored `register_node_mutations`
  (90 → 13 lines; per-route handlers now live at module level) and
  `reconcile_milestone_status.main` (98 → 30 lines; per-node planner
  + emitter helpers extracted). No behavior change.

- Test suite: 480 → **495 passing**. New coverage for
  `__version__` resolution (×3), PM API milestone lock end-to-end
  (×5), graceful failure modes in lock-guard / fingerprint-guard
  (×4), per-node isolation in `reconcile-milestone-status` (×2),
  `start-milestone-session` re-entry guard (×1). Hardened the
  `_shared_catalog` cache-invalidation test against the
  same-nanosecond rewrite flake observed on fast tmpfs.

- Repo policy: `.cursor/rules/*.mdc` (7 rules) tracked in the
  repository — entry/load order, roadmap+registry discipline,
  do-next-available registry publish, change discipline, PM-Gantt
  ESLint stack, release/version/tag sync, and git-workflow
  management. `CLAUDE.md` is now tracked at the repo root; the
  `.gitignore` carve-out keeps IDE/agent state ignored while the
  policy remains version-controlled.

## [v0.1.0-rc4] - 2026-04-20

Fourth prerelease (TestPyPI). Adds dependency-aware briefs + LLM-review
prompt updates, gate status from the PM GUI + `set-gate-status` CLI,
PM Gantt focus-ring fix, optimistic-UI work for outline mutations,
narrow-fingerprint redesign for the GUI mutation guard (rooted in real
field repros), plus a Dependabot batch for `gui/pm-gantt/` (#40-#45).

### Added

- **Dependency-aware brief + LLM-review prompt.** `specy-road brief`
  now ships a new section, **`## 6. Dependency context (intent of
  upstream work)`**, that inlines each effective dependency's
  `## Intent` block (or `## Why this gate exists` for upstream
  gates) verbatim. Section numbers shift: Touch zones is now `## 7.`
  and Rollup semantics is now `## 8.`. Both LLM-review system
  prompts (feature sheet + gate sheet) are updated to scan section
  6 first and **drop sentences** in the revised planning sheet
  that paraphrase a dep's intent, allowing only a one-line
  clarification under `## Approach` (or `## Decisions and notes`
  for gates) when the dep's own intent doesn't cover something
  specific to this task. Workflow docs (`roadmap-authoring`,
  `dev-workflow`, `pm-workflow`, `pm-llm-review`, the consumer-
  scaffold `AGENTS.md`, and the planning-sheet templates) are
  updated to nudge authors away from duplicating dependency prose
  inside their planning sheets.
  (`feature/dependency-prompt-enhancement`)

- **Gate status from the PM Gantt UI** plus a new
  `specy-road set-gate-status <NODE_ID> --status <STATUS>` CLI for
  driving `type: gate` lifecycle from outside the dashboard.

- PM Gantt: optimistic UI for outline mutations. The dragged row snaps
  to its new position immediately and pulses blue while the server
  write completes; on success the pulse gracefully fades, on failure
  the row reverts and a brief red flash plays. Covers reorder,
  cross-parent move, indent/outdent, dependency-edit save, add-task
  (placeholder row appears with a `…` ID until the server assigns the
  real one), and delete. Visual treatment mirrors the existing
  `governance-pulse` styling on red-outlined header doc buttons,
  recolored to the accent blue. `prefers-reduced-motion` falls back to
  a static blue inset border. (`feature/optimistic-pm-ui`)

- `GET /api/roadmap` and `GET /api/roadmap/fingerprint` now return both
  `fingerprint` (the narrow outline-mutation token, used by mutating
  POSTs as `X-PM-Gui-Fingerprint`) and `view_fingerprint` (the broader
  change-detection token used by the polling refresh hook). Existing
  consumers that read `fingerprint` continue to work unchanged.
  (`fix/drag_and_drop`)

### Changed

- PM GUI mutation guard now validates a **narrow** fingerprint that
  only includes files whose change can actually invalidate the
  requested mutation: `roadmap/manifest.json`, every included roadmap
  chunk file, and `roadmap/registry.yaml`. Activity in `planning/`,
  `constitution/`, `shared/`, `vision.md`, git HEAD, or remote refs no
  longer shifts the token, so noise from IDE autosave, our own agents
  writing planning sheets, background `git fetch` / `merge --ff-only`,
  or files outside the user's window of attention can no longer reject
  a legitimate PM edit. The broad fingerprint is still emitted as
  `view_fingerprint` for the polling refresh hook (informational only —
  never causes 412). (`fix/drag_and_drop`)

- Every 412 from a mutating route still includes `retryable: true` and
  a `current_fingerprint`, so the bundled UI's transparent one-shot
  retry continues to absorb true conflicts (someone else actually
  modified a roadmap chunk) without showing the user a banner.

### Fixed

- PM Gantt drag-and-drop reorder, dependency edits, add/delete, and
  cross-parent move no longer fail with the "Roadmap or workspace
  changed elsewhere" banner. Field-reproduced root causes (both fixed):

  1. **JS Number precision on the fingerprint.** The optimistic-
     concurrency token routinely exceeds `2**53` (it's a sum of
     `mtime_ns` values, ~1e19). The server emitted it as a JSON
     number, so the browser's `JSON.parse` rounded to the nearest
     IEEE 754 `Number` and forwarded a slightly different value back
     as `X-PM-Gui-Fingerprint`. The server's exact int never matched
     → every mutation 412'd. Fix: `GET /api/roadmap`,
     `GET /api/roadmap/fingerprint`, and the 412 detail body now emit
     `fingerprint` (and `view_fingerprint`) as JSON strings; the
     bundled UI parses them as strings, stores as strings, and sends
     verbatim as the header. No precision involved end-to-end.

  2. **`rollup_status` rejected by older consumer schemas.**
     `load_roadmap` annotates each in-memory node with a derived
     `rollup_status` field. The on-disk chunk JSON never carries it,
     but `run_validation` was passing the in-memory document straight
     to schema validation. Older consumer schemas don't list
     `rollup_status` as an allowed property, so post-mutation
     validation rejected the document with "Additional properties
     are not allowed (`rollup_status` was unexpected)". Fix: strip
     derived per-node keys (mirrors `roadmap_chunk_utils._DERIVED_NODE_KEYS`)
     before schema validation.

  Plus: under-the-hood narrow-fingerprint redesign (mutating routes
  guard against only manifest+chunks+registry, not planning/shared/
  vision/git-HEAD) so noise from IDE autosave can no longer reject
  legitimate edits. (`fix/drag_and_drop`)

  Plus: PM Gantt planning markdown focus ring now aligns with the
  editor wrap (`fix(pm-gantt): align planning markdown focus ring
  with editor wrap`).

### Maintenance

- Batched Dependabot updates for `gui/pm-gantt/` (#40-#45):
  `vite` 8.0.8 → 8.0.9, `typescript-eslint` 8.58.2 → 8.59.0,
  `@tiptap/markdown` / `@tiptap/extension-link` / `@tiptap/react` /
  `@tiptap/starter-kit` 3.22.3 → 3.22.4. PM Gantt static assets
  rebuilt; bundle entry chunk 81 KB (well under the 900 KB budget).

## [v0.1.0-rc3] - 2026-04-18

Third prerelease (TestPyPI). CLI polish and roadmap dependency commands.

### Added

- CLI: `list-dependencies`, `set-dependencies` (`--clear` / `--deps`),
  `add-dependency`, and `remove-dependency`, using the same
  `edit_node_set_pairs` / validation path as the PM GUI
  `PATCH /api/nodes/{id}` dependency updates.

### Fixed

- Top-level `specy-road` no longer prints a `CalledProcessError` traceback
  when a pass-through bundled script exits non-zero (for example
  `archive-node` for an unknown id); the child script’s stderr message
  and exit code remain the contract.

### Changed

- Tests: `script_subprocess_env` prepends the repository root on
  `PYTHONPATH` so subprocess invocations of bundled scripts resolve
  `import specy_road` the same way the packaged CLI wrapper does.

## [v0.1.0-rc2] - 2026-04-18

Second prerelease (TestPyPI). Unifies `dev` with `main` for promotion PRs,
rolls up Dependabot bumps (#36), and updates README / install guidance for
stable PyPI vs TestPyPI.

### Changed

- CLI: `specy-road --help` exits 0 so release smoke-install (`set -e`) runs
  `validate` / `export` after `--help`.
- CI workflows: `actions/download-artifact` v8, `actions/github-script` v9,
  `softprops/action-gh-release` v3, `peter-evans/create-pull-request` v8.
- `requirements-ci.txt`: FastAPI 0.136.0.
- `gui/pm-gantt` devDependencies: ESLint patch, TypeScript patch.

### Documentation

- README and `docs/install-and-usage.md`: clarify stable PyPI vs TestPyPI
  prereleases.

## [v0.1.0-rc1] - TBD

First public release candidate. Published to TestPyPI for rehearsal.
v0.1.0 will follow on PyPI once a smoke install / smoke run confirms
the package wheel is correct.

### Added

- Roadmap-first coordination kit: scaffold (`specy-road init project`),
  validate, export, brief, the dev pickup loop
  (`do-next-available-task` / `mark-implementation-reviewed` /
  `finish-this-task`), and the PM Gantt FastAPI + React UI
  (`specy-road gui`).
- Auto-derive codenames from titles (with collision suffix from the
  node UUID); validate self-heals codenames and strips deprecated
  fields. Tasks created via `add-node` are pickup-eligible by
  default. (F-006, F-008)
- Comprehensive `specy-road brief`: a deterministic 7-section
  work-packet that inlines all relevant planning sheets and shared
  contracts so an implementing agent has everything in one document.
  (F-004)
- PR-body snapshot: when finishing a task with `--on-complete pr` (or
  `auto`), `finish-this-task` writes `work/pr-body-<NODE>.md`
  containing the dev-authored implementation summary plus the
  work-packet brief. The printed `gh pr create` / `glab mr create`
  command already references it via `--body-file` /
  `--description-file`. Snapshot semantics: the body does not
  auto-update if the roadmap evolves later. (F-015)
- PR-gating for downstream tasks when `on_complete: pr`: a leaf whose
  dependency has been picked up but whose PR has not yet merged is
  blocked from selection. (F-007)
- Self-heal stale registry claims: if `do-next-available-task` fails
  after registering a claim but before creating the feature branch,
  the claim is auto-rolled-back; if the rollback also fails, a
  structured warning names the node and the recovery command. (F-014)
- Computed ancestor `rollup_status`: a non-leaf is `Complete` only
  when every leaf descendant is. The CLI export, the JSON API, and
  the PM Gantt UI all read the same computed value; the API
  substitutes `status` with `rollup_status` on the wire so the
  prebuilt React bundle shows correct rollups without a rebuild.
  (F-013)
- Auto-stash work/ around the integration-branch registry commit
  (`do-next-available-task` and `mark-implementation-reviewed`) so
  the registry mutation lands alone, not polluted with feature-branch
  artifacts. (F-011)
- Consumer scaffold ships a `.gitignore` covering session-only files.
  (F-011)

### Changed

- `validate` is now a self-healing utility (silent fixes for missing
  codenames + deprecated-field scrubbing); `do-next-available-task`
  runs `validate` before pickup.
- `finish-this-task --on-complete merge` actually merges the feature
  branch into the integration branch and pushes; clear error if the
  integration branch ref is missing rather than a silent fall-through
  to PR instructions. (F-012)
- Touch zones are optional. The brief instructs the implementing
  agent to discover or confirm them via codebase scan if missing.
  (F-009)
- README: pre-release notice + `pip install` from-source steps until
  v0.1.0 ships. (F-001)
- Docs: consolidated three install-overlapping guides into
  `docs/install-and-usage.md` (end-user) and `docs/contributor-guide.md`
  (release process, branching, tagging, contributors). Removed
  `docs/setup.md`. (F-002)

### Removed

- `execution_subtask` and `agentic_checklist` fields. All leaf tasks
  are agentic by design; the schema, CRUD CLI, validate, brief, and
  export no longer reference them. Validate auto-strips them from
  any consumer roadmap that still has them. (F-003, F-007)
- `--no-git` flag from `specy-road sync`. Git with a configured
  remote is a hard dependency; the docs document the local-bare-remote
  pattern for purely-local trials. (F-010)
- `validate`'s warning about missing `origin/main` ref. specy-road
  only cares that `integration_branch` is declared; the rest is the
  user's git hygiene. (F-005)

[Unreleased]: https://github.com/shanevigil/specy-road/compare/v0.1.3...HEAD
[v0.1.3]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.3
[v0.1.2]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.2
[v0.1.1]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.1
[v0.1.0]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0
[v0.1.0-rc4]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc4
[v0.1.0-rc3]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc3
[v0.1.0-rc2]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc2
[v0.1.0-rc1]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc1
