# Implementation summary: M22.5 `steering-file-guard`

The branch already held the git-steering part of M21.7, after R30, R31 and R32 removed the other classes, finish's refusal and the launch denies (M22.30, M22.31 and M22.32 restore them). This change makes that code meet M22.5's acceptance. It is commit 77430a38 on top of base 7cc1b7c0, plus rework commit 50067050 for the `gpt-5.6-sol-high` block on 3efc97a7 (see Rework).

## What changed, per acceptance item

- **A1 (filesystem only):** `steering_paths.scope_for` no longer asks git at the turn's start. `git_config_text.git_reads` (`rev-parse --git-path hooks`, `config --list --show-origin`) is removed, and `Scope.git_known` with it. The snapshot reads:
  - the common `config`, `config.worktree` and their `include.path` / `includeIf.*.path` files, using the existing parser;
  - the hooks directories.
  The hooks directories are `core.hooksPath` when set, else `<common>/hooks` and `<worktree-gitdir>/hooks` (rework 50067050). A `hooksPath` value that only an `includeIf` names may not apply, since conditions are not evaluated. If no other value exists, the defaults are watched as well. The existing `nonmatching_conditional_include` case covers that.
  Direct entries only: a regular file (a link followed) is stored as its sha256 and a subdirectory is skipped. The old `link:<text>@sha` and `dir`/`other` values are gone.
- **A2 (cap):** a hooks directory is listed with `os.scandir` and `islice(201)`. If it has more than 200 entries, the directory itself is recorded as unreadable, so every comparison gives one `check_error` (class `git_hook`) and the git probes are skipped. This replaces the `capped` marker.
- **A3 (fail closed):**
  - Every read opens the file with `O_NONBLOCK`, then `fstat` must show a regular file. A FIFO, socket or device is a `check_error` and never blocks, including one swapped in after a stat.
  - A 30 s snapshot budget (`SNAPSHOT_SECONDS`) is checked before each step and per 1 MiB chunk while hashing. A path read after the budget runs out is a `check_error` (`TimeoutError`).
  - With no snapshot from the turn's start, or a comparison that raises, the check records one `check_error` per class naming the worktree, plus `git_probes_skipped`. Before, that path had no path or class and no `git_probes_skipped`.
  - `git_probes_skipped` is now the shared constant `PROBES_SKIPPED`.
- **A4 (runner order):** `worker_runner._finish` now runs `close_turn` before `fresh_ready`. If `fresh_ready` raises (invalid UTF-8 in a READY), `ready` is false. On exit 0, the turn's `completion` event then reads `exit 0; READY file invalid: <error>`; `exit_event` is not called, because its summary would parse the READY again. A non-zero exit still goes through `exit_event`, which does not read READY.
- **A5 (sticky flag):** this already worked and is unchanged. `steering_changed` is in the record's `flags`, which `worker status --json` and `handoff status --json` print, and the schema's flag enum already lists it. `worker reconcile` prints one `path class before after` line per finding and clears the flag.
- **A6:** all cases are in `tests/test_steering_file_guard.py` (see Added).
- **A7:** none of M22.30, M22.31 or M22.32's code is on this branch. The docs name them as out of scope.

## Rework (block by `gpt-5.6-sol-high` on 3efc97a7)

The review found four defects, which fall into two classes.

**Class 1: an entry's absence at one end was reported as a change when the thing that lists it was not read there.** Three of the findings are this class:
- a hooks directory crossing the cap (200 to 201 entries) gave one error plus 200 stale "absent" findings;
- a hooks directory replaced by a FIFO gave its error plus "absent" findings for the hooks it held;
- a hooks directory the config stops naming reported its hooks as absent.

The design change: each snapshot entry records its `parent`, the key of what listed or included it. A hook's parent is its hooks directory. An included config file's parent is the file that included it. A top-level config file's parent is the checkout's `.git`. Containers are recorded as `read:` markers when read in full: a hooks directory that is listed, or that does not exist (an empty listing), and `.git`. The new `steering_paths.compared(before, after, key)` treats an entry's absence at one end as a change only when its parent was read in full at that end. Otherwise the container's own `check_error` reports the gap, or, for a changed `hooksPath`, the config finding does. The rule is transitive: an unreadable `.git` or config file hides everything it would have led to. `_gitdirs` now raises on a missing or invalid `.git` instead of silently watching nothing, so that case fails closed.

