# Implementation summary: M21.7 `steering-file-guard`

Executors can no longer change the files that steer harnesses and specy-road without it being noticed.
The work: detection after each turn, a refusal at finish, and per-file denies when a Claude Code executor launches. Nothing restores a changed file.

## Touch zones (final list)

The listed zones plus `specy_road/schemas/worker-record.schema.json`, which the coordinator added for the flag enum (1da375e1). Two new files sit **outside** the zones. Both are splits forced by the 400-line cap in `sr/constraints/file-limits.yaml`, which plain `specy-road file-limits` uses. Please add them to the zones:

- `specy_road/steering_gate.py`: finish's refusal (`zones_or_exit`, `steering_or_exit`, `steering_hits`) and the Claude Code denies (`claude_denies`). With them inside, `steering_paths.py` was 465 lines.
- `specy_road/git_config_text.py` (fix round 1): the git-config(1) text parser and include follower behind the git snapshot (R1); in `steering_paths.py` it would have pushed that file past 400 lines.
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

## Fix round 1 (review `gpt-6.1-sol-low` at c4d9c4de)

The `origin/WIP/improvements-0-3-1` merge went in first (5c0949a8), with no conflicts.

- **R1, class: git config read differently from how git reads it.** The line-based reader kept trailing comments, mishandled quotes and escapes, and never followed includes. As a result, the check watched a hooks directory git does not use. It is replaced by `git_config_text.parse_config`, which implements git-config(1) syntax. `read_chain` follows `include.path` and `includeIf.*.path` to git's depth of 10, without evaluating conditions, so the result is a superset of what git reads. `git_snapshot` hashes every file in that chain and watches each `core.hooksPath` value it sets, or the default directories when none is set. Still without running git.
- **R2, class: a per-checkout class implemented for only one checkout.** `review_file` read only the main checkout, and so did `env_bin`. Both now go through `scope.tops`, like the tree, git and registry classes. Entries are still keyed by real path, so the worker's linked `.venv` and its main-checkout source stay a single entry. The own-READY exemption applies in both checkouts.
- **R3, class: one path reached by two detectors.** Overlaps: a harness or shell file that is also a new escaping symlink, and a `core.hooksPath` inside `.claude/hooks` (git_hook plus harness), which before this fix came from two separate snapshots. These are no longer patched per detector. A single `SteeringWatch.merged` (it replaces `without_steering_paths`) keeps one `steering_file` per path, choosing the first class in `CLASSES` order. It also drops porcelain and committed-outside-zones mentions of that path.

## Probes

- `git config --file` (oracle) compared with `parse_config` for three `core.hooksPath` spellings: a trailing `#` comment; a quoted value containing `#` and `;`, followed by a `;` comment; an escaped `"` plus a backslash continuation. Result: equal, asserted in the new test.
- New tests run against the round-0 `steering_paths.py` and `worker_turn_check.py` in a scratch worktree. Result: all 5 new cases fail there (3 spellings, forged REVIEW in the worktree, escaping symlink at `.claude/settings.json`) and pass now.
- `core.hooksPath` set only in a file named by `[include] path`, with a hook written there during the turn. Result: one `git_hook` finding (probe script, not kept as a test).
- `core.hooksPath = .claude/hooks` with a hook written there. Result: one finding, class `harness`, with no duplicate `git_hook` (probe script).
- Every snapshot class against "both checkouts": tree, git, registry and symlink already covered both; reviews and env_bin were fixed here. `policy_blob` reads one ref shared by both, so it is correctly read once.
- Other parsers of git files in the change: `_gitdirs` reads only the `gitdir:` line and `commondir`. Result: no config syntax involved.
- Other merge points for findings: `_turn_findings` is the only place steering findings are combined. Result: it now ends in `merged`.
- Full suite after the merge: 5,032 passed. `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Fix round 2 (review `gpt-6.1-sol-low` at e84e9049)

The `origin/WIP/improvements-0-3-1` merge went in first, with no conflicts.

These findings are new input shapes of one open-ended problem: reading git config without running git. So rather than chase each shape, the fix states one bounded rule, in the `git_config_text` docstring, the `git_snapshot` docstring and docs/orchestration-steering-files.md.

The rule: what depends on the parse is bounded. A config file's change is always reported by the digest of its bytes. The hooks directories watched are `<common>/hooks` and `<worktree-gitdir>/hooks` always, plus every `core.hooksPath` value read. So a value read wrongly, or an `includeIf` condition left unevaluated, can only add a watched directory; it can never drop the default one. This is a deliberate superset of A1's "hooksPath when set, else the defaults".

- **R1, class: bytes git accepts before the syntax proper.** `parse_config` now drops a leading UTF-8 BOM. It is the only entry point, so files reached through includes get the same treatment.
- **R2, class: a hooks directory chosen by a condition the snapshot does not evaluate.** Removed by the rule above: the defaults are no longer replaced by a candidate value.
- **Test.** The parametrized hooks test has two new shapes: a BOM before the first section, and an `includeIf "gitdir:/nowhere/"` naming a hooksPath. It now asks git, run in the worker checkout with conditions evaluated, which hooks directory is in use, and writes the hook there. It requires exactly one `git_hook` finding with that exact path, plus `git_probes_skipped`.

## Probes (round 2)

- The new BOM and nonmatching-include cases, run against round-1 `steering_paths.py` and `git_config_text.py` in a scratch worktree: both fail there and pass now. (A first version of the BOM case passed on round-1 code, because the BOM did not precede the hooksPath section; the test now puts that section first.)
- Git accepts a BOM-prefixed config: the test's `git config --get core.hooksPath` returns the directory.
- Other readers in the change that could meet a BOM: `yaml.safe_load` of the registry handles one (probe returned the parsed entries). The `.git` gitdir line and `commondir` are written by git itself and carry none.
- Other decisions taken on a parsed value: the hooks directories (now a superset) and which includes are followed (already every one, conditions not evaluated). Displayed `;key=value` values only describe a finding; detection is by digest.
- Targeted tests: 104 passed. `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Fix round 3 (review `gpt-6.1-sol-low` at 3d391a47)

