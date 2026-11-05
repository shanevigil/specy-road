# Implementation summary: M15.21

Linked worktrees: commands resolve the enclosing worktree, and `env_setup` handles symlinked environments.

## Final touch zones

As widened by the coordinator (WIP 17af42ad): `specy_road/runtime_paths.py`, `specy_road/worker_ops_launch.py`,
`specy_road/worktree_env.py`, `docs/orchestration-worktrees.md`, `tests/`,
`specy_road/templates/project/schemas/git-workflow.schema.json`, `specy_road/bundled_scripts/doctor_env_setup.py`,
`specy_road/worker_ops_message.py`. All changes fall inside these zones.

Not changed (outside the zones, so a follow-up):
- `sr/schemas/git-workflow.schema.json`: this checkout's own copy of the schema. It does not have `link` yet.
- `docs/git-workflow.md`: its "Worktree environment (`env_setup`)" section still describes `{cmd, copy}` only.
  The new `docs/orchestration-worktrees.md` covers `link`.

## A1: the enclosing worktree wins

- `runtime_paths.project_root`: when `SPECY_ROAD_REPO_ROOT` is set, `enclosing_worktree_root` asks git
  (`rev-parse --path-format=absolute --show-toplevel`, then a separate `--git-common-dir` query, each read as
  bytes by `git_path`, fix round 2) for the worktree top and common dir of
  both the working directory and the named path. If they are different worktrees with the same common dir, it
  returns the same project-relative path in the working directory's worktree, even when that directory is
  missing there (rework R4: the command then fails on that path; it is never sent back to the main checkout).
  It prints nothing. If the working directory is in another repository, outside git, or in the same worktree, the
  named path is returned as before.
- `worker delegate` (`worker_ops_launch.worker_env`) sets `SPECY_ROAD_REPO_ROOT` in the harness environment to
  the worker's project root (`<worktree>/<prefix>`). It uses the `Launch.env` overlay, which the wrapper
  applies over `harness_env`. `worker message` and `resume` (`worker_ops_message._send`) set it the same way,
  so a resumed turn keeps it.
- Test: `ready` runs in a linked worktree with no `--repo-root`, the variable naming the main checkout, and cwd
  in the worktree. It writes a valid READY at the worktree's HEAD. Red-green: without the `runtime_paths`
  change this test fails (exit 1), because it resolves the main checkout on `dev`.

## A2: `env_setup.link`

- Schema: `env_setup.link` is an array of `envSetupPath`.
- `worktree_env.link_into` symlinks each path from the main checkout's project root to the same
  project-relative path in the new worktree. The steps run in order: copy, then link, then cmd. The source is
  bounded by the main checkout's git root. The target (`link_target`) has its parent resolved and bounded by the
  leaf worktree, so a symlinked directory on the way cannot carry the link out (rework R1); its final component
  is not followed, so an existing or dangling link there is still refused. A missing source, or a target
  that already exists, stops with the usual "worktree stays" note. Then `exclude_links` appends an anchored
  `/<git-root-relative path>` line (`exclude_pattern` escapes `\ * ? [` and trailing spaces, rework R2), if
  not already there, to the file `git rev-parse --git-path info/exclude`
  names. Git keeps that file in the common git dir, so it is shared by every worktree and the main checkout.
  There the line matches the real, already-ignored directory.
- `worker delegate`'s clean-tree check also skips a `??` entry that is a declared link path **and** a symlink
  resolving to that path in the main checkout (`linked_status_paths`, rework R3), so a symlink made by hand in an
  existing worktree does not block a launch, while an ordinary file or directory of that name still does.
- `doctor` lists links (`; link a, b`, only when set) and reports a missing or out-of-bounds link source as an
  error, as it does for copy sources.
- Test: `.gitignore` holds `node_modules/` and `.venv/` (directory-only patterns). After setup,
  `git status --porcelain --untracked-files=all` is empty in both the worktree and the main checkout.

## A3: docs

New `docs/orchestration-worktrees.md`. It covers root resolution, where `env_setup` lives
(`roadmap/git-workflow.yaml` at the project root), the command and link forms, why links go in
`info/exclude` (common dir), and that copying environments is out of scope.

## Rework (review by `gpt-6.1-sol` of 063ec92a)

- R1 (class: a write through a symlinked path component): `link_target` resolves the parent before bounding.
- R2 (class: a literal name written as a git pattern): `exclude_pattern` escapes pattern syntax; a name with a
  newline is refused, since no exclude line can hold it.
- R3 (class: an exemption decided by name, not by what is on disk): the exemption needs a symlink to the source.
- R4 (class: falling back to the named checkout): the enclosing worktree's path is returned even when missing.
- R5 (class: assertions on how often a mock was called): `len(launches) == 1` is now an active worker record
  (`active_for_node`); `[launch] = launches` in the delegate-env test is now `launches[-1]`.
