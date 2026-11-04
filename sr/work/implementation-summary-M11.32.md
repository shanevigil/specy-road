# Implementation summary: M11.32 — Unpushed nested-repo commits are reported

Branch `feature/rm-nested-unpushed-report`, base `3f16a0e9` (WIP after the touch-zone update), code commit `10f26990`.

## What changed

- `specy_road/nested_repos.py`: `unpushed_branches(repo_root)` runs
  `git for-each-ref refs/heads` with `%(upstream:short)` and `%(upstream:track,nobracket)`
  in each configured nested repository and returns one dict per local branch
  holding commits its remotes lack: `ahead` (count from the track, past the
  upstream), `no upstream` (no upstream, or an upstream deleted on the remote; count of commits on no remote-tracking ref),
  `no remote` (the repository has none; every commit counts). `describe_unpushed` formats
  one line naming repo, branch and commit count; `report_unpushed` prints doctor's section.
- `specy_road/bundled_scripts/doctor.py`: calls `report_unpushed` after `report_checkout`. It is
  advisory and leaves the exit code alone. The `--help` description names it. The file was at the
  400-line cap, so one `if/else` assignment and one heading tuple were joined onto single lines. No
  docstring, comment or user-facing text was shortened.
- `specy_road/bundled_scripts/session_plan.py`: `SessionPlan.nested_unpushed` (list of those dicts, default empty).
- `specy_road/bundled_scripts/session_plan_git.py`: `gather_session_plan` fills it, because `compute_session_plan` stays pure.
- `specy_road/bundled_scripts/session_plan_render.py`: a `## Nested repos: commits no remote has` text section (only when
  non-empty), the `nested_unpushed` JSON key, and the same key in `PLAN_FIELDS` (so `--fields nested_unpushed` works).

A branch with nothing to push (for example a fresh leaf branch with no upstream) is not listed. The leaf is
about commits that would otherwise be lost, and listing every new branch would be noise. A configured path that is
not a repository is skipped here, because delegate and finish already report it.

## Touch zones (final)

`specy_road/bundled_scripts/doctor.py`, `specy_road/bundled_scripts/session_plan.py`,
`specy_road/bundled_scripts/session_plan_git.py`, `specy_road/bundled_scripts/session_plan_render.py`,
`specy_road/nested_repos.py`, `tests/`. No new module was needed. `doctor.py` is at exactly 400 lines.

## Follow-up (outside zones, not done)

`docs/grind-session.md` shows an example plan JSON and does not mention `nested_unpushed`. `docs/` was not in
the zones.

## Verification

- `python -m pytest -q tests/test_nested_unpushed_report.py`: 7 passed
- `pytest -n 4`: 3711 passed, 2 skipped
- `specy-road file-limits`: OK
- `ruff check` on the touched files: clean

## Added

- `nested_repos._unpushed`: the state and commit count for one branch (no remote / no or gone upstream / ahead). It keeps `unpushed_branches` under the complexity limit.
- `nested_repos.unpushed_branches`: the A1 data, shared by doctor and the plan.
- guard in `unpushed_branches`, `if not is_repo_top(repo): continue`: a configured path that is missing or not a repository would make the git calls fail. Finish and delegate report that case already.
- guard in `unpushed_branches`, `(line.split("\t") + ["", ""])[:3]`: `git_text` strips the output, so the last line loses the trailing tabs of an empty upstream and track.
- branch in `unpushed_branches`, `if commits:`: leaves out a branch with nothing to push.
- `nested_repos.describe_unpushed`: one line naming repo, branch and count, used by the doctor and plan text.
- `nested_repos.report_unpushed`: doctor's advisory section, printed only when something is found.
- `SessionPlan.nested_unpushed` field: carries the list from `session_plan_git` to the renderer.
- `session_plan_render._render_nested_unpushed`: the plan's text section.
- `"nested_unpushed"` in `PLAN_FIELDS` / `_plan_dict`: the JSON output, and `--fields`.
- mocks: none (real git repositories and bare remotes).
- `tests/test_nested_unpushed_report.py`, fixtures `clean_project` / `project`: nested `lib` with branches for ahead, no upstream, upstream gone, no upstream with nothing to push, and a clean `main`; nested `svc` with its remote removed.
- `test_each_unpushed_branch_is_named_with_its_count`: A1 data and wording for ahead, no upstream (and gone), and no remote (A2).
- `test_a_clean_nested_repo_reports_nothing`: the clean case (A2).
- `test_a_configured_path_that_is_not_a_repository_is_skipped`: the not-a-repository guard.
- `test_doctor_lists_them_without_failing` / `test_doctor_is_silent_about_a_clean_nested_repo`: doctor half of A1, and clean.
- `test_plan_text_and_json_list_them` / `test_plan_has_no_section_for_a_clean_nested_repo`: the `grind-session --plan` half of A1 (text, JSON, `--fields`), and clean.
