# Implementation summary: M21.40 (upgrade-scratch-git-env-sterile)

## What changed

- `ignore_report.scratch_git_env(isolate=None)` drops every `GIT_` variable (`_REPO_ENV` is gone). With `isolate` it
  sets `GIT_CONFIG_NOSYSTEM=1` and `GIT_CONFIG_GLOBAL=<isolate>/empty-gitconfig`.
- `git_subprocess.run` gains `env=` (`None` inherits, as before; the 60 s default stays).
- `upgrade_generated.scratch_environ(tmp)` installs the isolated environment and yields the caller's prefix-stripped
  environment for the live `ls-files`. `_dry_run` now runs entirely inside it, the plan stage included.
- Mirror `git init`, `add`, `commit` and `ls-files` go through `git_subprocess.run`. Init uses an empty template
  directory, and init, add and commit pass `-c core.hooksPath=<empty dir>`.
- A failed scratch call raises `GitFailed`; `run_upgrade` prints `error: <message>` to stderr and returns 2 before the
  plan is applied or validate runs. `ls-files`: exit 1 is untracked, anything else aborts before a generated file.
- docs/install-and-usage.md, CHANGELOG [Unreleased] Fixed, and the `upgrade.py` docstring are updated.

Touch zones were accurate: only the nine listed files changed, and no new module was needed.

## Decisions the reviewers should check

1. **`-c core.fsmonitor=false` on the live `ls-files` (not in the brief).** A1 keeps the caller's config on that call,
   but A3's HOME row needs no marker, and `git ls-files` itself fires a global `core.fsmonitor` (checked on git 2.43).
   Passing this one override satisfies both: `safe.directory` and all other config still apply. Without it the HOME
   test fails (red check 3).
2. **The plan stage is isolated too, through `ignore_report.isolate_git` (not in the brief).** The refresh's ignore
   note runs `ls-files` in the plan's mirror, which also fires a global `core.fsmonitor`. Inside `scratch_environ`,
   `_git`'s plain `scratch_git_env()` would strip the isolation back out, so `_git` passes a module-level scratch path
   that `scratch_environ` sets and clears. Without it the HOME test fails (red check 2).
3. **Unreadable files stay out of `git add` (not in the brief).** `add --ignore-errors` exits 1 on an unreadable file,
   which under A2 would turn `test_an_unreadable_agents_md_fails_alike_in_both` into exit 2. Rather than exempt exit 1,
   the Mirror records those files and `add` excludes them by pathspec, so A2's rule holds with no exception. They were
   already absent from the copy's index, because add failed on them.
4. **The `.git`-exists check is kept, not replaced.** The brief says to replace it, but
   `test_a_dry_run_whose_copy_has_no_git_validates_nothing` (M21.16) removes `.git` after a successful init and asserts
   `git init failed in the temporary copy`. It stays as one guard beside the result check; deleting it would mean
   rewriting that test, and `add` could then reach a repository above the copy.
5. **`ls-files` wording.** In a dry run the error uses A2's literal `the temporary copy`, although the call runs in the
   checkout. In a real run there is no copy, so it says `the checkout`.

## Behaviour changes and limits

- **Non-git project:** `ls-files` exits 128 outside a repository, so `upgrade` in a directory with a manifest but no
  git now exits 2 at `regenerate` (it used to read that as untracked). A2 requires this for any exit other than 0 or 1,
  and 128 cannot be told apart from a real failure. No test covers such a project.
- **Real run's plan mirror:** its `git init` is isolated, but a failed init there is still ignored as today, and `_git`
  in that mirror still reads the caller's global config. A1 and A3 scope the isolation to the dry run.
- **Dry-run ignore note:** it no longer sees a global `core.excludesFile`, so it can differ slightly from the real run.
  It is advisory.
- **`init.defaultBranch`:** the copy no longer reads it from global config, so its branch is git's default. All tests
  pass with this.

## Verification

- `tests/test_upgrade_preview.py` and `tests/test_git_subprocess.py`: 42 passed.
- Full suite, `pytest -n 4`: 5913 passed.
- `validate`, `export --check`, `digest --check` on the dogfood fixture and `file-limits`: pass. `ruff`: clean.
- Red checks, each reverted afterwards: base package (23 of the new tests fail); `_git` without isolation (2 fail);
  live `ls-files` without the fsmonitor override (2 fail).

## Added

- `ignore_report.isolate_git` and `_isolated`: keep `_git` isolated inside `scratch_environ` (decision 2).
- `scratch_git_env(isolate=)` branch: the config isolation A1 requires.
- `git_subprocess.run(env=)`: A2.
- `upgrade_generated.GitFailed`: one abort path to exit 2 for all four git commands.
- `upgrade_generated.checked`: turns a `GitResult` into the A2 error text.
- `upgrade_generated.COPY`: the location text, shared by `checked` and `regenerate`.
- `regenerate(caller_env=)` and `_check(caller_env=)`: hand the caller's environment to the live `ls-files`.
- `regenerate`'s `r.code != 1` branch: exit 1 means untracked, anything else aborts (A2).
- `-c core.fsmonitor=false` on the live `ls-files`: decision 1.
- `upgrade._commit_copy`: the checked init, add and commit, out of `_dry_run`.
- `_commit_copy`'s `.git` guard: decision 4.
- `--allow-empty` on the scratch commit: a copy git ignores whole would otherwise now abort; no test covers it.
- `Mirror.dest`, `.hooks`, `.init`: the empty scratch directories and the init result the dry run checks.
- `Mirror.unreadable` and its branch in `_copy_file`: decision 3, exercised by the existing parity test.
- `except GitFailed` in `run_upgrade`: prints the error and returns 2.
- Test helpers `_committed`, `_checkout_state`, `_marker_config`, `_stub_git`, and the `FAILURES` table: shared setup.
- `test_git_config_count_runs_no_command_in_a_dry_run` (3 cases): the three `GIT_CONFIG_COUNT` rows.
- `test_the_callers_global_git_config_never_reaches_the_copy` (2 cases): the HOME and XDG row, plus validate and the
  plan mirror; it spies on `validate_at` and `git_subprocess.run` for the caller's env on `ls-files`.
- `test_the_scratch_repository_has_no_template_hooks`: the no-hooks row.
- `test_git_ceiling_directories_does_not_hide_a_tracked_roadmap_md` (2 cases): the ceiling row, dry and real.
- `test_a_failed_scratch_git_call_stops_the_dry_run` (9 cases): init, add, commit by failure kind, stubbed.
- `test_a_failed_ls_files_writes_no_generated_file` (4 cases): the ls-files row, dry and real.
- `test_ls_files_exit_1_means_untracked`: exit 1 keeps its meaning under the new check.
- `test_run_inherits_the_environment_unless_given_one`: `env=` in tests/test_git_subprocess.py.