- Red-green: the four new regression tests fail (4 failed) with `worktree_env.py` and `runtime_paths.py` at
  063ec92a, and pass with the fix.

## Fix round 1: link invariants

The record blocks 063ec92a. R1 to R5 were fixed in a48cbf2b and 2762aa1b, before this round's message
arrived. This round merged `origin/WIP/improvements-0-3-1` (6ad03fcd, clean), widened the escape set, and
pinned the listed inputs with tests (a0355639).

Invariants, each held by one function every caller goes through:
- Write containment (R1): `link_target` resolves the destination's parent and refuses it outside the leaf
  worktree; the final component is not followed, so an existing or dangling link there is refused by the
  `exists`/`is_symlink` check. Test: `test_link_refuses_a_parent_that_is_a_symlink_out_of_the_worktree`
  (`assets` -> external directory: refused, external directory stays empty).
- Exemption scope (R3): `linked_status_paths` exempts a path only when it is a symlink whose resolved target
  equals the declared source's resolved path. Test, through `worker delegate`:
  `test_delegate_refuses_an_ordinary_file_with_a_declared_link_name` (refused, no worker record, file kept);
  `test_delegate_ignores_a_declared_link_made_by_hand` (a real link is still exempt).
- Literal ignore lines (R2): `exclude_pattern` escapes `\ * ? [ ] ! #` and trailing spaces; each line starts
  with `/`, so none can begin with `!` or `#`. Test: `test_link_excludes_a_name_with_pattern_characters_literally`
  (`env[1]`, `a*b?`, `!bang`, `#hash`, `c]d`, `e\\f`: status clean; `env1` and `aXbY` still untracked).
  `]`, `!` and `#` were already literal in that position; they are escaped so the rule doesn't depend on position.
- Root resolution (R4): `enclosing_worktree_root` returns the enclosing worktree's path even when it is missing
  there, so it never redirects to the main checkout. Test:
  `test_a_project_missing_from_the_enclosing_worktree_is_not_redirected_to_the_main_checkout`.

Other inputs checked:
- A link whose source is missing: refused, "does not exist" (`test_link_refuses_a_missing_source_and_a_path_past_the_git_root`).
- A source that is itself a symlink: inside the git root, linked to the resolved target, and the delegate
  exemption accepts it; pointing past the git root, refused and nothing linked
  (`test_a_source_that_is_a_symlink_links_its_resolved_target`).
- An absolute path in `link:`: the schema (`^(?!/)`) rejects the config, so setup does nothing; with the schema
  bypassed (`link_into` directly), `link_target` refuses it and nothing is written
  (`test_an_absolute_link_path_is_refused_by_the_schema_and_by_the_link_guard`).
- `..` in `link:`: `node_modules/..` (the worktree top) and `../escape` (past the git root) are refused and the
  worktree is unchanged (`test_link_refuses_dot_dot_out_of_place`).
- A nested project prefix (`sr/`): `link: [node_modules, ../.venv]` writes `/sr/node_modules` and `/.venv`, and
  the delegate exemption names them the way `git status` does
  (`test_link_in_a_nested_project_excludes_git_root_relative_lines`).

## Fix round 2: path parsing

Class: a filesystem path read from git output as text, then split on newlines or stripped. A checkout named
`main\ncheckout` turned the two-line `--show-toplevel --git-common-dir` answer into three lines, so
`_worktree_and_common_dir` returned `None` and `project_root()` fell back to the named main checkout.

Design: `runtime_paths.git_path` asks git for one value per call. It reads stdout as bytes, removes only git's
single trailing newline, and decodes with `os.fsdecode`. It spawns git itself, because
`git_subprocess.run` decodes as text and `git_subprocess.py` is outside the touch zones. That module's
docstring list of callers that spawn git themselves does not name this one yet: a follow-up outside the zones.

Every git call this leaf added or touched:
- `runtime_paths._worktree_and_common_dir` (`--show-toplevel` + `--git-common-dir` in one call, `splitlines`):
  the reported bug; now two `git_path` queries.
- `worktree_env.exclude_links` (`--git-path info/exclude` via `git_text`, which strips): not split, but a path
  ending in whitespace would lose it; now `git_path`.
- `worker_ops_launch._launch_locked` / `linked_status_paths` (`status_entries`): already `-z`, NUL-separated;
  unchanged.
- `worker_ops_launch.worker_env`, `worker_ops_message._send`, `doctor_env_setup`: no git calls added.
- `worktree_env.git_top`: walks the filesystem for `.git`, no git output; unchanged.

