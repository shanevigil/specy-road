# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The release-publish workflow extracts the section for the release tag
(matched by `## [vX.Y.Z]` heading) and uses it as the GitHub Release
body. Keep section bodies focused; link to PRs for detail.

## [Unreleased]

### Added

### Changed

- PM GUI mutation guard: every 412 from a mutating route now includes
  `retryable: true` and a `current_fingerprint` value freshly recomputed
  *after* re-running the same auto-fetch / `merge --ff-only` side
  effects the GET endpoints run. This lets the bundled PM Gantt UI
  transparently retry the mutation exactly once with the fresh token
  before showing the "Roadmap or workspace changed elsewhere" banner.
  Behavior is on by default — drag-and-drop reorder/move now "just
  works" when several PMs are editing concurrently, without any env
  flag or operator action. (`fix/drag_and_drop`)

### Fixed

- PM Gantt drag-and-drop reorder (`POST /api/outline/reorder` and
  `POST /api/outline/move`): no longer fails spuriously when the
  toolkit's own background `git fetch` + `merge --ff-only` happens to
  run between the GET that issued the client's token and the POST
  that uses it. Both `GET /api/roadmap` and `GET /api/roadmap/fingerprint`
  now go through a shared `_pm_gui_finalize_state` helper so the
  invariant "auto-FF runs before fingerprint is computed" cannot
  drift. (`fix/drag_and_drop`)

### Removed

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

[Unreleased]: https://github.com/shanevigil/specy-road/compare/v0.1.0-rc1...HEAD
[v0.1.0-rc1]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc1
