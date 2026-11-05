# Implementation summary: M15.32

Exempt `work/done/implementation-summary-*.md` from file-limits so finish never fails on an archived summary under the template `**/*.md` cap.

## Acceptance

- **A1:** Added `work/done/implementation-summary-*.md` to `SESSION_ARTIFACT_GLOBS` beside the live summary glob, with a comment pointing at `finish_work_artifacts.archived_implementation_summary_rel`.
- **A2:** `tests/test_archived_summary_file_limits.py` runs `specy-road file-limits` on an `init project` scaffold (template `constraints/file-limits.yaml`): a 450-line `work/done/implementation-summary-M1.md` passes; adding a 450-line `work/done/notes.md` fails and names that path.
- **A3:** `docs/file-limits.md` new **Skipped before measurement** section lists archived implementation summaries among paths not measured. Other `work/done/` files and pre-merge destination checks remain out of scope.

## Touch zones (final)

Confirmed unchanged: `specy_road/file_limits_engine.py`, `docs/file-limits.md`, `tests/` (new `tests/test_archived_summary_file_limits.py` only).

## Verification

- `python -m pytest -n 4 -q tests/test_archived_summary_file_limits.py tests/test_file_limits_gitignore.py`
- `python -m specy_road.cli file-limits`

## Added

- `SESSION_ARTIFACT_GLOBS` entry `work/done/implementation-summary-*.md` with finish-archive comment: A1; matches `archived_implementation_summary_rel`.
- `docs/file-limits.md` section **Skipped before measurement**: A3; documents gitignore skip, session artifacts including archived summaries, and `roadmap/archive/`.
- `tests/test_archived_summary_file_limits.py`: A2 CLI test on scaffolded template constraints.
- `tests/test_archived_summary_file_limits.py::_lines`: builds an n-line body for limit fixtures.
- `tests/test_archived_summary_file_limits.py::_init_scaffold`: runs `init project` so constraints match the template.
- `tests/test_archived_summary_file_limits.py::_file_limits`: invokes the public `file-limits` CLI on a repo root.
- `tests/test_archived_summary_file_limits.py::test_archived_implementation_summary_exempt_other_work_done_files_are_not`: asserts archived summary passes and `work/done/notes.md` fails at 450 lines.
- Mocks: none.