Test: `test_a_checkout_path_with_a_newline_resolves_the_enclosing_worktree`, Sol's exact input (main checkout
`main\ncheckout`, cwd in its linked worktree `lane`, the variable naming main): `project_root()` returns `lane`
and prints nothing. The same test runs `setup_worktree_env` with `link: [node_modules]` there, so the exclude
file under `main\ncheckout/.git` is found and the lane's status is clean. Red-green: with `runtime_paths.py` and
`worktree_env.py` at 0ed4797c the test fails (`project_root()` returns `main\ncheckout`).


- Link target with `assets` symlinked out of the worktree: refused, nothing written outside (test).
- Copy targets: already bounded by a full `resolve()` (`bounded_path`), so a symlinked parent or final component
  pointing out is refused; unchanged.
- Link and copy sources: bounded by a full `resolve()` against the main checkout's git root; unchanged.
- Link target `x/..` and the worktree top itself: refused by `link_target`.
- `mkdir` of the link's parents: runs only after the resolved parent is bounded.
- Exclude lines for `env[1]` and `a*b?`: status clean after setup, and `env1` / `aXbY` still untracked (test).
- Other places writing a git pattern in this change: none besides `exclude_pattern`.
- `git status` path quoting for odd names: `status_entries` uses `-z`, so the compared path is literal.
- Delegate with an ordinary file named `node_modules` declared under `link`: refused, no worker record, file kept (test).
- Delegate with a hand-made symlink to the main checkout's `node_modules`: still accepted (existing test).
- Other exemptions in the clean-tree check (`_bookkeeping`, `in_nested`): not part of this change; unchanged.
- `worker_turn_check` (`status_entries` after a turn, outside the zones): does not use the link exemption; unchanged.
- `enclosing_worktree_root` with the project directory missing in the lane: returns the lane path (test).
- Its other `return named` branches (cwd outside git, named path missing or outside git, same worktree, other
  common dir): the cases A1 says keep today's behaviour; unchanged.
- Other mock call counts in `tests/test_linked_worktrees_root.py`: the `[launch] = launches` unpack; replaced.

- Fix round 2, other git path reads not touched by this leaf: `runtime_paths.git_root` and `project_prefix` use
  `git_text` (strip only, no split), so a newline inside a path survives; they predate this leaf and stay unchanged.
- Fix round 2, `main_project_root` / `reviews_root` with a `main\ncheckout` checkout: resolves (the newline test's
  setup step passes).
- Fix round 2, `exclude_links` reads exclude file lines with `splitlines`: those are patterns, not git output, and a
  link name with a newline is refused, so no line holds one.

## Probes

R1 class: a filesystem path read from git output as text, then split on newlines or stripped.

- `_worktree_and_common_dir` combined `--show-toplevel --git-common-dir` with `splitlines`: reproduced wrong root with checkout name `main\ncheckout`; fixed with two `git_path` queries.
- `worktree_env.exclude_links` (`--git-path info/exclude` via `git_text`): trailing whitespace on the path would be lost; now `git_path`; exclude file found under `main\ncheckout/.git` in the newline test.
- `worker_ops_launch` clean-tree (`status_entries`, `-z`): NUL-separated paths; safe; unchanged.
- `runtime_paths.git_root` / `project_prefix` (`git_text`, strip only): embedded newline in path survives; pre-leaf; unchanged.
- `exclude_links` reading `info/exclude` with `splitlines`: file content is patterns, not git path output; link names with newlines refused at setup; fixed in fix round 3 for vertical tab (see below).
- Public `project_root()` from linked worktree `lane` with `SPECY_ROAD_REPO_ROOT` naming `main\ncheckout`: returns `lane`, silent (test `test_a_checkout_path_with_a_newline_resolves_the_enclosing_worktree`).

## Fix round 3: `info/exclude` line records

Class: treating `info/exclude` body as Unicode line-oriented text via `str.splitlines()`, which splits on vertical tab and other breaks that are legal inside one gitignore pattern.

Design: `info_exclude_lines` splits on LF only; `exclude_links` appends new patterns without rewriting existing file bytes.

## Fix round: probes

- `str.splitlines()` on `/env\x0bodd`: two records (`/env`, `odd`); reproduced sol-low R1; fixed with LF-only split and append-only writes.
- Second `setup_worktree_env` on another worktree after `link: [env\vodd]` on the first: first lane stays clean (test `test_a_second_setup_does_not_corrupt_exclude_lines_with_vertical_tab`; probe `probe-gpt-6.1-sol-low.py`).
- `exclude_links` duplicate guard still uses exact line equality on LF-split records; unchanged behaviour for normal names.
- Git path reads (`git_path`, two queries): newline in checkout dirname; fix round 2; unchanged this round.
- Link names with `\n`/`\r`: still refused at `link_target`; no exclude line can hold them; unchanged.
- Tests asserting exclude content via `splitlines()` (`test_link_in_a_nested_project_excludes_git_root_relative_lines`): patterns are normal path segments without vertical tab; still valid.

## Verification

