# Implementation summary for M10.7

Output budgets with --full on packets, briefs and plans (`output-budgets-with-full`).

## Summary

Each output specy-road writes into a model's context now carries a budget with a pointer to the rest:

- **A1 — review packet diff cap.** `review-packet --max-diff-lines N` (default 1500). Past the cap the packet inlines the first changed files whole (in `git diff` order, as many as fit under N lines), lists every remaining path with its `+`/`-` counts from `git diff --numstat`, and names the full diff it wrote to `work/reviews/<NODE_ID>/DIFF.patch` beside `PACKET.md`. `0` means no cap and no `DIFF.patch`: every packet build first removes any `DIFF.patch` an earlier capped run left in the review directory, and only a capped build writes a new one (review round 2, `gpt-6.1-sol`, required change). A packet under the cap takes the unchanged code path and is byte-identical to before (tested by comparing the default against `--max-diff-lines 0`).
- **A2 — brief size line.** The brief header gains one line: `_Size: N bytes. Largest sections: `## 4. …` n B; …_`, where N is the brief's own total (the line counts itself; a fixed-point loop settles the digit count) and the sections are the brief's numbered `## N.` sections, not the `## Intent` headings of inlined sheets. `specy-road brief` warns on stderr past 65536 bytes, naming the three largest sections. The warning is printed only by the `brief` command's `main`; `render_brief` stays pure for the packet and prompt callers.
- **A3 — `grind-session --plan --json --fields KEY,...`.** Prints only those top-level plan keys (`event` and `ts`, the JSONL envelope, stay). An unknown key, or an empty list, is an argparse error naming the valid keys; `--fields` without `--plan --json` is an argparse error too. `PLAN_FIELDS` in `session_plan_render.py` is the single list, and a test pins it to the full dict's keys.
- **A4 — grouped validate warnings.** The no-acceptance warning and the `|`-joined-criterion warning are each one line counting the nodes and listing every id, followed by one fix hint with `<NODE_ID>` as placeholder. The per-leaf cap (`_WARN_CAP`) now applies only to `warn_unauthored`, which was already grouped. The grouped line keeps the phrase `has no acceptance criteria` because two tests outside this leaf's touch zones assert it (`tests/test_review_round6_policy.py`, `tests/test_validate_strict.py`); both pass unchanged.
- **A5 — docs.** `docs/dev-workflow.md`: the diff cap, `DIFF.patch` and the brief size line. `docs/grind-session.md`: `--fields` (the file sits exactly at its 500-line cap, so the example JSON's `waves` array was compacted to one line to pay for the new sentences). `cli_usage.py` mentions all three flags/lines.

## Changes

Touch zones as listed by the PM, plus `tests/test_project_layouts.py`, which the roadmap added to this leaf's zones after the first review blocked on it; nothing outside them was edited:

- `specy_road/bundled_scripts/review_packet.py` — `MAX_DIFF_LINES`, `DIFF_NAME`, `_split_files`, `_numstat`, `_capped_diff`; `_diff`/`build_packet`/`main` take `max_diff_lines`; `_diff` removes a stale `DIFF.patch` before deciding whether to cap.
- `specy_road/bundled_scripts/brief_acceptance.py` — grouped warnings; the size helpers (`section_sizes`, `with_size_line`, `size_warning`, `print_size_warning`, `SIZE_WARN_BYTES`) live here because `generate_brief.py` sits at its 400-line cap (it is now exactly 400).
- `specy_road/bundled_scripts/generate_brief.py` — calls `with_size_line` and `print_size_warning`; docstring folded by one line to stay under the cap.
- `specy_road/bundled_scripts/session_plan_render.py` — `PLAN_FIELDS`; `session_plan_to_dict(plan, fields=None)`.
- `specy_road/bundled_scripts/grind_session_args.py` — `--fields`, `_plan_fields` validation.
- `specy_road/bundled_scripts/grind_session.py` — `_emit_plan(..., fields)`.
- `specy_road/cli_usage.py`, `docs/dev-workflow.md`, `docs/grind-session.md`.
- `tests/test_project_layouts.py` — `test_the_brief_is_identical_across_layouts` also strips the `_Size:` line (asserting each brief has exactly one) before comparing, since A2's total counts the nested-only `Project root` line and so legitimately differs by layout (review round 1, `cursor-grok-4.6-high`, required change).
- Tests: `tests/test_review_packet.py`, `tests/test_generate_brief.py`, `tests/test_session_plan.py`, `tests/test_validate_acceptance_coverage.py` (the last one's three assertions on the old per-leaf wording were updated to the grouped format A4 specifies; `test_the_warning_is_capped` became `test_the_warning_is_one_line_per_class_with_one_hint`).

Not done, on purpose: the planning sheet's "orchestration.md packet section" note. `docs/orchestration.md` is outside the touch zones and A5 does not require it; a one-sentence pointer to the cap in its `PACKET.md` section is a follow-up for the coordinator.

## Verification

- `pytest tests/test_review_packet.py tests/test_generate_brief.py tests/test_session_plan.py tests/test_validate_acceptance_coverage.py tests/test_project_layouts.py` — 103 passed (re-run on the round-3 fix; the extended zero-cap test fails without it).
- `specy-road file-limits` — OK (grind-session.md 500/500, generate_brief.py 400/400).
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood` — OK.
- `python scripts/check_test_private_imports.py` — 0 new (ruff and pylint are not installed in this environment, so the C901 and clone gates were not run locally).
- Full `pytest`: at `99748af` (round 2) 2532 passed, 2 skipped, 0 failed. At `cf7ae41` (round 3 fix) the suite could not finish: other worktrees' suites held the machine at load average 40–84 and every run past ~10 minutes was killed by the harness. What did run at `cf7ae41`, all green: the first 110 of 219 test files (1255 passed, 2 skipped), 235 more tests from the second half (0 failed before the kill), and the five touch-zone files above (103 passed). Not run at `cf7ae41`: roughly 1040 tests in the second half, among them `tests/test_review_evidence.py`, `tests/test_review_round6_evidence.py` and `tests/test_review_hardening.py`, which also build packets. The round-3 change is one `unlink(missing_ok=True)` in `_diff` plus the extended test.

## Walkthrough

1. `specy-road review-packet <ID> --max-diff-lines 40` on a branch with a large diff: see "**Diff capped at 40 lines**", the `+/-` list, and `work/reviews/<ID>/DIFF.patch`.
2. `specy-road brief M0.3 --repo-root tests/fixtures/specy_road_dogfood | sed -n 5p` then `| wc -c`: the numbers match.
3. `specy-road grind-session --plan --json --fields ready,totals --repo-root tests/fixtures/specy_road_dogfood`; then with `--fields nope` for the error.
4. `specy-road validate` on a repo with several open leaves lacking acceptance: one `warning:` line plus one `fix each with:` line.

## Added

### Helpers
- `review_packet._split_files` — one chunk per file so whole files can be kept under the cap.
- `review_packet._numstat` — `+/-` counts per path for the files not inlined.
- `review_packet._capped_diff` — the capped rendering plus the `DIFF.patch` write.
- `review_packet.MAX_DIFF_LINES`, `DIFF_NAME` — the default and the patch name (`review_files.py` is outside the zones).
- `brief_acceptance.section_sizes` — numbered-section sizes, shared by the size line and the warning.
- `brief_acceptance._size_line`, `with_size_line` — the header line whose total includes itself.
- `brief_acceptance.size_warning`, `print_size_warning`, `SIZE_WARN_BYTES` — the stderr warning past 65536 bytes.
- `session_plan_render.PLAN_FIELDS`, `_plan_dict` — the valid key list and the unfiltered dict.
- `grind_session_args._plan_fields` — `--fields` parsing and validation.

### Branches or guards
- `_diff`: `max_diff_lines and diff.count("\n") > max_diff_lines` — the cap path; `0` falls through unchanged.
- `_diff`: unconditional `DIFF.patch` `unlink(missing_ok=True)` at the start — a patch from an earlier capped run must not outlive an uncapped (`0`), under-cap or empty-diff packet that does not name it; the capped path writes it afresh.
- `_capped_diff`: numstat row count must equal chunk count, else paths come from the `diff --git` headers with `?` counts — a safe fallback for an unexpected numstat shape.
- `_plan_fields`: `--fields` without `--plan --json` is an error, so the flag is never silently ignored.
- `warn_acceptance_missing` / `warn_acceptance_merged`: early return when nothing to warn about (replaces the per-leaf loop).

### Mocks
- `test_main_prints_the_size_warning_on_stderr`: monkeypatches `generate_brief.render_brief` to return an oversized brief, so the warning path is exercised without a 64 KB fixture.
- `test_plan_json_fields_prints_only_those_keys`: monkeypatches `grind_session.gather_plan` to return a computed plan, so `run_session --plan` runs without git.

### Tests
- `test_diff_past_the_cap_keeps_first_files_whole_lists_the_rest_and_writes_the_patch` — A1 cap behaviour.
- `test_max_diff_lines_zero_means_no_cap_and_no_patch` — A1 `0`; extended in round 3 to build a capped packet (`max_diff_lines=1`) in the same review directory first, then assert the `0` packet inlines the whole diff, does not name `DIFF.patch`, and the file is gone (fails without the fix).
- `test_a_packet_under_the_cap_is_byte_identical_to_an_uncapped_one` — A1 byte-identity.
- `test_main_passes_max_diff_lines_through` — A1 CLI flag; also the "first file alone exceeds the cap" edge (0 of 2 inlined).
- `test_render_brief_header_states_its_size_and_largest_sections` — A2 line, total equals `len(text)`, inlined headings excluded.
- `test_size_warning_names_the_largest_sections_past_the_threshold` — A2 threshold and ordering.
- `test_main_prints_the_size_warning_on_stderr` — A2 stderr.
- `test_to_dict_fields_keeps_only_those_keys_and_plan_fields_names_them_all` — A3 filter and `PLAN_FIELDS` parity.
- `test_fields_flag_parses_and_rejects_unknown_keys` — A3 parsing, unknown key error naming valid keys, flag without `--plan --json`.
- `test_plan_json_fields_prints_only_those_keys` — A3 end to end through `run_session`.
- `test_the_warning_is_one_line_per_class_with_one_hint` — A4 (replaces the per-leaf cap test).
- `test_the_brief_is_identical_across_layouts` (changed, not added) — strips the layout-dependent `_Size:` line on both briefs, after asserting each has exactly one; the rest stays byte-identical.
