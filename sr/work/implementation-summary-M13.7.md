# Implementation summary: M13.7

Clearer notices: symlinked skill dirs, new ignore rules over tracked files, and session end.

## Acceptance

- **A1 (symlinked stub dirs):** `refresh-stubs` reports every written path through
  `resolve_linked()`. An entry under a symlinked directory is listed once, by its
  real path, with `(<link> → <target>)` appended, e.g.
  `wrote .claude/skills/specyrd-brief/SKILL.md (.agents/skills → .claude/skills)`.
  In a dry run the claude-code pack also reported `.claude/skills/<name> (created)`
  for each skill. That path is the same directory as the skill. A real run reports
  it unchanged (`ensure_link` sees it resolve to the canonical skill), so the report
  drops it, and dry and real runs now print the same lines. Pinned by
  `tests/test_m13_7_notices.py` (end to end through `main`, dry and real, plus the
  report helper given both names).
- **A2 (new ignore rules):** before `apply_and_report()` writes `.gitignore`, it
  finds each managed rule that matches no line already in the file. For each one
  it lists tracked matches (`git ls-files -- <rule>`, "still tracked; git keeps
  tracking it") and untracked matches that are not already ignored
  (`git ls-files --others --exclude-standard -- <rule>`, "untracked; now hidden from
  git status"). It prints at most 20, then `… and N more`, and only when
  `.gitignore` was created or updated. It does nothing outside a git checkout and
  untracks nothing. Pinned by tests with one tracked and one untracked match (dry
  and real), the cap, and a rerun that prints nothing.
- **A3 (session end):** `_end_own` now prints
  `ended your only live session <A> here (this shell's id <B> has no record)`.
  Exit code and effect are unchanged. The existing test in
  `tests/test_session_presence.py` now pins the new text as the first line of output.
- **A4:** the shipped ignore rules, untracking and `session end` behaviour are all unchanged.

## Touch zones (final)

`specy_road/bundled_scripts/refresh_stubs.py`, `specy_road/agent_ignores.py`,
`specy_road/bundled_scripts/session_cli.py`, `tests/`, **plus one new module:
`specy_road/bundled_scripts/refresh_stubs_report.py`**. `refresh_stubs.py` was at
its 400-line cap, so its report printers (`_report`, `_report_orphans`,
`_old_command_stub`, `NEXT_STEP`) moved there unchanged and the new grouping code
went in with them. `refresh_stubs.py` re-imports them under their old names, so
`upgrade.py`'s `from ...refresh_stubs import _report` and the tests' private
imports (already in the baseline) still resolve. Please add the new module to the
leaf's touch zones.

**Not changed:** `upgrade.py` (outside the zones) still calls `_report` without
`repo_root`, so the `upgrade` report does not group symlinked paths yet. That is
a one-argument follow-up (`repo_root=checkout`). The A2 notice does reach
`upgrade`, because it is printed from `apply_and_report()`. It also prints from
`specyrd init` and `init project`, which call the same function.

## Verification

- `python -m pytest -n 4 -q`: 3966 passed
- `specy-road file-limits`: OK
- `ruff check` on the changed files: clean

## Added

- `refresh_stubs_report.py` (new module): holds the moved report printers, because `refresh_stubs.py` was at its line cap.
- `refresh_stubs_report._linked_dir`: finds the shallowest symlinked directory above a reported path, which the note names.
- `refresh_stubs_report.resolve_linked`: folds entries that reach one file under two names into its real path plus the link note (A1).
- Branch in `resolve_linked` that drops a skill link which is the real directory of a file listed through the symlink: without it, dry runs listed each skill twice and disagreed with real runs.
- Guard in `resolve_linked` that keeps an entry as-is when its real path is outside the repo: such a path cannot be named relative to the repo root.
- `report(..., repo_root=None)` parameter: `refresh-stubs` `main` passes the root, and other callers keep their old output.
- `agent_ignores._new_rule_matches`: collects tracked and newly hidden files matched by rules new to `.gitignore` (A2).
- Guard in `_new_rule_matches` that returns nothing without a `.git` entry: skips git calls outside a checkout, as in tests on bare temp dirs.
- `agent_ignores.print_new_rule_matches`, `MATCH_LIMIT`, `TRACKED_NOTE`, `HIDDEN_NOTE`: print the A2 notice, capped at 20.
- Call in `apply_and_report` that computes matches before the write and prints them only when `.gitignore` was created or updated: `--exclude-standard` must still see the files the new rule will hide.
- `tests/test_m13_7_notices.py::test_a_symlinked_skills_dir_reports_each_skill_once_with_the_link` (dry and real): A1 end to end.
- `tests/test_m13_7_notices.py::test_the_report_folds_two_names_for_one_file_into_its_real_path`: A1 with both names given.
- `tests/test_m13_7_notices.py::test_a_new_ignore_rule_lists_tracked_and_untracked_matches` (dry and real): A2 lines and labels, and the tracked file stays tracked.
- `tests/test_m13_7_notices.py::test_the_match_list_stops_at_the_limit_then_counts`: A2 cap.
- `tests/test_m13_7_notices.py::test_rules_already_in_the_file_are_not_new`: no notice once the rules exist.
- `tests/test_session_presence.py` assertion updated to the new A3 text, which it pins as the first output line.
- Mocks: none.

## Fix round 1

This round addresses Sol's (gpt-6.1-sol) block on a07d9e96, R1–R3, after merging `origin/WIP/improvements-0-3-1`. The code fix is commit `0be41c29`.

- **R1 (either link direction):** `resolve_linked` now drops a skill-folder entry whose real path is the folder of another listed file, whichever side the symlink is on. Before, it was dropped only when the file was reached through the link. For `.claude/skills -> .agents/skills`, a dry run listed `.agents/skills/<x>/SKILL.md` and `.agents/skills/<x> (created) (…)`; it now lists the SKILL.md once. No link note is carried onto that file, because a real run never lists the link, and the two runs must print the same lines.
- **R2 (git's ignore semantics):** `_new_rule_matches` no longer uses `git ls-files -- <rule>` pathspecs. It asks git through `git -c core.excludesFile=<tmp file of the new rules> check-ignore --no-index -v -z --stdin`, given the tracked files and the untracked files git shows today. A path is listed only when git says a new rule decides it. An existing `.gitignore` rule takes precedence over `core.excludesFile`, so a later `!work/prompt-keep.md` keeps the file unlisted. Gitignore `*` does not cross `/`, so `work/prompt-dir/sub.md` is not listed. This still runs before the write, so dry and real runs agree. The tracked notice and the 20-entry cap are unchanged.
  - **Known limit:** a negation placed *before* the managed block is overridden in reality by the block rule after it. Here it still wins, so such a file is under-reported, never falsely reported as hidden.
- **R3 (target outside the root):** the link note is now built by `_link_note`. It prints the target relative to the root when it lies inside the root, and absolute otherwise. `relative_to(root)` is no longer called unconditionally on the link target.

**Red-green:** the 7 new test cases fail on a07d9e96 (7 failed, 7 passed) and pass on 0be41c29.

**Verification:**
- Targeted run (Sol's import-based selection plus `tests/test_upgrade.py`): 427 passed.
- `specy-road file-limits`: OK.
- `ruff check`: clean.

### Added (fix round 1)

- `refresh_stubs_report._link_note`: formats the link note safely when the target lies outside the root (R3).
- `linked_parents` / `folded` sets in `resolve_linked`: fold the skill-folder entry in either symlink direction (R1).
- `agent_ignores._ls_files`: NUL-separated `git ls-files` listing of tracked and visible untracked files, so paths with special characters parse correctly.
- `agent_ignores._check_ignore`: asks git which paths a new rule decides, through `check-ignore` with the new rules as `core.excludesFile` (R2).
- Guard in `_check_ignore` that returns no matches when git cannot run, so the notice is skipped rather than the refresh failing.
- Early return in `_new_rule_matches` when there are no new rules or no files, which avoids a temp file and a git call.
- `tests/test_m13_7_notices.py::test_a_reverse_symlinked_skills_dir_reports_each_skill_once_and_runs_agree`: R1, end to end, dry and real.
- `tests/test_m13_7_notices.py::test_a_link_out_of_the_repo_and_back_names_its_target_absolutely` (dry and real): R3, end to end.
- `tests/test_m13_7_notices.py::test_a_path_the_new_rule_only_matches_as_a_pathspec_is_not_called_hidden` (dry and real): R2, `work/prompt-dir/sub.md`.
- `tests/test_m13_7_notices.py::test_a_later_negation_keeps_the_file_visible_and_unlisted` (dry and real): R2, negation after the managed block, with the tracked notice kept.
- Mocks: none.

## Fix round 2

This round addresses Sol's (gpt-6.1-sol) block on f800421e, R1 and R2, after merging `origin/WIP/improvements-0-3-1`. The code fix is commit `2e41f167`.

- **R1 (A2): judge the `.gitignore` the update would actually write.** `_new_rule_matches` no longer passes the new rules through `core.excludesFile`. In a throwaway `git init` directory it:
  1. copies the current `.gitignore` byte for byte, plus every nested `.gitignore`;
  2. runs `git check-ignore --no-index -v -z` on the tracked files and on the untracked files git shows today;
  3. updates the copy with `apply_agent_ignores` itself, using the same prefix and seed, so the block position, preserved text and line endings match the real write;
  4. runs the check again.

  A path is listed only when it is ignored afterwards and was not before; the rule shown is the one git names. If the copy does not change, nothing is listed. The real file is never touched, so dry and real runs print the same lines.
- **R2 (A1): report entries are data, not reparsed strings.** The new `specy_road/written_entry.py` defines `Written(path, outcome)`. It is a `str` subclass whose text is still `"<path>"` or `"<path> (<outcome>)"`, so every existing caller, return value and string comparison is unchanged, while `.path` and `.outcome` stay fields. Producers in the zones now append `Written`: `refresh_stubs._write_if_changed`, `_refresh_pack`, the `CLAUDE.md` guide line, and `agent_ignores.apply_and_report`. Both readers had parsed with `partition(" (")`, and now read the fields:
  - `resolve_linked`, the report;
  - `_print_diffs`: managed-block previews are looked up by their whole line and carry their own path.

  Plain strings, i.e. `agents_md_block` entries from outside the zones, are printed as they are and never parsed.

**New file outside the listed zones:** `specy_road/written_entry.py`. Please add it to the leaf's touch zones, alongside `refresh_stubs_report.py`.

### Fix round 2: probes

| Input | Checked | Result |
|---|---|---|
| Parenthesised generic dir `docs/team (commands)/`, plain and symlinked (`→ actual`) | dry and real | Fixed (R2); each stub reported whole, the symlinked one as `actual/<name> (docs/team (commands) → actual)` |
| Generic dir with unicode, spaces, `#` and `!` (`docs/équipe #1 !x`) | dry and real | Reported whole |
| `refresh-stubs --diff` on a parenthesised dir | | **Real defect:** `_print_diffs` truncated the path at ` (` and printed no diff. Fixed with the same data change; new test `test_diff_shows_stubs_under_a_parenthesised_dir` |
| Untracked files with spaces, unicode, a leading `#` or `!` in a name, and top-level `#top.md` and `!top.md` | | Listed exactly as git hides them; the top-level ones are unlisted because no rule matches them |
| `.gitignore` with no trailing newline | | Correct |
| CRLF `.gitignore` with a negation before the block | | Correct. The update rewrites the file with LF, and the sandbox copy goes through the same code, so the listing matches git. The previous code failed this probe |
| Nested project prefix `sr/` | | Only `sr/…` paths listed; root-level `work/prompt-y.md` is not |

For each A2 probe, the test asserts that the "now hidden" list equals the set of files that stop appearing in `git status --untracked-files=all` after the real update, and that the dry and real runs print the same output.

**Red-green:** the new R1, R2, crlf and `--diff` cases fail on f800421e (7 failed in the file; `--diff` checked separately) and pass on 2e41f167.

**Verification:**
- Targeted run, 36 files: the earlier selection plus every test that imports `specyrd_init`, `init_project` or `run_init`: 714 passed.
- `specy-road file-limits`: OK.
- `ruff check`: clean.

### Added (fix round 2)

- `specy_road/written_entry.py` `Written`: carries each report item as path plus outcome while staying a `str`, so other callers are unaffected (R2).
- `agent_ignores._ignored`: `check-ignore --no-index` in the sandbox, returning `{path: rule}` for ignored paths (R1).
- Sandbox flow in `_new_rule_matches`: `git init`, copy the top and nested `.gitignore` files, check before, apply the real update, check after (R1).
- Explicit copy of the top `.gitignore` even when `ls-files` does not list it, for example a `.gitignore` that ignores itself.
- Early return in `_new_rule_matches` when the sandbox `.gitignore` is unchanged, which skips the second check.
- Removed the round-1 `_check_ignore`, its `core.excludesFile` approach and the "new rule = line not in file" test.
- `_block_previews` now returns `(path, text)`, so `_print_diffs` never parses a path out of a line (`--diff` defect).
- `tests/test_m13_7_notices.py::test_a_negation_before_the_block_loses_to_the_new_rule_and_is_listed` (dry and real): R1.
- `tests/test_m13_7_notices.py::test_a_generic_dir_with_parentheses_or_odd_characters_is_reported_whole` (2 dirs × dry and real): R2 and odd-character probes.
- `tests/test_m13_7_notices.py::test_a_symlinked_generic_dir_with_parentheses_reports_its_real_path` (dry and real): R2 with a symlink.
- `tests/test_m13_7_notices.py::test_the_hidden_list_is_exactly_what_git_status_stops_showing` (4 probes): the ignore-side probes, checked against git status.
- `tests/test_m13_7_notices.py::test_diff_shows_stubs_under_a_parenthesised_dir`: the `--diff` defect.
- `test_the_report_folds_two_names_for_one_file_into_its_real_path` now passes `Written` entries: plain strings are no longer parsed, by design.
- Mocks: none.

## Fix round 3

This round addresses Sol's (gpt-6.1-sol) block on 4a1551f5, R1–R3, after merging `origin/WIP/improvements-0-3-1`. The code fix is commit `e99dfa22`.

- **R3: the note is advisory and never aborts or changes a write.** `apply_and_report` first asks `apply_agent_ignores(dry_run=True)` whether `.gitignore` will change, and only then works out the note. All git calls in the note go through `_git`, which raises `IgnoreCheckSkipped` on any unexpected exit; `check-ignore`'s exit 128 counts. That exception, `OSError`, `ValueError` (including decode errors) and `SubprocessError` (including timeouts) are caught. In their place the report prints exactly one line, `ignore check skipped: <reason>`, and never a guessed match list. The writes are the base's own `apply_agent_ignores(...)` call, unchanged and unconditional.
- **R2: the scratch repositories carry the checkout's ignore settings.** `_ignore_config` reads:
  - `core.ignorecase`, always passed as `-c`, defaulting to `false` when unset;
  - `core.excludesFile` (`git config --path --get`, any scope), passed as `-c` when set;
  - `info/exclude` (`git rev-parse --git-path`, which also works from a linked worktree), copied into the scratch repository's `.git/info/exclude`.

  Git calls also drop `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR` and `GIT_OBJECT_DIRECTORY`. Inside a git hook those would point `git init` and `check-ignore` back at the real checkout, so the first would re-initialise it.
- **R1: tracked files are judged on their own.** `_tracked_matches` writes only the rules the update adds (block lines that are not already a line of the file) to a scratch `.gitignore`. It lists every tracked path git says one of them matches, counting only matches from that file and ignoring any older rule that also matches. The untracked "now hidden" label keeps the before/after comparison on the real resulting file (`_newly_hidden`, unchanged in substance).

**Red-green:** the 6 new R1–R3 cases fail on 4a1551f5 and pass on e99dfa22. The `GIT_DIR` test fails when `_REPO_ENV` is emptied.

**Process note:** while running that red-green check I restored the file with `git checkout --`, which also discarded my uncommitted round-3 edit to `agent_ignores.py`. I re-applied the identical edit from this session's script before committing, then re-ran all checks; nothing else was affected.

**Verification:**
- Targeted run, 36 files (same selection as round 2): 721 passed.
- `specy-road file-limits`: OK.
- `ruff check`: clean.

### Fix round 3: ignore-input audit

| Input | Scratch repo | How / why |
|---|---|---|
| `core.ignorecase` | **Honoured** | Read from the checkout (all scopes) and passed as `-c` to every `check-ignore`. Defaults to `false` like git. Test: `test_ignorecase_from_the_checkout_is_honoured` |
| `core.excludesFile` | **Honoured** | When set at any scope it is passed as `-c`, relative paths resolved against the checkout. When unset, the scratch repo uses the same per-user default (`$XDG_CONFIG_HOME/git/ignore`), because it runs as the same user with the same `HOME`/`XDG_CONFIG_HOME`. The tracked check counts only matches from its own `.gitignore`, so the global file never shows up as a "new rule" |
| `info/exclude` | **Honoured** | Copied byte for byte into the "now hidden" scratch repo. Not used by the tracked check, which only asks which new rules match |
| Nested `.gitignore` files | **Honoured** in the "now hidden" check | Every tracked one, and every untracked one git shows, is copied to the same path. **Gap:** an untracked nested `.gitignore` that git itself hides (it ignores itself, or sits under an ignored directory) is not copied. Files under an ignored directory are never candidates anyway. Deliberately **not** used by the tracked check, which asks only whether a new rule matches. An unreadable one makes the note skip (R3) |
| Global gitignore | **Honoured** | It is `core.excludesFile` or its XDG default; see that row |
| Sparse checkout | **Deliberately not used** | It does not affect ignore matching. Skip-worktree entries are still in the index, so `ls-files` lists them as tracked and the note calls them "still tracked", which is true |
| `GIT_DIR` and other repository-location variables (hooks) | **Removed** for the note's git calls | Otherwise the scratch repository would be the checkout. Test: `test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout` |

### Added (fix round 3)

- `IgnoreCheckSkipped` and `_git`: one place where a failed git call becomes "skip the note", with the git subcommand and its last stderr line (R3).
- Dry-run pre-check in `apply_and_report`: the note is worked out only when `.gitignore` will change, so most refreshes start no extra git process.
- try/except around the note in `apply_and_report`, printing `ignore check skipped: <reason>` (R3).
- `_ignore_config`: `core.ignorecase`, `core.excludesFile` and `info/exclude` from the checkout (R2).
- `_REPO_ENV` filter: keeps hook-set `GIT_DIR` and related variables from redirecting the scratch repository to the checkout.
- `_scratch`: `git init` plus byte copies, shared by both checks.
- `_tracked_matches`: tracked paths matched by the newly added rules alone (R1).
- `_newly_hidden`: the round-2 before/after check on the resulting `.gitignore`, moved out unchanged in substance.
- `source=` filter in `_ignored`: limits the tracked check to its own rules.
- `tests/test_m13_7_notices.py::test_an_unreadable_nested_gitignore_skips_the_note_but_not_the_writes` (dry and real): R3.
- `tests/test_m13_7_notices.py::test_ignorecase_from_the_checkout_is_honoured` (dry and real): R2.
- `tests/test_m13_7_notices.py::test_a_tracked_file_an_older_rule_already_ignores_is_still_listed` (dry and real): R1, with the index unchanged.
- `tests/test_m13_7_notices.py::test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout`: the env guard.
- Mocks: `monkeypatch.setenv` for `GIT_DIR`/`GIT_WORK_TREE` in that one test, to reproduce a hook environment.

## Fix round 4: design change

This round answers Sol's (gpt-6.1-sol) block on 625acb89 (R1: an ignored nested `.gitignore` was not copied into the scratch repository) with the design change the maintainer chose. The code change is commit `a5a25fe1`, made after merging `origin/WIP/improvements-0-3-1`.

The new module `specy_road/ignore_report.py` (167 lines) is outside the listed zones; please add it. All the note logic lives there, so `agent_ignores.py` shrinks to 198 lines with no scratch code. `docs/install-and-usage.md` (one line, under `refresh-stubs`) is also outside the zones; the maintainer asked for it in this round.

### Real-run contract (refresh-stubs, upgrade, init: any run that writes)

1. **Run condition:** only when the dry outcome of `apply_agent_ignores` says `.gitignore` will be created or updated, and the root is a git checkout.
2. **Before the write:** `observe()` records, in the real checkout and from git's NUL-split byte output:
   - (a) `git ls-files -o --exclude-standard -z`, the untracked files git shows;
   - (b) `git ls-files -c -i --exclude-standard -z`, the tracked files git ignores.
3. **The write:** the same `apply_agent_ignores(...)` call as the base, unconditional and unchanged.
4. **After the write:** `observed()` records (a) and (b) again.
   - **Now hidden** = in (a) before and not in (a) after.
   - **Still tracked under a new rule** = in (b) after and not in (b) before. A tracked file an older rule already ignored is therefore *not* listed; this replaces the round-3 contract.
   - The rule shown beside each path comes from `git check-ignore --no-index -v` in the real checkout.
5. **Output:**
   - The header is `.gitignore: new rules match files already in the tree (nothing was untracked):`.
   - At most 20 paths, then `… and N more`.
   - When a tracked path is listed, one more line: `to stop tracking one of the files above: git rm --cached <path>`. The round brief said to keep this hint, but no such hint existed before; I added it, and it suggests a command without running it.
6. **Advisory guarantee:** any failure in either capture or the rule lookup, whether an `OSError`, a non-zero git exit, a timeout or a decode error, prints exactly one line, `ignore check skipped: <reason>`, and never lists invented matches. The write happens either way.

Nothing is predicted. Rule order, nested and self-ignored `.gitignore` files, `info/exclude`, `core.ignorecase` and the global excludes file are all read by git itself.

### Dry-run contract (`--dry-run`, `--diff`)

- **Label:** the header is `estimated (dry run): .gitignore's new rules would match files already in the tree (nothing is untracked); the real run reports exactly what changed:`.
- **How it is estimated:** in a throwaway `git init` directory, `estimate()` copies:
  - the top-level `.gitignore`;
  - the `.gitignore` in **every ancestor directory of every candidate path, ignored or not** (the R1 fix);
  - `info/exclude`.

  It passes the checkout's `core.ignorecase` and `core.excludesFile`. It then asks `check-ignore` about tracked files and shown untracked files, applies the real update code, and asks again. The same tracked and now-hidden definitions apply.
- **No further inputs:** it does not try to reproduce anything else.
- **Known limits:** documented in one paragraph of the `ignore_report` module docstring and one line in `docs/install-and-usage.md`. The estimate can differ from the real run when git reads an input it does not copy, or when files change between the two runs.
- **Same guarantee:** the advisory skip-line guarantee is identical to the real run's.

### Tests merged or removed

Merged into one parametrized test, `test_the_real_run_reports_exactly_the_visibility_change_git_shows`, with 12 cases. Each case asserts that the listed now-hidden set equals both the `git status --porcelain -z -uall` change and an explicit expected set. It asserts the same for the listed tracked set against the `ls-files -c -i --exclude-standard` change, and that `git ls-files -s` (the index) is unchanged. The merged tests were:
- `test_a_new_ignore_rule_lists_tracked_and_untracked_matches` → case "plain";
- `test_a_path_the_new_rule_only_matches_as_a_pathspec_is_not_called_hidden` → "r1 pathspec-only match";
- `test_a_later_negation_keeps_the_file_visible_and_unlisted` → "r1 negation after block";
- `test_a_negation_before_the_block_loses_to_the_new_rule_and_is_listed` → "r2 negation before block";
- `test_the_hidden_list_is_exactly_what_git_status_stops_showing` (4 probes) → "r2 crlf", "r2 no trailing newline", "r2 odd names", "r2 nested project";
- `test_ignorecase_from_the_checkout_is_honoured` → "r3 ignorecase";
- `test_a_tracked_file_an_older_rule_already_ignores_is_still_listed` → "r3 tracked already ignored". The contract changed, so it is now expected **not** to be listed.

New cases in the same test: "r3 info/exclude" and "r4 self-ignored nested .gitignore" (Sol's R1 layout: only `prompt-hide.md` is hidden).

`test_an_unreadable_nested_gitignore_skips_the_note_but_not_the_writes` was split in two. In the real run git warns and carries on, so an unreadable nested file no longer causes a skip there.
- `test_a_failed_git_capture_skips_the_note_and_the_writes_still_happen` (dry and real): a `.git` file pointing at a missing git directory. Both managed files are still written, and the output is the single skip line.
- `test_an_unreadable_nested_gitignore_skips_the_estimate` (dry run).

**Also new:** `test_the_dry_run_is_labelled_an_estimate_and_gets_the_self_ignored_nested_case_right`. It checks the label, the R1 layout in the dry run, that nothing is written, and that the dry run's paths, rules and notes equal the real run's.

**Kept, updated:** `test_the_match_list_stops_at_the_limit_then_counts` now expects the hint line last.

**Kept unchanged:** `test_rules_already_in_the_file_are_not_new` and `test_a_git_dir_from_a_hook_does_not_point_the_scratch_repo_at_the_checkout`.

**Red-green:** with the test file on 625acb89 (header constants inlined, because the module did not exist), 4 fail: "r4 self-ignored nested", "r3 tracked already ignored", the estimate-label test and the limit/hint test. All pass on a5a25fe1.

**Verification:**
- Targeted run, 37 files: the round-3 selection plus the tests that reference `install-and-usage`. 722 passed.
- `specy-road file-limits`: OK.
- `ruff check`: clean.

### Added (fix round 4)

- `specy_road/ignore_report.py` (new module): holds the observed note and the dry-run estimate, so `agent_ignores.py` keeps only the writes.
- `observe` and `observed`: the real-run before/after measurement in the checkout, as bytes split on NUL.
- `estimate` and `_ancestor_ignores`: the dry-run estimate, copying every ancestor `.gitignore` of each candidate path (R1).
- `attempt`: turns any capture failure into the skip reason (advisory guarantee).
- `print_matches`: the real and estimate headers, the cap and the untrack hint.
- `_paths` and `_stdin`: NUL/bytes conversion for git input and output.
- Kept from round 3, moved here: `IgnoreCheckSkipped`, `_git` (now bytes), `_ignored`, `_ignore_config` and the `_REPO_ENV` filter.
- Removed: `_scratch`, `_tracked_matches`, `_newly_hidden` and the old `_new_rule_matches`.
- Tests: listed above.
- Mocks: none new.

## Fix round 5: R1 class audit

This round reworks Sol's (gpt-6.1-sol) block on 625acb89, R1, after the previous worker (w-0006) stopped on a usage limit. Round 4 (`a5a25fe1`) had already fixed the named instance. Sol's reproduction now lists only `work/prompt-hide.md` in both the dry and the real run, and `git status` still shows `work/prompt-keep.md`. The regression is in place: case "r4 self-ignored nested .gitignore" and `test_the_dry_run_is_labelled_an_estimate_and_gets_the_self_ignored_nested_case_right`. The code change in this round is commit `e6218bfd`.

**Class:** an ignore input that git reads, or refuses to read, differently from how the dry-run scratch repository reproduces it. The class only reaches `ignore_report.estimate`. The real run is observed by git in the checkout itself, so nothing there is reproduced.

**Second instance found and fixed (design change):** a `.gitignore` that is a symlink, whether nested, at the top level or dangling. Git (2.43 here) does not read a symlinked `.gitignore`, but `estimate` copied the link target's bytes into a regular file.
- For a nested link to `!prompt-keep.md`, the dry run left out `prompt-keep.md`, which the real run hides.
- For a top-level link, the dry run listed a file the real run does not hide.

`_copy_ignore` now keeps a symlink a symlink in the scratch repository. The link points at a scratch copy of its target under the scratch `.git/`, and a dangling link stays dangling. So the same git decides whether to read it, and the update in the scratch repository can never write through a link to a checkout file.

## Probes

Each probe ran `apply_and_report` dry and real on a fresh repository and compared three things: the dry listing, the real listing, and the change in `git status --porcelain -uall`. The probe script was `/tmp/m137_probe.py`; it is not committed.

- Sol's R1 layout (`work/.gitignore` = `.gitignore`, `!prompt-keep.md`): dry, real and status agree on `prompt-hide.md` only. Already fixed in round 4.
- Self-ignored nested `.gitignore` three levels deep (`work/a/b/`): agree, nothing listed (no shipped rule reaches it).
- Self-ignored `.gitignore` under a shipped directory rule (`work/reviews/`): agree; the directory rule hides both files despite the negation, as git does.
- Nested `.gitignore` ignored by its parent's `.gitignore` (`sub/.gitignore`): agree.
- Nested `.gitignore` ignored by a top-level `**/.gitignore`: agree.
- Nested `.gitignore` ignored through `info/exclude`: agree.
- Nested `.gitignore` ignored through `core.excludesFile`: agree.
- Nested `.gitignore` under an already ignored directory: agree, nothing listed (no candidates there).
- A self-ignored nested `.gitignore` whose only candidate is tracked: agree, nothing listed.
- Self-ignored nested `.gitignore` in a directory with a space and `é`: agree.
- Self-ignored nested `.gitignore` under project prefix `sr/`: agree, `sr/work/prompt-hide.md` only.
- Nested `.gitignore` that is a symlink: **differed** (the dry run missed `prompt-keep.md`). Fixed; test case "nested symlink".
- Top-level `.gitignore` that is a symlink: **differed** (the dry run listed `prompt-hide.md`, the real run nothing). Fixed; test case "top-level symlink".
- Dangling top-level and nested `.gitignore` symlinks: agree after the fix. The top-level one is pinned as test case "dangling top-level symlink".
- Advisory skip handling is unchanged: `test_a_failed_git_capture_skips_the_note_and_the_writes_still_happen` and `test_an_unreadable_nested_gitignore_skips_the_estimate` pass.

**Red-green:** the 3 new cases fail with `ignore_report.py` at 53f9e35c and pass at e6218bfd.

**Verification:**
- Targeted run, 37 files (Sol's selection): 726 passed.
- `specy-road file-limits`: OK.
- `ruff check`: clean.

### Added (fix round 5)

- `ignore_report._copy_ignore`: copies one ignore file into the scratch repository and keeps a symlink a symlink, because git does not read a symlinked `.gitignore`.
- Branch in `_copy_ignore` for a dangling link: it stays dangling, as in the checkout.
- `is_symlink()` alternative in `estimate`'s copy filter: without it a dangling link was skipped, and the scratch update created a regular `.gitignore`.
- `tests/test_m13_7_notices.py::test_the_dry_run_estimate_treats_a_symlinked_gitignore_as_git_does` (3 cases: nested, top-level and dangling top-level symlink). Each case checks that dry, real and the git-status change agree and that the dry run writes no file.
- Mocks: none.

### Fix round 5: merge

`specy-road ready` reported `origin/WIP/improvements-0-3-1` 90 commits ahead, with a conflict in `specy_road/bundled_scripts/refresh_stubs.py`. I merged it in as `73bd36ed`. This is a merge commit, so it could not be committed by explicit path.

The conflict was one line in `_block_previews`. The resolution keeps both sides:
- the integration branch's `apply_agents_files(..., mode=agents_block_mode(repo_root / prefix))`;
- this branch's `(path, text)` preview values (fix round 2, R2).

After the merge, the full suite (`pytest -n 4`) gave 4148 passed and 1 failed: `tests/test_worker_queue_message.py::test_message_while_running_queues_and_delivers`, a timing assertion (`idle` vs `running`). That file passed 6/6 on each of three reruns. Compared with the integration tip, the merge differs only in this leaf's own files.

## Fix round 6

This round addresses Sol's (gpt-6.1-sol) block on c366c94f, R1 (A2). It starts with a merge of `origin/WIP/improvements-0-3-1` (`542229f5`, clean). The code is commit `45d839f8`; the docs line is `8af46df0`.

**Class:** a tracked file that a rule this update added reaches, but that the report leaves out because of how "new" is measured. Round 4 measured it as *ignored after and not before*. That drops a tracked file an older rule already ignored (Sol's case: `work/*.md` already present, new `work/prompt-*.md`). A2 never narrows the tracked list to newly ignored paths.

**Design change: attribution, measured by git.** After the write, `git check-ignore --no-index -v -z --stdin` runs on every tracked file (`git ls-files -c -z`). Its `source`, `linenum` and `pattern` output is read as bytes. A tracked file is listed when:
- the source is the top-level `.gitignore`, and
- the line number is one of the lines the update added, meaning lines of the new file that are not a line of the old one (a trailing CR is ignored, so a CRLF file rewritten as LF is not "all new").

The untracked "now hidden" list is unchanged: the observed before/after visibility difference. `observe()` now records the shown files and the old `.gitignore` bytes. The dry-run estimate applies the same attribution against the scratch copy and keeps its label. The 20-entry cap, the `git rm --cached` hint, the skip-on-error line and the index are all unchanged.

**Known limit:** git names one deciding rule, the last match with nested files ahead of the root. A tracked file is therefore not listed when, in the same root `.gitignore`, an older rule after the block also matches it, or when a nested `.gitignore` decides it. That is git's own answer to "which rule ignores it". It is pinned by test case "r5 older rule after the block decides".

**Tests:**
- Case "r3 tracked already ignored" now expects `work/prompt-a.md` and `work/prompt-tracked.md` listed as tracked.
- New case "r5 tracked by an older rule only": `work/old.md` is not listed.
- New case "r5 older rule after the block decides": nothing is listed.
- The real-run test asserts that the listed tracked set equals the expected set and lies within what git ignores. It no longer compares against a set difference.
- New test `test_the_dry_run_estimate_lists_what_the_real_run_reports` runs every case dry and requires the estimate's lines to equal the real run's, so Sol's case has dry-run coverage.
- `tests/test_m13_7_notices.py` reached 402 lines, so the symlinked-`.gitignore` tests (round 5) moved unchanged to the new file `tests/test_m13_7_gitignore_symlinks.py`.

**Red-green:** with `ignore_report.py` from `542229f5`, the 2 "r3 tracked already ignored" cases (real and dry) fail; all 51 pass on `45d839f8`.

## Probes

Each probe below ran dry and real, checked that the index was unchanged, and compared the dry listing with the real one. The probe script was `/tmp/m137_probe2.py`; it is not committed. All 14 agree between dry and real.

- Sol's case (older `work/*.md`, new `work/prompt-*.md`): the tracked file is listed. Fixed; test case r3.
- Tracked file matched only by an older root rule: not listed. Test case r5.
- Older root rule after the block matching the tracked file: not listed, because git attributes it to the later rule. This is the known limit; test case r5.
- Older rule in a nested `work/.gitignore`: not listed (git attributes it to the nested file). Same limit.
- Older rule in `info/exclude`: listed, because the root `.gitignore` outranks it.
- Older rule in `core.excludesFile`: listed.
- CRLF `.gitignore` with an older rule: listed under the block rule, and the old lines are not counted as added.
- A user line identical to a shipped rule already in the file: not listed, because it is not a new rule (as in round 1).
- `init project` seed carrying a rule: listed under the block's rule.
- Tracked names with a space, `β`, a leading `#` or `!`: listed exactly, since NUL-split bytes are used throughout.
- `core.ignorecase=true` with `work/Prompt-T.md`: listed.
- Negation of the tracked file after the block: not listed, because the deciding rule is the `!` line.
- No `.gitignore` before the update: listed.
- Top-level `.gitignore` that is a symlink: nothing listed, since git does not read it.
- Nested project prefix `sr/`: `sr/work/prompt-t.md` listed.
- 25 tracked matches: 20 listed, then `… and 5 more` and the hint.

**Verification:**
- Targeted run (refresh_stubs, agents_md_block, agents_md_report, agent_ignores, both M13.7 files, init_project_gitignore, init_project_reports, session_presence, upgrade, specyrd_init): passed.
- Docs tests for `install-and-usage`: passed.
- `specy-road file-limits`: OK.
- `ruff`: clean.

### Added (fix round 6)

- `ignore_report._shown`: the shown-untracked listing, shared by `observe` and `observed`.
- `ignore_report._top_ignore`: the top-level `.gitignore` bytes, the baseline for "added lines".
- `ignore_report._deciding`: the `check-ignore -v` records with source and line number. `_ignored` is now a view over it.
- `ignore_report._added_lines`: line numbers of the lines the update added, with a trailing CR ignored.
- `ignore_report._tracked_under_new_rules`: the attribution, used by both the real run and the estimate (R1).
- Removed: the tracked half of `observe()` (`ls-files -c -i`) and the before/after tracked difference.
- `tests/test_m13_7_notices.py`:
  - cases "r5 tracked by an older rule only" and "r5 older rule after the block decides";
  - r3 expectation updated;
  - `test_the_dry_run_estimate_lists_what_the_real_run_reports` (all cases).
- `tests/test_m13_7_gitignore_symlinks.py` (new file): the round-5 symlink tests, moved for the 400-line cap.
- `docs/install-and-usage.md`: the one line now says how the tracked notice is decided.
- Mocks: none.

## Precheck fix: no private test imports

The coordinator's precheck flagged `tests/test_m13_7_gitignore_symlinks.py` (round 6). It imported the underscore-prefixed `_listed`, `_repo_with_prompts`, `_shown` and `_write` from `tests/test_m13_7_notices.py`. Commit `46507ea0` fixes it:

- **New module `tests/m13_7_ignore_helpers.py`:** holds the shared helpers under public names: `git`, `repo_with_prompts`, `write`, `shown` and `listed`.
- **Both test files:** now import from that module. Their local copies are removed.
- **Renamed locals:** the local variable that held the earlier `git status` set is renamed `was_shown`, so it no longer shadows `shown()`.
- **Unused import:** `subprocess` is dropped from `test_m13_7_notices.py`.
- **Assertions:** unchanged.

**Probes:**
- Added test lines in this branch's diff that import an underscore name from a test module: none remain from M13.7. The other lines found came in with WIP merges and are not this leaf's.
- `scripts/check_test_private_imports.py`: exit 0, with no M13.7 entries.
- `specy-road file-limits`: OK.
- `ruff`: clean.
- Targeted run, the same 13 files as the round-6 READY: 185 passed.

### Added (precheck fix)

- `tests/m13_7_ignore_helpers.py`: public helpers shared by the two M13.7 ignore test files. It replaces the cross-module private imports.
- Mocks: none.
