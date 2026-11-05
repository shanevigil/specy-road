# Implementation summary: M13.3

Base `94c56865`; code commit `b46c464d`.

## What changed

- **A1 — `agents_block` setting.** `agents_block_mode()` reads `agents_block` from the git root's `.specyrd/manifest.json` (`full` default; `minimal`). `render_agents_lines(project_root)` returns a single pointer line for `minimal` (the "Written by … (minimum …)" text plus the pointer to `.specyrd/AGENTS.md` and both addenda), so the managed section is 3 lines with its markers. `apply_agents_md_block`, `agents_md_block_state` and `print_migration` pass the project root, so `refresh-stubs`, `upgrade` and `validate`'s stale check honour it with no change of their own. `render_agents_lines()` with no argument still returns the full block. The full template (`agents-md-block.md`) gains one line saying why it repeats the floor and naming the setting. `claude-md-block.md` repeats no bullets, so it is unchanged.
- **A2 — notice about overlapping text.** `print_migration` (which `upgrade` and `refresh-stubs` already call before writing) now calls `print_rules_overlap` whenever `.specyrd/AGENTS.md` does not exist yet. It prints the new file's `##`-and-deeper headings, then one `rules:` line per heading in the project's `AGENTS.md` outside the managed section that matches one (case-insensitive, whitespace-normalised, with its line number), then "compare these with … and drop the copy that is stale". It writes nothing.
- **A3 — per-harness totals.** Every harness's `context:` line ends with `total N lines, B bytes`; Cursor and Copilot become `— no documented limit; total N lines, B bytes per session`. The Claude Code line also appends `(<file> imported twice, counted once)` for each counted file that is loaded directly or imported more than once. The total was already deduplicated by `claude_imports`; the change is that the line now says so.
- **Docs and prompts:** `docs/install-and-usage.md` (the upgrade notes) documents all three in one bullet, kept to one line so the file stays under its 400-line cap. `suggested_prompts/bootstrap-agents-md.md` mentions the minimal option where it describes the stub.

## Touch zones (final)

The listed zones, plus **`specy_road/agents_md_report.py` (new)**. `agents_md_block.py` was at 392/400 lines, so the new code lives in this module, as the file-limits rule says to do. Please add it to the zones. No caller outside the zones changed.

## Things for reviewers to check

- `tests/test_enforced_rules_pointers.py` has a budget for the `AGENTS.md` stub (`_STUB_LINES, _STUB_BYTES`). Its comment says a rule added to the stub needs a maintainer's approval and must raise the budget. A1 requires one added line in the full block, so I raised the budget from 17 / 2,063 to 18 / 2,260 and noted M13.3 in the comment. Please confirm this is acceptable.
- The toolkit's own `sr/AGENTS.md` section is now stale by exactly the new line (`agents_md_block_state('sr') == 'stale'`). `sr/` is outside the touch zones, so I left it alone. `specy-road refresh-stubs` fixes it.
- The "at most 3 lines" in A1 counts the markers here (the measure `validate` reports as "specy-road section N lines").

## Verification

- `pytest -n 4`: 3962 passed
- `ruff check specy_road tests`: clean
- `specy-road file-limits`: OK
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK

## Added