**Class 2: one file reached by two names was stored twice.** Config files are now keyed by the file they resolve to (`resolved_path`), not by `real_path` (which keeps the last component). Hooks directories were already resolved and deduplicated. Hooks stay keyed by name in their directory, because two names in one hooks directory are two hooks git runs.

**A1 directory selection:** an unconditional `core.hooksPath` value now excludes `<common>/hooks` and `<worktree-gitdir>/hooks`. `read_chain` now returns `ConfigFile` (path, data, pairs, parent, conditional) so the snapshot knows each file's includer and whether only an `includeIf` reached it.

## Rework 2 (block by `gpt-5.6-sol-high` on 3ccb81da)

**Class: a config file the snapshot never recorded at one end, under a container that is not a `read:` marker.** `read_chain` left a missing include out entirely, and an included file's parent is its including config, which holds a digest and not a `read:` marker. So `compared` never treated that absence as a change: an include the unchanged config already named, created or deleted during the turn, gave no finding, and a created one holding `core.fsmonitor` was run by the post-turn `git status`.

**Design change:** a missing file is now part of the chain. `read_chain` lists it with its `FileNotFoundError`, and `_config_file` records it as an `absent` entry (with its parent). Every config file a readable config names is now recorded at each end, so a creation or deletion compares as present against `absent` directly, without depending on the container rule. A file that is no longer named at all (its includer changed) is still covered by the includer's own `git_config` finding, and a file under an unreadable includer by that includer's `check_error`, as before. Hooks never had this gap: their container is a hooks directory listed in full (`read:`), and a missing hooks directory is recorded as `read:absent`.

## Rework 3 (block by `gpt-5.6-sol-high` on 8ab42769)

This change is commit 598bfaad. The four findings fall into two classes.

**Class A: a change of where a name leads was hidden, because entries were keyed by the file a link resolves to.** Three findings belong to this class: an include symlink created, the hooks-directory symlink retargeted, and a dangling include symlink. When a link changes, its key changes at that end. The entry it replaces then has no counterpart. Its parent (an including config, or the new hooks directory) is not a `read:` container at the other end, so `compared` drops both sides. A dangling link failed to open with `FileNotFoundError` and was recorded as `absent`. The same class reached a worktree's `.git` retargeted to a forged gitdir whose `commondir` points back: the configs compared equal, and the new gitdir's hooks had no counterpart. It also reached a `commondir` that is a dangling link, which read as missing (`exists()`).

**Design change:**
- A config file or hooks directory is still stored once, by its real path (A1).
- Each name git reads it by that is not that real path (a symlink on the way, the name itself or a directory above it) is also recorded. That name is keyed by its normalized absolute path, with the value `link:<real path>`. A `git_config` link carries the watched values of the file it leads to. `steering_paths._link` does this.
- A link that is created, removed or retargeted is therefore a change of the same key at both ends, whatever the real paths are.
- A link that resolves to nothing (dangling, or a loop) is recorded as unreadable, so it becomes a `check_error`.
- A checkout's `.git` container now holds `read:gitdir <gitdir> common <common>`. `compared` compares a container present at both ends by its value. So a `.git` that leads elsewhere is one finding.
- A hooks directory that does not exist is recorded as `read:dir`, the same value as a listed one. Creating that directory is not a container change; its hooks still compare as before.
- `commondir` is read whenever `lexists`, so a dangling one makes `.git` a `check_error`.

**Class B: a value from an executor's file reached line-based text output unescaped.** This class covers finding 4. A config value can hold a newline (`\\n` unescapes to one), and so can a hook file's name. The new `steering_paths.one_line` escapes a backslash and every character that is not printable. It is applied where a finding becomes text:
- the `summary` of `steering_finding` and `steering_error`;
- each field of `worker reconcile`'s `path class before after` line.

