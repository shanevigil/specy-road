# Implementation summary — M9.3 (`layout-with-outside-change`)

## Scope

Regression coverage for finish-this-task’s implementation check, review-packet changed paths, and merge-mode re-run idempotency across three repository shapes: embedded, nested under `sr/`, and nested with a leaf commit that also changes `README.md` at the git root (outside the project).

Design reference: `docs/design-notes/regression-prevention.md`.

## Touch zones (confirmed)

Only these paths were required for this leaf:

- `tests/test_project_layouts_outside.py` — parametrized tests for A1–A4
- `tests/helpers.py` — `sorted_diff_paths_project_relative` for A3 expectations
- `tests/review_repo_helpers.py` — `make_layout_finish_repo`, merge-mode remote setup, layout constants

No product code changes.

## Acceptance mapping

| Criterion | How it is covered |
|-----------|-------------------|
| **A1** | `LAYOUT_FINISH_SHAPES` and `make_layout_finish_repo` build embedded, nested, and `nested_outside`; `test_layout_fixture_defines_three_shapes` asserts the set. |
| **A2** | `test_implementation_check_sees_work_in_each_layout` calls `implementation_gate_error` for all shapes. `test_nested_outside_would_fail_the_pre_79eaff3_implementation_paths` asserts old path filtering would drop the outside file; manually restoring `specy_road/finish_implementation_check.py` to `79eaff3^` makes `test_implementation_check_sees_work_in_each_layout[nested_outside]` fail with “nothing was implemented”. |
| **A3** | `test_review_packet_lists_every_changed_path` compares `review_packet.changed_paths_section` to `sorted_diff_paths_project_relative` (merge-base..HEAD), including `README.md` for `nested_outside`. |
| **A4** | `test_finish_merge_rerun_is_idempotent` runs `finish_task.main` twice in merge mode; second run exits 0, prints “already merged into dev on origin; nothing to do”, and `dev` SHA plus `roadmap/registry.yaml` bytes on the bare remote are unchanged. |

## Verification

```bash
pytest tests/test_project_layouts_outside.py -v
```

All 11 tests passed (2026-10-29).

Manual A2 check (optional, matches planning sheet):

```bash
git show 79eaff3^:specy_road/finish_implementation_check.py > /tmp/fic_old.py
cp specy_road/finish_implementation_check.py /tmp/fic_new.py
cp /tmp/fic_old.py specy_road/finish_implementation_check.py
pytest tests/test_project_layouts_outside.py -k 'nested_outside and implementation_check' -v  # expect FAIL
cp /tmp/fic_new.py specy_road/finish_implementation_check.py
```

## Commits

Implementation: `189d825f5cd1d7061864baf02fa466b62504a77f` (checkpoint on this branch). Summary: commit that adds this file.

## Added

- `sorted_diff_paths_project_relative` in `tests/helpers.py` — project-relative diff path list aligned with review-packet for A3 assertions.
- `OUTSIDE_ROOT_FILE`, `LAYOUT_FINISH_SHAPES`, `layout_prefix`, `touch_zones_for_layout`, `git_root_relative`, `make_layout_finish_repo`, `prepare_layout_merge_mode_remote` in `tests/review_repo_helpers.py` — shared three-shape fixture and merge-mode bare remote for finish re-run tests.
- `_paths_dropped_before_79eaff3` in `tests/test_project_layouts_outside.py` — documents pre-`79eaff3` implementation-path filtering for A2 without editing product code in CI.
- `layout` pytest fixture parametrized over `LAYOUT_FINISH_SHAPES` — DRY driver for per-shape tests.
- `test_layout_fixture_defines_three_shapes` — A1 guard on shape set.
- `test_implementation_check_sees_work_in_each_layout` — A2 gate passes for all shapes.
- `test_nested_outside_would_fail_the_pre_79eaff3_implementation_paths` — A2 regression oracle for outside-root touch zone.
- `test_review_packet_lists_every_changed_path` — A3 full diff vs packet changed paths.
- `test_finish_merge_rerun_is_idempotent` — A4 second finish in merge mode.