- `specy_road/agents_md_report.py`: a new module, split out for file-limits.
- `agents_block_mode()`: reads the A1 setting. The `except` covers a missing or unreadable manifest, which happens in a repo with no `specyrd init`; existing tests that have no manifest exercise it.
- `minimal_lines()` / `_MINIMAL_LINE`: the pointer-only section for A1.
- `_headings()` / `_key()`: heading extraction and case/whitespace normalisation for A2.
- `print_rules_overlap()`: the A2 notice. Its `except` covers an unreadable `AGENTS.md`, mirroring `_read` in `agents_md_block`.
- `total()`: the per-harness total suffix for A3.
- `claude_reread()`: counts how many times Claude Code reaches each file and names the ones it reaches more than once (A3).
- A branch in `render_agents_lines()`: the minimal mode.
- A change in `print_migration()`: the early return now depends only on whether the rules file exists, so the overlap notice also fires when `AGENTS.md` has no section.
- Mocks: none.
- Test `tests/test_agents_md_report.py::test_full_and_minimal_sections_render_and_refresh_stubs_honours_the_setting`: A1, covering both renders, refresh-stubs writing a 3-line section, the setting kept in the manifest, and the context line showing the smaller section.
- Test `…::test_upgrade_names_project_headings_the_new_rules_file_repeats`: A2, with a duplicated heading under different case and spacing; also checks that upgrade honours `minimal` and that the notice does not repeat once the file exists.
- Test `…::test_claude_code_total_counts_a_doubly_imported_file_once`: A3's double-import note and total.
- Updated expected context lines in `tests/test_agents_md_block.py` (3 tests) and `tests/test_context_meter_harnesses.py` (1 test) for the new totals format, plus the stub budget in `tests/test_enforced_rules_pointers.py`, as described above.

## Fix round 1 (maintainer decision)

Maintainer principle (2026-11-04): the root `AGENTS.md` and `CLAUDE.md` belong to the developer, and specy-road budgets only what it owns. A1 was rewritten in f19b16ec to match.

- Removed the reason line I had added to `specy_road/templates/specyrd/agents-md-block.md`. The full block is byte-for-byte what it was at base `94c56865`.
- Reverted `tests/test_enforced_rules_pointers.py` to base: `_STUB_LINES, _STUB_BYTES = 17, 2063` with its original comment.
- `docs/install-and-usage.md` needed no change: its bullet already says the full block repeats the seven floor rules so an agent that reads only `AGENTS.md` (Codex) still has them, and names `"agents_block": "minimal"`.
- `tests/test_agents_md_report.py` no longer asserts the removed line. The minimal setting, the overlap notice and the per-harness totals are unchanged.
- The note above that `sr/AGENTS.md` is stale no longer applies, because the full block is unchanged.
- Verified with the targeted tests (81 passed) and `specy-road file-limits` (OK).

Added in this round: none; one test assertion was removed because the line it checked no longer exists.

## Fix round 2 (Sol R1–R3)

I first merged `origin/WIP/improvements-0-3-1`. Code commit: see `git log` (message "M13.3 fix round 2").

- **R1:** heading extraction now follows CommonMark ATX: up to three spaces of indent, a space or tab after the `#` run, and an optional closing `#` run.
- **R2:** fenced code is skipped, for both backtick and tilde fences of length 3 or more. A fence closes only on the same character, at least as long, with nothing after it. An unclosed fence runs to the end of the file, as CommonMark says.
- **R3:** `claude_reread` counts every `@` import line, including two in the same importer. The total stays deduplicated because `claude_imports` lists each file once.

**What I reused:** `normalize_heading` (`specy_road/text_sections.py`) for case and whitespace folding; it replaces my `_key`. The fence logic comes from the CommonMark helpers in `bundled_scripts/validate_stale_commands.py` (`_fence_marker`, `_fence_closes`, `_opening_is_code_span`), imported lazily as `decisions._unfenced_lines` does. I could not call `_unfenced_lines` itself because it drops the line numbers the notice prints. I also could not use `text_sections.LEVEL2_RE`, because it matches level 2 only and allows any indent.

**`specy_road/text_sections.py`, checked for every helper:**