The JSON fields stay raw, because JSON escapes them and `merged` matches paths against porcelain.

## Fix round 1 (block by `gpt-5.6-sol-high` on cef67a38)

First merged `origin/WIP/improvements-0-3-1` (c2c8f2e3, no conflicts). The fix is commit b4c69de9. The six findings fall into two classes.

**Class C: a location git must read that cannot be followed was treated as absent.** This class covers five findings: a missing gitdir target, a missing `commondir` target, a dangling link above an include, a dangling link above a hooks directory, and a looping link above a hooks directory. Rework 3 only checked whether the name itself was a dangling link. A link higher up the path made `lexists(name)` false, so the name was recorded as `absent`. `_gitdirs` accepted any gitdir or common dir path. **Design change, one rule:** the new `steering_paths._unresolved(name)` finds the deepest part of the name that exists (the name itself, or a directory above it) and requires it to resolve. A dangling link, a loop or a part with no access is a path git cannot read: `_link` records it as a `check_error` under the name. This replaces Rework 3's dangling check on the last part only, so there is one rule for every config file and hooks-directory name. `_gitdirs` raises when the gitdir or common dir is not an existing directory, so `.git` is a `git_config` `check_error` and the git probes are skipped. A missing name under ordinary missing directories (no link) is still `absent`.

**Class D: an empty `core.hooksPath` value was ignored.** The snapshot skipped empty values, so it watched the default directories, which git no longer uses then. With git 2.43, `git rev-parse --git-path hooks/pre-commit` gives `/pre-commit`, and a commit tries only `/pre-commit` (seen with strace). **Change:** an empty value is a value that names no directory (`None` in the `hooks` map). Like any unconditional value, it turns the defaults off. Only an empty value under an `includeIf` keeps them watched, as before. I do not watch `/`: only root can write there, and hashing every regular file at the filesystem root (a swap file, for example) would hit the time budget on every turn. The docstring and docs state this limit.

## Probes

Fix round 1. Each probe is a public turn on the test layout, and the script was kept outside the tree. Six were new `CONTAINER_ROWS` rows; each fails at cef67a38 and passes at b4c69de9:
- Empty `core.hooksPath`, then a hook written in the default `.git/hooks`: no finding, and the probes run (row `empty_hookspath`).
- Include under a dangling directory link, clean turn: one `check_error` at the include (`git_config`) (row `include_under_dangling_link`).
- `hooksPath` under a dangling directory link, clean turn: one `check_error` (`git_hook`) (row `hooks_under_dangling_link`).
- `hooksPath` under a looping link, clean turn: one `check_error` (`git_hook`) (row `hooks_under_link_loop`).
- Worktree `.git` naming a missing gitdir: one `check_error` for `.git`, probes skipped (row `gitdir_missing`).
- `commondir` naming a missing directory: one `check_error` for `.git`, probes skipped (row `commondir_missing`).

Other probes:
- Include under a looping link: one `check_error`. Pass.
- Link above an include made dangling during the turn: one `check_error`. Pass.
- Missing include under ordinary missing directories (no link): clean, still `absent`. Pass.
- Empty `hooksPath` only under a non-matching `includeIf`, hook written in the default directory: found, defaults still watched. Pass.
- Empty `hooksPath` followed by `hooksPath = X`, hook written in X: found. Pass.
- Worktree gitdir deleted during the turn: one `check_error` for `.git`, probes skipped. Pass.
- Clean turn on the default layout: no findings. Pass.
- All 13 Rework 3 probes re-run: same results as listed below. Pass.

### Rework 3
Rework 3. Each probe below is a public turn (`TurnWatch` and `close_turn`) on the test layout; the script was kept outside the tree.

