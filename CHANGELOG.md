# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The release-publish workflow extracts the section for the release tag
(matched by `## [vX.Y.Z]` heading) and uses it as the GitHub Release
body. Keep section bodies focused; link to PRs for detail.

## [Unreleased]

### Added

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

### Removed

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

[Unreleased]: https://github.com/shanevigil/specy-road/compare/v0.1.0-rc3...HEAD
[v0.1.0-rc3]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc3
[v0.1.0-rc2]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc2
[v0.1.0-rc1]: https://github.com/shanevigil/specy-road/releases/tag/v0.1.0-rc1
