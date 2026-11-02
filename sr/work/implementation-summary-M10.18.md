# Implementation summary: M10.18 `review-file-case`

## What changed

- **A1, canonical-case write.** `review_files.write_review(path, text)` first removes any file in the directory whose name equals `path.name` ignoring case, then writes `path`. On macOS APFS a plain write to `REVIEW-x.md` keeps an existing `review-x.md` name; removing the file first makes the canonical name stick on any filesystem. `review record` writes its record through it, and so does the independence relabel in the same command (`_relabel_independence`), so relabelling a lowercase record also renames it.
- **A2, case-insensitive discovery.** `list_reviews` matches the `REVIEW-` prefix and the `.md` extension in any case (`_files(..., any_case=True)`, which lists the directory rather than globbing `*.md`, so `review-opus.MD` is found too). Each record is reported as `REVIEW-<model>.md` when its name differs from that only in case. Otherwise only the prefix and extension are fixed, for a file that names another model. The real file is kept on the new `ReviewFile.on_disk` field. `round_span` reads mtimes from `on_disk` when it is set. `handoff status`, `review list` and the gate (`evaluate_gate`) all read records through `list_reviews`, so all three find the file and report the canonical name. That includes the gate's own problem lines, which use `review.path.name`.
- READY and RCA discovery is unchanged (case-sensitive), since this leaf covers only reviewer records.

## Line-cap note

Both `specy_road/review_files.py` and `specy_road/bundled_scripts/review_cli.py` were at 397 of the 400-line cap. To make room in `review_files.py` without an exemption:

- collapsed the multi-line signatures of `ready_semantic_errors`, `review_semantic_errors`, `load_ready`, `list_ready`, `latest_ready` and `list_reviews`;
- replaced `latest_ready`'s `if not valid: return None` with `max(..., default=None)`.

Behaviour is the same. Final sizes are 400 (the cap, which is inclusive) and 396 lines.

## Touch zones

Confirmed: `specy_road/review_files.py`, `specy_road/bundled_scripts/review_cli.py`, `tests/`. No other file needed a change. `review_gate.py` reports `review.path.name`, which is now canonical, and `review_gate_ready.py` writes `REVIEW-human.md` itself; the brief covers only agent records.

## Verification

- `pytest tests/test_review_file_case.py`: 7 passed (round 2)
- `pytest tests/test_review_file_case.py tests/test_review_files.py tests/test_review_cli.py tests/test_review_gate.py`: 70 passed (round 2)
- `pytest tests/ -k "review or handoff or worker or gate or finish"`: 842 passed, 2 skipped (round 1, before the extension fix)
- `ruff check` on the changed files: clean
- `specy-road file-limits`: OK

## Added

- `review_files.write_review`: writes a record under its exact name, removing a case-variant first (A1).
- `review_files._canonical`: reports a record found under another case as `REVIEW-<model>.md`, keeping the real file on `on_disk` (A2).
- `ReviewFile.on_disk` field: the real file when the reported `path` differs only in case, so `round_span` can stat it.
- `_files(..., any_case=False)` parameter: case-insensitive prefix and `.md` extension match, used only by `list_reviews` (A2); READY and RCA discovery stay case-sensitive.
- Guard in `_canonical`: uses the model's name only when it matches the file name ignoring case, otherwise fixes just the prefix. This means a misnamed file never gets another model's name.
- `tests/test_review_file_case.py::test_write_review_replaces_a_name_that_differs_only_in_case`: A1 at the helper level; another model's record is left alone.
- `tests/test_review_file_case.py::test_review_record_writes_the_canonical_name_over_a_lowercase_file`: A1 through `review record`.
- `tests/test_review_file_case.py::test_list_reviews_reports_a_lowercase_record_under_the_canonical_name`: A2 discovery, parametrized over a mixed-case model part (`Review-OPUS.md`) and an uppercase extension (`review-opus.MD`).
- `tests/test_review_file_case.py::test_the_gate_counts_a_lowercase_record_and_names_it_canonically`: A2 for the gate, both when it counts the record and in the stale-record problem line, parametrized over `review-opus.md` and `review-opus.MD`.
- `tests/test_review_file_case.py::test_handoff_status_and_review_list_report_a_lowercase_record`: A2 for `handoff status` (state, file name, rounds) and `review list`.
- Mocks: none. Each test writes the lowercase file itself into a temporary directory, so the tests do not depend on the host filesystem's case rules.