- Full suite `pytest -n 4`: 4035 passed (after the rework).
- Targeted pytest (16 files, `-n 4`): 190 passed (first round).
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean. `setup_worktree_env` and `report_env_setup` went over the
  C901 limit; I split out `link_into` and `_missing_sources` to bring them back under it.

## Added

- `runtime_paths.git_path`: one path from git, read as bytes and decoded with `os.fsdecode` (fix round 2).
- `runtime_paths._worktree_and_common_dir`: a checkout's worktree top and common git dir, two `git_path` queries (A1, fix round 2).
- `runtime_paths.enclosing_worktree_root`: the A1 rule (same common dir, different worktree → the enclosing one).
- Branch in `project_root`: the env-var value goes through `enclosing_worktree_root`.
- `worker_ops_launch.worker_env`: adds `SPECY_ROAD_REPO_ROOT=<worker project root>` to a `Launch.env` (A1, delegate).
- Call in `worker_ops_message._send`: resumed turns get the same variable as the first turn.
- Guard in `_launch_locked`'s clean-tree check: `??` entries that are declared link paths are not dirty (A2).
- `worktree_env.link_paths`: reads `env_setup.link`.
- `worktree_env.linked_status_paths`: link paths as `git status` names them, for the delegate guard; only those
  that are symlinks resolving to their main-checkout source (rework R3).
- `worktree_env.link_target`: the link's place in the leaf, parent resolved and bounded, final component not
  followed; refuses `..`, the worktree top and newlines (rework R1, R2).
- `worktree_env.exclude_pattern`: escapes gitignore pattern syntax (`\ * ? [ ] ! #`, trailing spaces) in an exclude line (rework R2, fix round 1).
- `worktree_env.info_exclude_lines`: LF-only records from `info/exclude` (fix round 3; avoids `splitlines()` breaking on vertical tab).
- `worktree_env.exclude_links`: appends anchored exclude lines to the common `info/exclude` (A2); append-only, no rewrite (fix round 3).
- `worktree_env.link_into`: makes the symlinks, with bound/missing/exists guards (A2). It was split out of
  `setup_worktree_env` for C901.
- `bounded_path(verb=...)`: so a link refusal says "cannot link", not "cannot copy".
- `doctor_env_setup._missing_sources`: copy and link source checks, split out of `report_env_setup` for C901.
- Doctor output: a `; link …` line segment, and missing link sources reported as errors.
- Schema: `env_setup.link` property.
- Mocks: `_capture_spawn` in the new tests replaces `worker_ops_launch.spawn` and `acquire_lease`, so delegate's
  launch is captured without starting a harness or touching a remote.
- Tests (`tests/test_linked_worktrees_root.py`):
  - `test_ready_in_a_linked_worktree_with_the_variable_naming_the_main_checkout`: A1's required test.
  - `test_the_enclosing_worktree_is_resolved_silently`: a nested path is kept, nothing is printed, and the main
    checkout is unchanged.
  - `test_a_working_directory_in_another_repository_keeps_the_variable`: today's behaviour outside the repository.
  - `test_delegate_sets_the_variable_to_the_workers_worktree`: delegate's environment.
  - `test_link_symlinks_the_environments_and_leaves_the_worktree_clean`: A2's required clean-status test.
  - `test_link_refuses_a_missing_source_and_a_path_past_the_git_root`: link guards.
  - `test_doctor_lists_the_links_and_a_missing_source`: doctor reporting.
  - `test_delegate_ignores_a_declared_link_made_by_hand`: the clean-tree guard, which needs no exclude line;
    now asserts an active worker record instead of a spawn count (rework R5).
  - `test_delegate_refuses_an_ordinary_file_with_a_declared_link_name`: rework R3, through delegate.
  - `test_a_project_missing_from_the_enclosing_worktree_is_not_redirected_to_the_main_checkout`: rework R4.
  - `test_link_refuses_a_parent_that_is_a_symlink_out_of_the_worktree`: rework R1, no external write.
  - `test_link_excludes_a_name_with_pattern_characters_literally`: rework R2, clean status and exact-name match
    (fix round 1 adds `!`, `#`, `]` and `\`).
  - `test_link_refuses_dot_dot_out_of_place`: fix round 1, `..` entries.
  - `test_an_absolute_link_path_is_refused_by_the_schema_and_by_the_link_guard`: fix round 1, absolute entries.
  - `test_a_source_that_is_a_symlink_links_its_resolved_target`: fix round 1, symlinked sources.
  - `test_link_in_a_nested_project_excludes_git_root_relative_lines`: fix round 1, nested prefix.
  - `test_a_checkout_path_with_a_newline_resolves_the_enclosing_worktree`: fix round 2, newline in a checkout path.
  - `test_a_second_setup_does_not_corrupt_exclude_lines_with_vertical_tab`: fix round 3, shared exclude append (sol-low R1).