- Include created as a symlink to a file holding `core.fsmonitor`, named by an unchanged config: one `steering_file` (the link name, `absent;core.fsmonitor=unset` to `link:...;core.fsmonitor=touch ...`), probes skipped, sentinel absent. Pass (new `include_link_created` row; fails at 8ab42769).
- `core.hooksPath` symlink retargeted between two populated directories: one `steering_file` for the link. Pass (new `hooks_link_retargeted` row; fails at 8ab42769).
- Dangling symlink as an included config: one `check_error` (`git_config`). Pass (new `dangling_symlink`/`git_config` row; fails at 8ab42769).
- `sshCommand = "ssh\\nevil"`, then reconcile: one physical line for the finding. Pass (new `config_value_with_newline` row; fails at 8ab42769).
- Worktree `.git` retargeted to a forged gitdir (`commondir` back to the common dir, a hook inside): one `steering_file` for `.git`, probes skipped. Pass (probe).
- Include through a directory symlink (`dl/x.gitconfig`), with `dl` retargeted: one finding for the name. Pass (probe).
- Include symlink retargeted between two files with the same bytes: one finding. Pass (probe).
- Include symlink removed: one finding, `link:...` to `absent`. Pass (probe).
- Default `.git/hooks` replaced by a symlink to another populated directory: one finding (`read:dir` to `link:...`). Pass (probe).
- `hooksPath` a dangling link at both ends: one `check_error` per turn, probes skipped. Pass (probe). This fails closed on every turn while that link stays dangling, by the one rule.
- `hooksPath` link turned into a loop: one `check_error`. Pass (probe).
- `hooksPath` switched between two plain directories: still one `git_config` finding. Pass (probe; unchanged).
- Common `config` a symlink, retargeted to a copy: one finding for the link, plus `absent`/created findings for the two real files, whose parent is the read `.git`. Pass (probe; each is one path).
- Worktree gitdir `commondir` turned into a dangling link: one `check_error` for `.git`. Pass (probe).
- Hook named `pre\ncommit` created: every summary and reconcile line is one physical line. Pass (probe).
- Clean turn with an include link and a `hooksPath` link in place: no findings. Pass (probe).
- Hook file links: not changed. A hook's value is the sha256 of what it resolves to (A1), so a retarget to different bytes is found. A retarget to identical bytes changes nothing git runs. Checked by reading the code.

### Earlier rounds

- `hooksPath` set unconditionally, hook written in the default `.git/hooks`: no finding (the `HOOKS_CONFIGS` rows now also write `ignored-by-git`). Pass.
- `hooksPath` set only under a non-matching `includeIf`, hook in the default directory: still found. Pass (existing row).
- Hooks directory with 200 entries, one added (cap transition): exactly one `check_error` naming the directory. Pass (new row).
- Hooks directory over the cap at both ends with one hook replaced: one `check_error`. Pass (existing test, and probe).
- Hooks directory holding hooks replaced by a FIFO: one `check_error`, no absent hooks. Pass (new row).
- Common config that includes a file becomes mode 000: one `check_error` for the config, the include not reported absent. Pass (new row).
- Config naming `hooksPath` becomes mode 000: one `check_error`, the hooks under that directory and the default ones not reported. Pass (probe).
- Worktree `.git` file becomes mode 000: one `check_error` (`.git`, `git_config`) plus `git_probes_skipped`, nothing else. Pass (probe).
- `hooksPath` switched from X to Y, both holding hooks: one `git_config` finding, no hook findings. Pass (probe).
- `hooksPath` names a missing directory and the turn creates it with a hook: the hook is reported as `absent` to sha256. Pass (probe; a missing directory counts as read and empty).
- `<worktree-gitdir>/hooks` absent at the start, hook created there: reported. Pass (probe).
- Hooks directory deleted: its hooks reported as absent (a real removal). Pass (probe).
- One include reached by a symlink and by its target, target changed: one `git_config` finding. Pass (new row).
- Hooks directory reached by two names (a `hooksPath` link to the default): one listing. Checked by reading the code (`resolved_path` plus `dict.fromkeys`), as before.
- Red/green: with base 3efc97a7's `steering_paths.py`, `git_config_text.py` and `worker_turn_check.py`, all 4 new rows and 5 `HOOKS_CONFIGS` rows fail. With the change, all 22 pass.

