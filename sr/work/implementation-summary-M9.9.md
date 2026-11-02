# Implementation summary: M9.9 — tests at risk

## Summary

New `specy-road impact <ID> [--ref REF] [--zones]` lists the Python test files that
import a leaf's code at any depth. `specy_road/impact.py` reads every `.py` blob at
REF (one `git ls-tree` plus one `git cat-file --batch`, with no checkout), parses the
imports with `ast` (relative imports resolved against the importing file's package,
each parent package counted as imported) and walks the reverse import graph from
the targets to the test files (`test_*.py`, `*_test.py`). Targets are the `.py`
files changed in `merge-base...REF` (diff mode) or the `.py` files under the node's
touch zones at REF (`--zones`). If the diff changes any `conftest.py`, the output is
the single line `ALL`. Otherwise a final `not analysed: <n> files` line counts the
changed files that are not Python, plus the `.py` files at REF that do not parse
(their imports are unknown). It only appears when n > 0. Sources are parsed from
their blob bytes, so `ast.parse` honours a coding cookie or BOM the way Python does. Paths are git-root
relative, like `specy-road integrity`. Zones are matched against the
project-relative form, like the packet's changed paths. The command is advisory: it
exits 0 whatever it lists, and exits 1 only when the target or git cannot be resolved.

The executor prompt written at pickup (`do_next_prompt.write_agent_prompt`) now has a
`## Tests at risk` section after `## Planned test changes`. It holds the `--zones`
list at the pickup `HEAD` (or `_none found_`). `review-packet` has a
`## Tests at risk` section after `## Test integrity` with the diff list. Both are
rendered by `impact.section_lines`, which shows at most 50 paths and then
`… and <n> more`. The packet section is computed from git objects only, so it is
deterministic for the same refs.

Module naming: a regular package (one with `__init__.py`) is imported from its top
only. Above that top, any directory may be a `sys.path` root or a namespace package,
so every dotted suffix from there to the git root is registered. For example,
`src/pkg/api.py` with no `__init__.py` files is `src.pkg.api`, `pkg.api` and `api`,
while `specy_road/bundled_scripts/x.py` is only `specy_road.bundled_scripts.x`.
Relative imports resolve by the importing file's directory, which gives its git-root
dotted name, so they also work inside namespace packages. A name shared by several
files links to all of them, which over-reports rather than under-reports. Out of scope: imports the
static graph cannot see, such as scripts run as subprocesses (for example `cli.py`
→ `python -m specy_road.bundled_scripts.*`) and `importlib` with computed names.
The doc says so.

## Changes

- `specy_road/impact.py` (new): graph, `Impact`, `impact_for_diff`, `impact_for_zones`, `section_lines`.
- `specy_road/bundled_scripts/impact_cli.py` (new): thin CLI on `resolve_target_or_exit`, like `integrity_cli.py`.
- `specy_road/cli.py`: `impact` → `impact_cli.py` in `_SCRIPTS`.
- `specy_road/cli_usage.py`: `impact` usage lines; `review-packet` lists the new section.
- `specy_road/bundled_scripts/do_next_prompt.py`: `_tests_at_risk_lines`, wired into `write_agent_prompt`.
- `specy_road/bundled_scripts/review_packet.py`: `tests_at_risk_section`, wired after test integrity; module docstring renumbered.
- `docs/orchestration-review.md`: new `## Tests at risk` section.
- `CHANGELOG.md`: `[Unreleased] / Added` entry.
- `tests/test_impact.py` (new); `tests/test_review_packet.py`: the provenance-label count goes from 3 to 4, because the new section carries the same `_Computed by review-packet from git_` label as the other git-computed sections. The count is still exact.

Touch zones confirmed: every changed path is inside the declared zones. `generate_brief.py` is not touched, as the planning sheet asks.

## Review round 1 (gpt-6.1-sol, block on A1)

R1: namespace packages under `src/` (no `__init__.py`) were missing from both the diff
and `--zones` results, because names started only at the topmost `__init__.py` and
relative imports resolved from that name. Fixed in `impact.module_names` (every suffix
above the regular-package top) and `impact._package` (the directory path). The
fixture's diff and `--zones` tests now run twice, with and without
`src/pkg/__init__.py`, and expect the same exact output, `tests/test_api.py` included.
Both namespace cases fail on the reviewed commit `7bcb714` and pass now. The `--zones`
list for this repository at the same commit is unchanged (153 = 153), so the wider
naming adds no noise here.

## Review round 2 (gpt-6.1-sol, block on A1)

R1: blobs were decoded as UTF-8 with replacement, so a valid Latin-1 source with a
coding cookie and a non-ASCII identifier failed to parse and its imports silently
vanished, in both modes. Fixed so that `_read_blobs` / `python_sources` keep bytes
and `imported_names` parses them directly, honouring the cookie. A file that still
does not parse now returns `None` from `imported_names`, and `tests_importing` counts
it. That count is added to `not analysed` in both modes. New public CLI tests: a
Latin-1 `tests/test_latin.py` importing `pkg.core` is listed by `--zones` and by the
diff, and a broken `src/pkg/broken.py` adds 1 to `not analysed` in both modes. Both
tests fail on the round-1 commit `296d1db` and pass now. This repository has no
unparsable `.py` file at HEAD (493 parsed), so the new count adds no noise here. The
docs and changelog wording for `not analysed` were updated to match.

## Verification