The `origin/WIP/improvements-0-3-1` merge went in first (registry rows only), with no conflicts.

- **R1, class: coverage decided by my own git-config parser.** This is the third input shape of the same open-ended problem (comments, then a BOM, now a CRLF continuation). The fix removes the parser from the decision instead of patching the shape. At the turn's start, before the executor acts, `git_config_text.git_reads` asks git itself which hooks directory it uses (`rev-parse --git-path hooks`). It also asks which config files it reads (`config --list --show-origin --includes`: global, system, local, worktree and their includes, with conditions evaluated). `scope_for` stores the answer in `Scope.git_known`. After the turn those files and directories are compared from the filesystem only, as before. The parser only adds candidates: the defaults, every `hooksPath` value and every include, unevaluated. It also now reads CRLF as LF, as git's reader does.

  The one bounded rule and its limit are in the `git_config_text` docstring and in docs/orchestration-steering-files.md ("What git is asked, and when"): a directory or file git would use only because of a change made during the turn is not watched itself; the change is, by its file's digest. The reviewer's flagged claim ("parsing errors can only add watched directories") is removed from the docs and the docstrings.
- **R2, class: the check falls through to the unsafe path when its own baseline is missing.** `_turn_findings` now fails closed in one place. A missing start snapshot and a failed git-steering comparison raise into the same `except`, which records `check_error … git probes skipped` and runs no git command. The separate `sw is None` branch is gone, so the function has fewer branches than in round 2.

  Its sources of failure were also audited and fixed. Every `.resolve()` on an executor-controlled path became `_resolved` (`os.path.realpath`, which never raises): gitdir, commondir, hooksPath, `env_setup.link` bin and porcelain links, where a link loop raised `RuntimeError` on Python 3.11. A registry whose `entries` is not a list no longer raises (the reviewer's trigger).

## Probes (round 3)

- The new `crlf_continuation` shape and `snapshot=unavailable` case, run against round-2 `steering_paths.py`, `git_config_text.py` and `worker_turn_check.py` in a scratch worktree: both fail there and pass now.
- A `hooksPath` that only git knows: set in a global config through `GIT_CONFIG_GLOBAL`, which the parser never reads. A hook written there gives one `git_hook` finding plus `git_probes_skipped`, so coverage no longer depends on the parser (probe script).
- `entries: 42` in the worker's registry plus a symlink loop in the main `.venv/bin`: `TurnWatch` still takes its snapshot (`steering_error` None) (probe script).
- `git config --list --show-origin --name-only -z` output shape (origin and name pairs, origins relative to the checkout) checked on git 2.43 before relying on it.
- Every `.resolve()` in `steering_paths.py`: 0 left. Other raising paths: `_value`, `_hooks_dir`, `tree_files` and the env_bin `iterdir` already catch `OSError`.
- Every place that takes a git-steering decision: `git_snapshot` (now git-named plus candidates) and `_turn_findings` (now one fail-closed `except`). `rest_changes` runs only after that gate.
- Full suite: 5,036 passed. `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

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
- Fix round 1: `git_config_text.py` (`parse_config`, `read_chain`, and helpers `_eol`, `_section`, `_value`, `_includes`) for R1. `steering_paths.watched_values` replaces `config_values` (display only). `SteeringWatch.merged` replaces `without_steering_paths` (R3). Tests: the parametrized `test_a_hook_in_the_configured_hooks_path_is_found_however_git_config_spells_it` (R1, with git as oracle); two new `CASES` entries, `forged_review_in_worktree` (R2) and `escaping_symlink_at_harness_path` (R3), plus the `_link` helper; the clean turn also writes its own READY in the worker checkout (R2 exemption).
- Fix round 2: no new helpers. The leading-BOM strip in `parse_config` and the superset in `git_snapshot` replace the earlier "hooksPath else defaults" choice. The round-1 test `test_a_hook_in_the_configured_hooks_path_is_found_however_git_config_spells_it` became `test_a_hook_in_the_hooks_directory_git_uses_is_found_however_the_config_reads`, with five shapes and git deciding the directory in use.
- Fix round 3: `git_config_text.git_reads` (git, at turn start only) and `Scope.git_known` (R1); `steering_paths._resolved`, which never raises; the CRLF line in `parse_config`. Tests: the `crlf_continuation` shape in `HOOKS_CONFIGS`, and the fsmonitor test parametrized over `snapshot` (`taken` / `unavailable`; the latter makes the public `steering_paths.file_snapshot` raise with monkeypatch, R2).
- `tests/test_finish_work_cleanup._config_on_dev`: keeps the changed test under the 80-line function cap, which the fixture fix above would otherwise have exceeded.