- Rework 2: an include the unchanged common config names, missing at the start and created with `core.fsmonitor`, through a public turn: one `git_config` finding (`absent;core.fsmonitor=unset` to the digest), probes skipped, sentinel not run. Pass (new `include_created` row; fails at 3ccb81da).
- Rework 2: an include deleted under its unchanged config: one `steering_file` finding. Pass (new `include_deleted` row; fails at 3ccb81da).
- Rework 2: a nested include (included by an include) created, then deleted: one finding each. Pass (probe).
- Rework 2: an `includeIf` target created under an unchanged config: one finding. Pass (probe).
- Rework 2: `config.worktree` created when missing at the start: one finding. Pass (probe; already covered by the `.git` container, now also recorded `absent`).
- Rework 2: an include dropped by its includer: only the includer's finding, the dropped file not reported. Pass (probe).
- Rework 2: a clean snapshot pair with missing includes recorded: no findings. Pass (probe).
- Rework 2: hooks checked by reading the code: every hook's parent is a hooks directory recorded as a `read:` marker, a missing directory included, so a hook created or deleted there already compares.
## Touch zones

The final list is the brief's list, unchanged. `specy_road/schemas/worker-record.schema.json` needed no change: it already lists `steering_changed` and describes it. No call site outside the zones changed.

## Verification

