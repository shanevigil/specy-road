# Implementation summary: M11.69 — A leaf that adds a schema key can be gated and finished

## What changed

A record is now valid when **either** the installed schema or the schema as a
specy-road checkout has it *at the record's own revision* accepts it. The
installed copy is checked first; the revision copy is consulted only when the
installed copy rejects the record, so the happy path costs nothing extra.

The revision depends on where the data was read:

| Data | Read from | Schema revision consulted |
| ---- | --------- | ------------------------- |
| `REVIEW-*.md`, `READY-*.md` (gate, handoff status, finish) | `work/reviews/<node>/` | the record's own `commit` (`git show <commit>:specy_road/schemas/<name>`) |
| `roadmap/orchestration.yaml` at a ref (the gate's integration-branch policy) | `git show <ref>:…` | that same `ref` |
| `roadmap/orchestration.yaml`, `roadmap/git-workflow.yaml` in the working tree (`validate` inside finish, `review_required`, every `_flag`) | working tree | the working tree's `specy_road/templates/project/schemas/…` |

"A specy-road checkout" is a git root holding `specy_road/__init__.py`, found
by walking up from the repo root (or the record's path) without running git.
In an adopter repo there is no such copy, nothing runs, and only the installed
schema counts: behaviour there is unchanged.

Trust: the gate's bar still comes from the integration branch, validated
against the integration branch's own schema, so a feature branch cannot loosen
the schema its policy is checked against. A review/READY record is checked
against the schema at the commit it names; it only counts at the commit under
review (or a bookkeeping-only carry), whose schema the reviewers approved. A
record value never reaches git as an option (a `-`-leading revision is refused).

- **A1** — `specy_road/schema_revision.py` (new) does the lookup;
  `review_files._schema_errors` (READY, REVIEW, RCA), `orchestration_config.validate_orchestration_dict`
  / `parse_orchestration_text` / `load_orchestration_config`, and
  `git_workflow_config.validate_git_workflow_dict` / `load_git_workflow_config`
  consult it. `review_gate.py` and `bundled_scripts/finish_task.py` needed no
  change: both go through these loaders (`evaluate_gate`, `gate_holds_at_head_or_exit`,
  `review_required`, and finish's `validate` subprocess). Tests:
  `tests/test_schema_revision.py`, including a leaf that adds a policy key
  (working-tree read, `HEAD` read, then the gate and finish's
  `gate_holds_at_head_or_exit` once the integration branch has the key).

## Touch zones (final)

- `specy_road/review_files.py`, `specy_road/orchestration_config.py`,
  `specy_road/git_workflow_config.py`, `tests/` — changed.
- `specy_road/review_gate.py`, `specy_road/bundled_scripts/finish_task.py` —
  confirmed in the path, no change needed.
- **New module outside the listed zones: `specy_road/schema_revision.py`.**
  `review_files.py` was at 399 of 400 lines and `review_gate.py` at 400, so the
  shared lookup could not live in a touch-zone file; please add it to the zones.

## Not covered (outside this leaf's zones or not reached by gate/finish)

- **Worker records** (`worker_state.py`, outside the zones) still use the
  installed copy only. They are runtime state written by the coordinator's own
  installed specy-road and bind to no commit, so gate and finish never see one
  written by a leaf's code.
- **Registry** is already validated against the project's own `schemas/`
  copy (`validate_roadmap_checks.py`), not the installed one.
- `review record --file <draft>` checks the draft at its own path: a draft
  outside a specy-road checkout (e.g. `/tmp`) is checked against the installed
  copy only. `ready` builds its file in a temp directory but writes only keys
  its own code knows.

## Verification

- `python -m pytest tests/test_schema_revision.py -q` — 8 passed.
- Red check: with `accepted_at_revision` stubbed to `return False`, the five
  positive tests fail and the three fallback tests pass.
- `specy-road file-limits` — OK (`review_files.py` 400, `git_workflow_config.py` 395).
- `python -m pytest -n auto -q` — 3384 passed, 2 skipped.
- `ruff check specy_road tests scripts` reports two C901 findings that exist
  at the base commit (`orchestration_config.load_availability_overlay`,
  `review_packet_uncommitted_refs.py:82`); neither function was touched.
  `scripts/check_clones.py` could not run here (pylint not installed).

## Added

- `specy_road/schema_revision.py` — new module (file-limit caps on the touch-zone files): the revision lookup, shared by the three loaders.
- `schema_revision.checkout_top` — finds the git root holding `specy_road/__init__.py` without running git, so adopter repos never shell out.
- `schema_revision._installed_text` (cached) — the installed copy's text, to skip a revision copy identical to it.
- `schema_revision._validator` (cached by text) — compiles a revision copy once; returns `None` for invalid JSON / JSON Schema so a broken copy never accepts anything.
- `schema_revision.revision_text` — reads `specy_road/<sub>` at a revision or in the working tree.
- Guard in `revision_text`: refuses a non-string, empty or `-`-leading revision, so a record's `commit` value cannot become a git option.
- `schema_revision.accepted_at_revision` — whether the revision copy accepts the data; false outside a checkout, for a missing file, or a copy equal to the installed one.
- `review_files._schema_errors(…, path)` — new `path` argument; returns no errors when the copy at the record's `commit` accepts it.
- `orchestration_config.validate_orchestration_dict(…, repo_root, rev)` / `parse_orchestration_text(…, repo_root, rev)` — optional arguments (old calls unchanged); `load_orchestration_config` passes the ref (or the working tree).
- `git_workflow_config.validate_git_workflow_dict(…, repo_root)` — optional argument; `load_git_workflow_config` passes the working tree.
- Mocks: none.
- `tests/test_schema_revision.py::test_a_policy_key_the_leaf_adds_validates_where_the_file_is_read` — A1's policy-key case, working tree and `HEAD` reads.
- `…::test_the_gate_and_finish_pass_once_the_integration_branch_has_the_key` — the gate and finish's `gate_holds_at_head_or_exit` pass with the key on the integration branch.
- `…::test_a_review_field_the_leaf_adds_counts_at_that_commit_only` — a review-record field counts at the commit whose schema has it, not at an earlier one.
- `…::test_a_handoff_key_the_leaf_adds_keeps_its_ready_file` — handoff status's `latest_ready` keeps a READY with a new key.
- `…::test_a_git_workflow_key_the_leaf_adds_keeps_the_review_switch_readable` — `require_implementation_review_before_finish` stays readable with a new git-workflow key.
- `…::test_outside_a_specy_road_checkout_only_the_installed_schema_counts` — adopter behaviour unchanged.
- `…::test_a_checkout_copy_equal_to_the_installed_one_changes_nothing` — an unchanged copy does not widen anything.
- `…::test_a_record_value_never_reaches_git_as_an_option` — the option guard.