- `normalize_heading`: reused; it is called as is.
- `split_sections`, `find_section` and `LEVEL2_RE`: cannot replace `_headings`. All three use `LEVEL2_RE`, which:
  - matches level 2 only (the rules file's `### Load order` would be lost);
  - allows any indent (so a 4-space code line would count as a heading);
  - has no fence or setext awareness;
  - returns no line numbers.
- Extending `text_sections.py` would mean editing a file outside the touch zones, and changing `LEVEL2_RE` would change brief and search output. I left it unedited; no edit there is needed for this leaf.
- `read_text_safely` fits `print_rules_overlap`'s file read, but swapping it in is a cosmetic change, so I left the read as is.

### Fix round 2: probes

Each probe below runs through `refresh-stubs` in `test_refresh_stubs_names_only_real_matching_headings`, as a parametrized case.

| Probe | Result | Case |
|---|---|---|
| Three-space-indented `   ## Task loop` | matched | `indent-3`; R1, failed before |
| Fenced `## Task loop` | not matched | `fenced`; R2, failed before |
| Mixed tilde/backtick fences, a longer opener, and a shorter or different closer that does not close | handled | `fence-kinds`; failed before |
| Setext `Task loop` / `---------` | matched, as a level-2 heading | `setext`; was missed before, real defect fixed |
| Setext `===` | ignored, like ATX `#` (level 1 is a title) | consistent with ATX, no change |
| Trailing `#`'s (`## Task loop ##`) and a tab after the run | matched | `tab-closing-run`; already worked; `## C#` keeps its `#` |
| 4-space or tab-indented `## …` | code, not a heading | `indented-code`; already worked |
| Unclosed fence | everything after it is code | `unclosed-fence`; matched before, real defect fixed |
| `---` after a list item or a blank line | thematic break, not a heading | `thematic-break`; checked so the setext support does not over-match |

R3 has its own case, `one-importer-twice`, in `test_claude_code_total_counts_a_doubly_imported_file_once`; it failed before.

The full block and its 17/2063 budget have no diff from base.

Verification: the targeted pytest command in READY (121 passed), `ruff`, and `specy-road file-limits` (OK).

### Added in round 2

- `_ATX`, `_ATX_ANY`, `_SETEXT_2`, `_CODE_INDENT`, `_LIST_OR_QUOTE` regexes: CommonMark heading, paragraph-end and code rules for R1 and the setext probe.
- The `_headings` fence and paragraph state machine: R2, setext and unclosed fences.
- Removed `_key` in favour of `normalize_heading`.
- Tests: `test_refresh_stubs_names_only_real_matching_headings`, with 8 parametrized cases. The R3 test is now parametrized, with a new `one-importer-twice` case.
- Mocks: none.

## Fix round 3 (Sol R1–R3; A2 bounded by e89b49a1)

- **Scope:** `_headings` is cut down to the bounded input class that A2 now sets. It recognises ATX headings indented 0–3 spaces, and skips fenced code and HTML comments. The round-2 setext and paragraph logic, and its `_SETEXT_2`, `_CODE_INDENT` and `_LIST_OR_QUOTE` regexes, are removed as out of scope, along with the `setext` and `thematic-break` test cases. The out-of-scope list is in the docstring and in the `docs/install-and-usage.md` line, which stays one line, so the file is still within its cap.
- **R1:** fences now use their own `_FENCE` regex, which allows 0–3 spaces of indent to open or close. The round-2 import of `validate_stale_commands`' fence helpers is dropped, because their regex allows any indent: that is right for the stale-command scan, which accepts list-indented fences, and wrong here. A backtick in a backtick fence's info string still means it is not a fence.
- **R2:** comments that open and close on one line are stripped. An unclosed `<!--` hides lines until a line containing `-->`, or to the end of the file. Text before the `<!--` on its line still counts.
- **R3:** the reread note formats `path.resolve().relative_to(top.resolve())`, the in-repo path. That cannot raise, because `inside()` already accepted the resolved path. That was the only `relative_to` in `agents_md_report.py`; `agents_md_block._display` already falls back safely.

### Tests (all failed on the previous commit)

New `test_refresh_stubs_names_only_real_matching_headings` cases:

| Case | Input it covers |
|---|---|
| `indented-backticks` (R1) | 4-space backticks are not a fence, so a later heading is found |
| `fence-indent` | a fence opened with 3 spaces; one indented 4 spaces does not close it |
| `html-comments` (R2) | multi-line, one-line and trailing comments |
| `unclosed-comment` | an unclosed comment runs to the end of the file |

New test `test_a_repeated_absolute_import_through_an_outside_link_names_the_file_in_the_repo` (R3): two absolute `@` imports through a symlink outside the repo to `shared.md` inside it.

The full block and its 17/2063 budget have no diff from base. Verification: the targeted pytest command in READY (114 passed), `ruff`, and `specy-road file-limits` (OK).

### Added / removed in round 3

- Added `_FENCE` and `_COMMENT` regexes: R1 and R2.
- Removed the setext and paragraph state, its three regexes, and the `validate_stale_commands` helper import.
- Tests: 4 new parametrized cases and 1 new test; 2 out-of-scope cases removed.
- Mocks: none.

## Fix round 4 (Sol R1–R2)

I first merged `origin/WIP/improvements-0-3-1`, which adds `specy_road/bundled_scripts/refresh_stubs.py` to the zones. My change to that file is one line plus one import name.

- **R1:** the new `_uncommented(line, comment)` helper walks the whole line. After a `-->` it keeps scanning, so a later `<!--` on the same line re-enters a comment, as often as the line does.
  - Fences take precedence: inside a fence, comment markers are text.
  - A fence opener inside an open comment is comment text.
  - A line that starts inside a comment, or starts with one, is not a heading (`<!-- x --> ## y`).
  - The docstring says all of this. I removed the round-3 `_COMMENT` regex.
- **R2:** `render_agents_lines(project_root, mode)`, `apply_agents_md_block(..., mode=)` and `apply_agents_files(..., mode=)` take an optional `agents_block` override. `_block_previews` in `refresh_stubs.py` passes `agents_block_mode(repo_root / prefix)`, the value the real run reads. I chose this over copying the manifest into the temp tree. `agents_md_block.py` is exactly at its 400-line cap.

### Fix round 4: preview/write parity

Each row runs `refresh-stubs --diff`, then the real `refresh-stubs`, and asserts that the previewed `AGENTS.md` hunk equals the diff of the real write. Each row also checks the 3-line section exactly when the setting is minimal. Rows in the second table marked † failed without the R2 fix.

**`test_the_diff_is_what_a_refresh_then_writes[...]`** (the existing test, extended; `_old_repo`, no git, no `AGENTS.md`):

| Parameter | agents_block | Result |
|---|---|---|
| `None` | key absent (full) | parity |
| `full` | full | parity |
| `minimal` | minimal | parity †; failed before |

**`test_the_agents_md_preview_is_what_a_refresh_then_writes[...]`** (new; a git repo):

| Layout | Manifest | Existing `AGENTS.md` | Result |
|---|---|---|---|
| embedded | minimal | text, no block yet | parity †; failed before |
| embedded | full | stale block | parity |
| embedded | missing | none | parity |
| embedded | missing | stale block | parity |
| nested (`project_root: sr`) | minimal | stale block | parity †; failed before |
| nested (`project_root: sr`) | minimal | none | parity †; failed before |
| nested (`project_root: sr`) | full | text, no block yet | parity |

### R1 cases

These are new `test_refresh_stubs_names_only_real_matching_headings` cases:

| Case | Result |
|---|---|
| `adjacent-comments` | passes (coverage) |
| `close-then-open` | fixed; failed before |
| `many-per-line` | fixed; failed before |
| `closed-then-heading` | fixed; failed before. A heading on the line after a closed comment counts; text after `-->` on the comment's own line does not. |
| `comment-in-fence` | passes; `<!--` inside a fence does not start a comment |

The full block and its 17/2063 budget have no diff from base. Verification: the targeted pytest command in READY (146 passed), `ruff`, and `specy-road file-limits` (OK).

### Added / removed in round 4

- Added `_uncommented`: R1.
- Added the `mode` parameter on the three render/apply functions: R2.
- Changed one line in `_block_previews`, and added `agents_block_mode` to its import: R2.
- Removed the `_COMMENT` regex.
- Tests: 5 heading cases; the existing parity test parametrized ×3 and given an `AGENTS.md` assertion; a new 7-row parity test; and a `_between_markers` helper.
- Mocks: none.
