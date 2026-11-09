# M22.62 — review record refuses empty notes and a shared notes body

`review record` now refuses two filings that used to succeed and read as one review written twice.

- An empty or whitespace-only notes body, after `notes_digest`'s normalisation (line endings joined with `\n`, trailing whitespace dropped). The refusal says the notes go in the body below the front matter and that `notes_sha256` covers only that body. `file_review` puts the answer's `notes` in that body, so whitespace-only notes are the same refusal and come back as a rerun.
- A non-empty digest equal to `notes_digest` of another model's stored REVIEW body for this leaf at the same commit. Candidates are the current `REVIEW-*.md` files `list_reviews` returns with `ok` true, another model id, and the same resolved commit. Signature, roster and policy are not checked. `history/` copies, `REJECTED-` files and files `list_reviews` reports with errors are not candidates. The digest is taken from the stored body, not from the stored `notes_sha256` field. The message names both models, says the bodies match after normalisation, that `findings` and `commands_rerun` are not in the digest, that a body left as the notes template matches too, and asks for this review's own notes. It does not say the record was copied.

The same model re-filing at that commit, and the same body at another commit, are filed as before. `notes_digest` and the gate are unchanged, so a record already on disk, empty body included, still counts.

Before the fix, the two red rows were filed: a schema-valid empty or whitespace body exited 0 and wrote `REVIEW-<model>.md`, and a second model filing the first model's body (different `findings` and `commands_rerun`, including CRLF and trailing whitespace) did the same. After the fix those filings exit 1, write `REJECTED-<model>.md`, and leave no REVIEW record.

Touch zones, confirmed and unchanged: `specy_road/review_rejected.py`, `tests/test_review_record_write.py`, `docs/orchestration-reviewer-output.md`, `CHANGELOG.md`. Call sites outside the zones stay as they are. `file_review` already turns a `review record` refusal into a rerun, and the gate does not grow a uniqueness or non-emptiness check.

Verifier: `python -m pytest tests/test_review_record_write.py -n 4 -q --tb=line`. A run of the same file without xdist passed 55 before this summary; `ready` re-runs it capped at 4 workers.

## Added

### Helpers

- `_notes_normalised` (`specy_road/review_rejected.py`): the body text `notes_digest` hashes, so the empty check uses that normalisation and `notes_digest` stays unchanged.
- `_notes_body_problem` (`specy_road/review_rejected.py`): refuses an empty or whitespace-only body, and a non-empty digest equal to another model's stored REVIEW body at this commit.
- `_submit` (test): files a schema-valid record through `review record` with a chosen notes body and no front-matter `notes` key.
- `_says_empty` (test): the empty-body refusal names the body below the front matter and that `notes_sha256` covers only it.
- `_says_shared` (test): the shared-body refusal names both models, the normalised match, that `findings` and `commands_rerun` are not in the digest, and the notes template, and does not say copied.
- `_TWO`, `_BODY`, `_FIND_A`, `_FIND_B` (test): a two-reviewer roster and the findings the shared-body rows differ by.

### Branches or guards

- `_review_record_validate` calls `_notes_body_problem` after the existing role and rerun checks and refuses through `trace.refuse`, so `REJECTED-<model>.md` is written as for any other refusal.

### Mocks

- none

### Tests

- `test_review_record_refuses_an_empty_or_whitespace_notes_body`: the red empty-body row, including whitespace-only bodies.
- `test_file_review_refuses_whitespace_only_notes_as_a_rerun`: whitespace `notes` from `file_review` is that refusal, as a rerun.
- `test_review_record_refuses_another_models_matching_notes_body`: the red shared-body row, plus the same body with CRLF line endings or trailing whitespace.
- `test_a_matching_body_is_refused_when_the_stored_notes_sha256_differs`: a stale stored `notes_sha256` is not what is compared; the stored body is digested again.
- `test_one_changed_word_in_the_notes_body_is_filed`: one substantive word change is filed.
- `test_the_same_model_refiles_its_own_notes_body`: the same model at the same commit is filed.
- `test_the_same_notes_body_at_another_commit_is_filed`: an equal body at an older commit is filed.
- `test_a_schema_invalid_record_is_not_a_notes_body_candidate`: a file `list_reviews` reports with errors is not a candidate.
- `test_a_notes_body_only_in_history_is_filed`: a `history/` copy is not a candidate.
- `test_two_file_review_calls_with_different_bodies_differ_in_notes_sha256`: two `file_review` calls with different bodies at one commit get different `notes_sha256`.
- `test_an_empty_body_already_on_file_still_counts_in_the_gate`: a record placed as filed before this change, empty body included, still counts.