- Fix round 1: `pytest -q tests/test_steering_file_guard.py`: 34 passed. The steering tests plus the test files that import the changed modules: 587 passed. `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK. Red/green: with cef67a38's `steering_paths.py`, the 6 new rows fail and the other 28 pass.
- `pytest -q tests/test_steering_file_guard.py`: 28 passed (rework 3).
- `pytest -q -n 4`: 5990 passed (rework 3).
- Red/green (rework 3): with HEAD 8ab42769's `steering_paths.py`, `worker_turn_check.py` and `worker_reconcile.py`, the 4 new rows fail and the other 24 pass. With the change, all 28 pass.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean.
- Red/green: with the four product files at base 7cc1b7c0, both new tests fail (`over_the_cap`, `unparsable_ready`). With this change, both pass.

## Notes for reviewers

- I dropped a `fifo` row for `git_config` (a FIFO as an included config). With that FIFO in place before the turn, git's own `git status` at the turn's start blocks on it (300 s), before any of this code runs. The snapshot side of a FIFO is covered by the `fifo` hook row.
- The turn-start `git_state` (`git status` and others in `TurnWatch.__init__`) still runs before the next turn. If the previous turn changed `core.fsmonitor`, it runs under it. That turn was already flagged `steering_changed`, and refusing the next turn is outside this leaf (M22.31 refuses at finish).

## Added

- `steering_paths._open_regular`: opens without blocking and refuses anything that is not a regular file once open (FIFO or special file, or a swap after stat; A3).
- `steering_paths._in_time`, `SNAPSHOT_SECONDS`, `_until`: the snapshot time budget, so a timeout is a `check_error` (A3).
- `steering_paths._hook_value`, `_add_hook`: a hook's value is the sha256 of the regular file it resolves to, and a subdirectory is skipped (A1, A3). They replace `_value` and `_add`.
- `steering_paths._hooks_dir` cap branch: more than 200 entries raises, so the directory is a `check_error` on every comparison; the listing stops at 201 (A2).
- `worker_turn_check.PROBES_SKIPPED`: one `git_probes_skipped` finding, also recorded when there is no snapshot (A3).
- `worker_turn_check._turn_findings` no-snapshot branch: one `check_error` per class naming the worktree (A3).
- `worker_runner._finish` try/except around `fresh_ready`: an unparsable READY is the turn's completion error, and the check runs before it (A4).
- Test row `fifo` for a hook in `UNREADABLE_ROWS`: a special file fails closed without blocking (A3).
- Test `test_a_hooks_directory_over_the_cap_fails_closed_even_when_a_replaced_hook_keeps_it_over` (A2, A6).
- Test `test_an_unparsable_ready_through_the_worker_runner_still_ends_with_one_check_holding_the_config_change`: a fake `claude` on PATH writes a READY with byte FF and runs `git config` (A4, A6).
- Changed tests (expectations only, to match the acceptance's value format): `unchanged_symlink_written_through` now compares sha256 values, not `link:` values. The `unavailable` snapshot case now expects one `check_error` per class plus `git_probes_skipped`.
- Rework, `steering_paths.Entry.parent`, `READ` markers, `compared`: an absence counts as a change only where its container was read in full (review findings 3 and 4, and the hooksPath switch).
- Rework, `steering_paths._config_file` keyed by `resolved_path`: one file reached by two names is one finding (review finding 2).
- Rework, `_git_top` defaults only when every `hooksPath` value is `includeIf`-only: A1's selection (review finding 1).
- Rework, `git_config_text.ConfigFile` and the `parent`/`conditional` of `read_chain`: give the snapshot each file's includer and condition.
- Rework, `_gitdirs` raises on a missing or invalid `.git`: fail closed instead of silently watching nothing.
- Rework, `HOOKS_CONFIGS` rows also write a hook in the default directory, asserted unreported when `hooksPath` applies (review finding 1).
- Rework, test `test_a_container_one_end_could_not_list_is_its_one_finding_and_one_file_is_one_finding`, four rows: `hooks_over_cap`, `hooks_dir_becomes_fifo`, `including_config_unreadable`, `include_reached_by_two_names` (review findings 2 to 4).
- Rework 2, `read_chain` lists a missing file with its `FileNotFoundError`, and `_config_file` records it as an `absent` entry: an include created or deleted under an unchanged includer compares (review finding).
- Rework 2, test row `include_created` in `test_a_changed_fsmonitor_is_reported_before_any_git_command_could_run_it`: the public-turn regression the review asked for (sentinel absent, probes skipped).
- Rework 2, test row `include_deleted` in `CONTAINER_ROWS`: the deletion side of the same class.
- Rework 3, `steering_paths._link`: records each non-real name of a config file or hooks directory as `link:<real path>`, and a dangling or looping one as unreadable (review findings 1 to 3).
- Rework 3, `steering_paths.compared` container branch: a container present at both ends compares by value, so a retargeted `.git` is a finding (same class, probe).
- Rework 3, `.git` container value `read:gitdir <gitdir> common <common>`, and a missing hooks directory recorded as `read:dir`: what the container branch compares, without a finding for a hooks directory merely created.
- Rework 3, `_gitdirs` reads `commondir` whenever `lexists`: a dangling one fails closed instead of reading as missing (same class, probe).
- Rework 3, `steering_paths.one_line`, applied to the steering finding summaries and to reconcile's lines: one finding, one line (review finding 4).
- Rework 3, test row `include_link_created` (fsmonitor test), `hooks_link_retargeted` (`CONTAINER_ROWS`), `dangling_symlink`/`git_config` (`UNREADABLE_ROWS`), and the `first` parametrization `config_value_with_newline` of the clean-turn reconcile test: one regression per review finding. `CONTAINER_ROWS` now names expected paths with `real_path`, which equals `resolve()` for the existing rows and keeps a link's own name.
- Fix round 1, `steering_paths._unresolved`: one rule. The deepest existing part of a name git reads must resolve, else `check_error` (class C). It replaces `_link`'s check on the last part only.
- Fix round 1, `_gitdirs` directory check: a gitdir or common dir that is not an existing directory raises, so `.git` is a `check_error` (class C).
- Fix round 1, `None` key in the `hooks` map for an empty `core.hooksPath`: the value turns the defaults off and names no directory (class D).
- Fix round 1, test rows `empty_hookspath`, `include_under_dangling_link`, `hooks_under_dangling_link`, `hooks_under_link_loop`, `gitdir_missing` and `commondir_missing` in `CONTAINER_ROWS`. Their helpers are `_empty_hookspath`, `_unresolvable` and `_noop`. Two changes to the shared test: it now names expected paths as findings do (worktree paths project-relative, others `abspath`, so a name is not resolved through its dangling parent), and it requires `git_probes_skipped` exactly when a row expects a finding.
- Mocks: none added.
