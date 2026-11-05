# Implementation summary: M21.7 `steering-file-guard`

Executors can no longer change the files that steer harnesses and specy-road without it being noticed.
The work: detection after each turn, a refusal at finish, and per-file denies when a Claude Code executor launches. Nothing restores a changed file.

## Touch zones (final list)

The listed zones plus `specy_road/schemas/worker-record.schema.json`, which the coordinator added for the flag enum (1da375e1). Two new files sit **outside** the zones. Both are splits forced by the 400-line cap in `sr/constraints/file-limits.yaml`, which plain `specy-road file-limits` uses. Please add them to the zones:

- `specy_road/steering_gate.py`: finish's refusal (`zones_or_exit`, `steering_or_exit`, `steering_hits`) and the Claude Code denies (`claude_denies`). With them inside, `steering_paths.py` was 465 lines.
- `docs/orchestration-steering-files.md`: the steering-file list and its rules. `docs/orchestration-workers.md` was already at 400 lines. It now carries the list in short form, in its existing post-run paragraph (no lines added), and links to the new doc from that paragraph and its flag and reconcile rows.

`finish_task.py` was also at 400 lines. Its implementation-check call became one `zones_or_exit` call, which runs `implementation_or_exit` and then `steering_or_exit`, so the file did not grow.

## Acceptance

- **A1:** `specy_road/steering_paths.py` holds the list:
  - harness config and hooks, at the git root and the project root;
  - git hooks: `core.hooksPath` when set, else `<common>/hooks` and `<worktree-gitdir>/hooks`; direct entries with sha256, or `capped` past 200;
  - git config: the common `config` and `config.worktree`, read as bytes plus the watched keys, parsed without git;
  - the three policy files, in the tree and via `cat-file` at `refs/heads/<integration_branch>` (no fetch);
  - other leaves' registry `entries` items;
  - `work/reviews/` files except `<node>/READY-*`;
  - root shell startup files;
  - `env_setup.link` `bin/` entries: name, type, link text and `@sha256` of the resolved file.

  It snapshots these in the worker's worktree and in the main checkout. Entries are keyed by real path, so each is stored once. They are named project-relative in the worker's tree, git-root-relative outside its project, and absolute elsewhere (the main checkout and the git dir when the worker is in a linked worktree).
- **A2:** `close_turn` (through `_turn_findings`) compares the git snapshot first. On a change it adds a `git_probes_skipped` finding and runs no `git status`, `stash`, `merge-base` or blob read.
  - Each change is one `steering_file` finding with `path`, `class`, `before` and `after`. For `git_config`, both sides are the file digest followed by `;key=value` for each changed watched key (`unset` when the key is absent).
  - That finding replaces any `porcelain` or `committed_outside_zones` mention of the same path.
  - Symlinks come from the porcelain of both checkouts: a link that is new or retargeted during the turn and resolves outside the worker's git root is a finding.
  - The flag `steering_changed` is sticky: `close_turn` never clears it. It shows in `rec.flags`, which both `worker status --json` and `handoff status --json` `workers[]` emit via `to_dict`.
  - `worker reconcile` without `--dismiss` puts the steering findings recorded since the last reconcile into `delta.steering`. It prints one shell-quoted `path class before after` line per finding, then clears the flag.
- **A3:** `steering_or_exit` diffs against the merge base with `base_ref` and `changed_paths`, as the implementation check does. It refuses changes to harness, `policy_tree` and `shell_startup` paths unless a zone equals the path, in either its project-relative or git-root-relative form. `roadmap/registry.yaml` is not a finish class. The message names each path and gives `edit-node` and revert as the next steps.
- **A4:** `claude_denies` adds `--disallowedTools` with `Edit(./<rel>)` and `Write(./<rel>)` to launch and resume. It covers the in-tree steering files present at launch, plus `.claude/settings.json`, `.claude/settings.local.json` and the three policy files (with the project prefix). Exact zone paths are skipped, and there is no glob. A custom `channels.cli` returns before this, so its argv is unchanged. `orchestration-harness-launch.md` documents Cursor's built-in block and Codex `workspace-write`. `orchestration-review.md` "What the gate cannot stop" says what M21.7 adds and what stays with M20.
- **A5:** `tests/test_steering_file_guard.py` covers:
  - nine parametrized classes, each giving exactly one `steering_file` finding with no porcelain or `committed_outside_zones` mention of that path;
  - the `core.fsmonitor` sentinel: absent after the check, then created by a real `git status`, which proves the case is real;
  - a clean turn (its READY, its own registry entry, in-zone code) giving `[]`, while the flag stays set and reconcile lists the finding and then clears it;
  - the finish land/refuse pair together with the argv check;
  - a custom CLI command whose argv is unchanged.

  `specy-road file-limits` passes.

## Behaviour notes and limits

- **Two fixtures changed in setup only.** `tests/test_finish_merge_failure_undo.py` (`_repo`) and `tests/test_finish_work_cleanup.py` (`test_an_opted_in_completed_worker_goes_through_review_to_finish`) used to commit `roadmap/git-workflow.yaml` on the leaf branch. A3 now correctly refuses that. They now commit the config on `dev` and merge it into the leaf. No assertion changed.
- **Other writers show up too.** Other workers and the coordinator also write some steering paths during a turn (their own READY, review records and registry rows). Those writes are reported as well. The docs say so.
- **The next turn's start is not guarded.** It still runs `git status` (`git_state` in `TurnWatch.__init__`), and after a `core.fsmonitor` change that would run the changed command. The sticky flag and reconcile are the human's signal. Blocking a resume is not part of this leaf's acceptance.
- **Cost.** A snapshot of this repository (3,700 review files) takes about 0.5 s at each end of a turn.

## Added

- `specy_road/steering_paths.py`: the list, `Scope` and snapshots per class, `changes`, `SteeringWatch` with `git_changes`, `rest_changes` and `without_steering_paths`, and `config_values`, a no-git config reader. Required by A1 and A2.
- `specy_road/steering_gate.py`: `steering_hits`, `steering_or_exit` and `zones_or_exit` (A3), and `claude_denies` (A4). A file-limit split.
- `worker_turn_check._turn_findings`: compares git steering first, then runs or skips the git probes, then compares the rest and removes duplicates (A2). Adds a `git_probes_skipped` finding as the skip mark.
- `worker_turn_check.git_findings` gained an optional `after` argument, so the porcelain read once is reused for the symlink check.
- `TurnWatch.steering` and `steering_error`: the snapshot at turn start. A failure becomes a `check_error` finding and never loses the turn's record.
- `worker_reconcile.steering_findings`, `delta["steering"]` and the lines in `reconcile_lines`: required by A2.
- `FLAG_STEERING = "steering_changed"`: the schema enum value and its description sentence.
- `docs/orchestration-steering-files.md`: a file-limit split of the docs.
- Tests: `tests/test_steering_file_guard.py` covers A5. Helpers: `_layout`, a linked worktree with a linked `.venv` and a second worktree on `dev`; `_turn`, which brackets one turn with `TurnWatch` and `close_turn`; plus `_write`, `_registry_add_other`, `_commit_policy_from_second`, `_finish`, `_set_zones` and `_denies`. No mocks.
- `tests/test_finish_work_cleanup._config_on_dev`: keeps the changed test under the 80-line function cap, which the fixture fix above would otherwise have exceeded.
