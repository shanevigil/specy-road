# Implementation summary: M11.41 — The two review-gate settings cannot silently disagree

## Summary

- **A1.** A new module, `specy_road/review_gate_agreement.py`, decides when the two settings disagree. They disagree when `roadmap/orchestration.yaml` exists and its effective `policy.reviewers_required` is above 0, while `review_gate.review_required()` is False. That function is the rule finish itself uses: the gate is on if the working tree or the integration branch turns it on, and counts as on if the integration branch can't be found. The message names `roadmap/orchestration.yaml`, `policy.reviewers_required`, `roadmap/git-workflow.yaml` and `require_implementation_review_before_finish`, and gives the one-line fix: ``set `require_implementation_review_before_finish: true` in roadmap/git-workflow.yaml``.
  - `validate` (`run_validation` in `validate_roadmap_checks.py`): prints `roadmap: error — …` and exits 1. It reuses the `gate` value it already computed.
  - `doctor`: prints `error: …` to stderr first, still lists the branches, worktrees, registry rows and stashes as before, then exits 1. **This changes doctor's behaviour:** before, a dry run always exited 0.
  - `mark-implementation-reviewed`: the "nothing to do" message now says the review gate is not enforced at finish-this-task. The stdout line adds that finish lands without reviews and how to enforce them.
  - Nothing turns the gate on automatically: whether a project reviews is its own decision.
- **What a missing file means.** A missing `orchestration.yaml` counts as asking for no reviewers, even though `DEFAULT_CONFIG` implies one. The schema requires `reviewers_required` ≥ 1, so any existing file requires reviewers. "Both off" can therefore only mean no file and the switch off. Flagging a missing file would have turned every older repo's validate red. An unparseable file is left to the commands that already report its error.
- **A2.** `tests/test_gate_config_agree.py` runs three cases (mismatch, both on, both off) against the helper, `validate`, and `doctor` (exit code and `error:` line). It also checks that a gate turned on only on the integration branch is not a mismatch, and checks the mark-implementation-reviewed message.
- **Dogfood fixture.** `tests/fixtures/specy_road_dogfood` had exactly this mismatch: an `orchestration.yaml` with one required reviewer and the switch unset. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` would now fail, so the fixture's `git-workflow.yaml` now sets `require_implementation_review_before_finish: true`, matching the `init project` template. One test, `test_archiving_a_node_with_an_open_claim_is_refused`, seeds a registry row in a fixture copy. That row now also carries `implementation_review: pending`, as a claim writes when the gate is on. No assertion changed.
- **Docs.** `docs/orchestration-review.md` has a new paragraph after the finish re-check that explains the switch, the mismatch error, and the fix.

## File limits

`doctor.py` (400), `mark_implementation_reviewed.py` (399) and `git_workflow_config.py` (392) were at or near the 400-line cap. The shared code is therefore in the new module **`specy_road/review_gate_agreement.py`**, which needs adding to this leaf's touch zones. `git_workflow_config.py` is unchanged. To stay at 400 lines, `doctor.py` has two code lines joined onto one line each: the `could not read the roadmap` print and the `--fix` `add_argument`. No docstring or comment was removed. `mark_implementation_reviewed.py` is now at 400.

## Touch zones (final)

`specy_road/bundled_scripts/validate_roadmap_checks.py`, `specy_road/bundled_scripts/doctor.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/review_gate_agreement.py` (new), `docs/orchestration-review.md`, `tests/`. `specy_road/git_workflow_config.py` was not needed.

## Verification

- `pytest tests/test_gate_config_agree.py tests/test_doctor.py tests/test_doctor_version_skew.py tests/test_mark_implementation_reviewed_gate.py tests/test_validate_roadmap.py tests/test_archive_limits_and_locks.py tests/test_review_gate.py tests/test_decisions.py`: 110 passed.
- `specy-road file-limits`, plus `validate`, `export --check` and `digest --check` on the dogfood fixture: all exit 0. I removed the `.specyrd/cache` those runs leave in the fixture.
- `ruff check` on the changed Python files: clean. `scripts/check_test_private_imports.py`: clean. `scripts/check_clones.py` could not run here because pylint is not installed.
- A full suite run (`pytest -n 8`) before the archive-test update gave 2 failures in 3,253 tests. One was `test_archiving_a_node_with_an_open_claim_is_refused`, fixed as described above. The other was `test_worker_queue_message.py::test_message_while_running_queues_and_delivers`, a timing race that passes when run alone and is unrelated to this change.
- Red-green: with `gate_config_mismatch` stubbed to return `None`, the three `[mismatch]` cases in `tests/test_gate_config_agree.py` fail (exit 1).

## Added

- `specy_road/review_gate_agreement.py` (new module): holds the shared check, because the files that needed it are at the line cap.
- `gate_config_mismatch(repo_root, *, gate_on=None)`: the single definition of "the settings disagree", shared by validate and doctor. `gate_on` lets validate reuse the `review_required()` result it already has.
- `report_gate_mismatch(repo_root)`: doctor's one-call wrapper that prints `error:` and returns whether there was a mismatch.
- `GATE_KEY` and `GATE_FIX` constants: the switch name and the fix text, so the message and the tests share one spelling.
- Guard `err or data is None` in `gate_config_mismatch`: a missing file asks for no reviewers, and a broken file is reported elsewhere.
- Branch in `run_validation`: error and exit 1 on a mismatch.
- `bad_config` in `cmd_doctor`: doctor reports the error first, still lists the rest, then exits 1.
- Fixture `git-workflow.yaml` line `require_implementation_review_before_finish: true` (with a comment): the dogfood fixture would otherwise fail validate.
- `implementation_review: pending` in `test_archiving_a_node_with_an_open_claim_is_refused`'s seeded row: that is what a claim writes once the fixture's gate is on.
- `tests/test_gate_config_agree.py`: the three cases against the helper, validate and doctor; the gate-on-only-on-the-integration-branch case; the mark-reviewed message.
- Test helper `_repo` (bare `origin`, switch committed on `dev`): doctor needs a remote to fetch, and `review_required` reads the integration branch.
- Test helper `_exit`: turns a `SystemExit` into an exit code.
- Mocks: none (`monkeypatch` sets only `sys.argv` for `validate_roadmap.main`).