- Round 2: `pytest -p no:cacheprovider tests/test_impact.py tests/test_review_packet.py tests/test_do_next_prompt.py` → 31 passed; `ruff check specy_road tests scripts` and `specy-road file-limits` → clean.
- Round 1: `pytest -p no:cacheprovider tests/test_impact.py tests/test_review_packet.py tests/test_do_next_prompt.py` → 29 passed; `ruff check specy_road tests scripts` and `specy-road file-limits` → clean.
- Round 0: `pytest tests/test_impact.py tests/test_review_packet.py tests/test_do_next_prompt.py tests/test_integrity.py tests/test_integrity_gate.py` → 57 passed.
- `specy-road file-limits` → OK.
- `ruff check specy_road tests scripts` → all checks passed.
- `python scripts/check_clones.py` (pylint 4.1.3) → 0 new. One stale baseline entry predates this leaf (refresh_schemas/refresh_stubs).
- `python scripts/check_test_private_imports.py` → 0 new. One stale baseline entry predates this leaf (`review_packet._changed` in `test_review_round6_evidence.py`).
- Full `pytest` at round 0 (`7bcb714`) → 2766 passed, 2 skipped in 1439s (exit 0). Not re-run for rounds 1 and 2, which change only `impact.py`, `tests/test_impact.py`, and (round 2) the `not analysed` wording in the docs and changelog.
- Smoke test on this checkout: `python -m specy_road.bundled_scripts.impact_cli M9.9 --zones` printed 153 test files in about 0.9 s.

## Walkthrough

1. Read `tests/test_impact.py::_FILES`, the fixture (10 Python files, with `tests/test_api.py` → `pkg/api.py` → `pkg/core.py` through a relative import), then the three A3 tests: diff, `--zones` and conftest.
2. Check `impact.tests_importing` / `module_names` / `imported_names` against those expectations.
3. Check the two section call sites and the 50 cap (`test_pickup_prompt_lists_zone_tests_capped_at_fifty`, `test_packet_section_lists_diff_tests_capped_and_byte_identical`).

## Added

### Helpers
- `impact.Impact` + `lines()`: one result shape for the CLI output and both sections (ALL / list / not-analysed line).
- `impact.is_test_file`: the A1 test-file rule (`test_*.py`, `*_test.py`).
- `impact.impact_for_diff`: diff mode (A1/A2), with the conftest → ALL short-circuit.
- `impact.impact_for_zones`: `--zones` mode (A1), used by the CLI and the pickup prompt.
- `impact.python_sources` / `_read_blobs`: reads the tree at a commit from git objects in one batch, so the result is deterministic (A5) and fast. Per-file `git show` was too slow for a whole repo. Returns bytes (round 2) so the source encoding is Python's to decide.
- `impact.tests_importing`: reverse-graph walk from the targets to the test files.
- `impact.module_names` / `_package`: import names for a path (every suffix above the regular-package top, for namespace packages), and the directory a relative import starts from. Round 1 removed `_parts`.
- `impact.imported_names`: `ast` import extraction, relative imports resolved, parent packages included.
- `impact.section_lines`: the shared `## Tests at risk` rendering with the 50-path cap (A4/A5).
- `do_next_prompt._tests_at_risk_lines`: the prompt section (A4).
- `review_packet.tests_at_risk_section`: the packet section (A5).

### Branches / guards
- `impact_for_*` return `None` when git cannot answer, and the sections render `_(cannot compute …)_`. Prompt writing must not fail outside a git checkout (existing prompt tests use non-git tmp dirs).
- `_tests_at_risk_lines` skips the computation when `HEAD` does not resolve, for the same reason.
- `tests_importing` keeps module names for targets deleted at REF, so a test that still imports a deleted module is listed.
- `imported_names` returns `None` for unparsable sources (`SyntaxError`/`ValueError`, including a bad declared encoding), and `tests_importing` counts them into `not analysed` (round 2), so they cannot crash the walk or vanish silently.
- `imported_names` skips a relative import that climbs above the git root (it cannot resolve).
- `python_sources` skips symlinks (mode 120000), whose blob is a path, not source.
- `impact_cli` exits 1 when there is no commit, or no merge base in diff mode, or git fails, matching `integrity_cli`.

### Mocks
- none

### Tests
- `test_diff_lists_tests_through_a_two_level_chain_and_counts_other_files[regular|namespace]`: A1/A2/A3, exact diff output, including the non-Python count; the `namespace` case is R1's reproduction.
- `test_zones_use_the_modules_under_the_touch_zones[regular|namespace]`: A1/A3, exact `--zones` output, plus a second zone that selects a different test; the `namespace` case is R1's reproduction.
- `test_conftest_change_prints_all`: A2/A3, exact `ALL`.
- `test_coding_cookie_source_is_parsed_with_its_declared_encoding`: round-2 R1 reproduction; a Latin-1 test with a non-ASCII identifier is listed by `--zones` and by the diff.
- `test_unparsable_python_counts_as_not_analysed`: round-2 guard; an unparsable `.py` adds to `not analysed` in both modes rather than vanishing.
- `test_deleted_module_still_lists_its_importers`: covers the deleted-target guard.
- `test_pickup_prompt_lists_zone_tests_capped_at_fifty` (3 and 55 tests): A4, the list and the cap with a count of the rest.
- `test_pickup_prompt_says_none_found`: A4, the "none found" case.
- `test_packet_section_lists_diff_tests_capped_and_byte_identical`: A5, the diff list, the cap, identical output from two builds, and the section's position in the packet.
