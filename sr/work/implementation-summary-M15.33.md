# Implementation summary: M15.33 — refused review record leaves a trace

## Touch zones (confirmed)

- `specy_road/review_rejected.py` (new)
- `specy_road/bundled_scripts/review_cli.py`
- `specy_road/review_run_status.py`
- `tests/`

No other paths were required. `review_record_write._review_record` already calls `cmd_review_record`, so delegate and CLI filing refusals share the same marker logic without editing that module.

## Behaviour

- After `resolve_target` and roster membership succeed, `run_review_record` writes `work/reviews/<NODE_ID>/REJECTED-<model>.md` on refusal. Front matter carries `commit` and `refused_at`; the refusal text is the body. A successful filing clears the marker. Models not on the roster never get a marker, even when notes are missing or invalid.
- `list_reviews` still only loads `REVIEW-*.md`.
- `handoff status` and `review list` (text and `--json`) show `record refused <age> ago: <first line>` via `review_run_status`; JSON includes a `refused` map per model with `age` and `reason`. Markers pinned to another commit are hidden.

## Fix round (Sol-low block on `9fb66b53`)

- `review list --json` via `review_list_payload` and a `--json` flag on the list subcommand.
- Roster lookup before `ReviewRecordTrace.roster_resolved`; refusals that precede roster membership do not call `write_rejected`.
- `test_record_refuses_unrostered_models_and_human` expects `REJECTED-human.md` for the rostered human refusal and no marker for unrostered `sol`.
- M15.33 tests call `run_review_cli` from `tests.review_delegate_helpers` instead of a private `_run` import.
- Restored the three signing/write comments beside their operations in `run_review_record`.

## Fix round (Grok block on `0975ddd9`)

- Removed unused `ReviewRecordTrace.target_resolved` alias (only `roster_resolved` is used).

## Fix round (Sol-low block on `a4ba3e64`)

- `read_rejected_marker` validates YAML and mapping front matter; malformed files become a `marker unreadable: <path>` line while status commands continue.
- `review list --json` exits 1 when `review_list_payload` carries an `error`, matching text mode.

## WIP merge (note 505, `de590732`)

- Merged `origin/WIP/improvements-0-3-1` (M14.1 sibling-repo approvals). `review_cli.py` keeps the thin `cmd_review_record` → `run_review_record`; M14.1’s `sibling_heads_field(root)` and `gate_policy_summary(after, [])` live in `review_rejected.py` so record signing still covers sibling heads.

## Fix round (Sol-low block on `de590732`)

- `rejected_state` uses `list_reviews` (case-insensitive prefix) to detect a current valid record for the model at the gate commit, not only `review_path(...).is_file()`.
- `read_rejected_marker` treats any read or YAML parse failure (including `UnicodeDecodeError`) as `marker unreadable: <path>`; absent paths still return `None`.
- Removed unreachable `gate is None` from the escalation guard in `_print_review_list_text` (`t is None` already short-circuits).

## Fix round (Sol-low block on `2e2b8d11`)

- Dropped duplicate age formatting in `review_rejected.py`; `rejected_state` uses public `relative_age` from `orphaned_claims.py` (formerly private `_age`).

## Probes

- Unrostered model with a missing notes path: roster check runs first; no `REJECTED-*.md` and no reviews directory (`test_unrostered_model_with_missing_notes_writes_no_marker`).
- Unrostered model with valid notes front matter: no marker (`test_roster_miss_does_not_write_a_marker`, `test_record_refuses_unrostered_models_and_human` for `sol`).
- Rostered human interactive-refusal path: writes `REJECTED-human.md` (`test_record_refuses_unrostered_models_and_human`).
- `review list --json` payload includes the same `refused` entry as handoff status JSON (`test_handoff_status_and_list_show_refused_text_and_json`).
- Milestone with open leaves before roster lookup: returns `milestone_open_problem` without a marker (`test_an_unfinished_milestone_is_not_awaiting_its_full_review`).
- Delegate and direct `review record` refusals after roster resolution: still write markers (`test_delegated_refusal_writes_the_same_marker`, existing A1 tests).
- Repo-wide search for `target_resolved` callers before removal: only the dead alias in `review_rejected.py`; no external references.
- Sequence-valued and malformed YAML `REJECTED-*.md` on disk: `review list` and `handoff status` print `marker unreadable: …` and complete (`test_malformed_rejected_marker_is_reported_without_breaking_list`).
- Unknown node and bad `--ref` with `review list --json`: exit 1 with JSON `error` and stderr `error:` (`test_review_list_json_exits_nonzero_on_target_resolution_errors`).
- Lowercase `review-<model>.md` at the gate commit with a valid record: `refused` omitted in handoff JSON and list JSON (`test_a_lowercase_review_record_suppresses_the_refusal`); canonical-path-only check would have left the marker visible.
- `REJECTED-*.md` with invalid UTF-8: `marker unreadable` on text list, handoff status, and `refused_unreadable` in list JSON (`test_invalid_utf8_rejected_marker_is_unreadable_in_status_interfaces`); other marker readers only call `read_rejected_marker` / `unreadable_rejected_lines`.
- Escalation line when `t is None`: condition is `t is None or not gate.passed`; `gate` is assigned only in the `else` branch, so no other `gate is None` paths in `review_cli.py`.
- Repo-wide search for the same ``Nd``/``Nh``/``Nm``/``under 1m`` age formatter: only `orphaned_claims._age` and the copy in `review_rejected`; consolidated as `relative_age` in `orphaned_claims`, one caller in `rejected_state`.

## Added

- `write_rejected`, `clear_rejected`, `rejected_state`, `read_rejected_marker`, `unreadable_rejected_lines`, `ReviewRecordTrace`, `run_review_record` in `review_rejected.py` — marker I/O, safe reads, roster-gated tracing, and the full `review record` command.
- `_review_record_setup`, `_review_record_validate`, `_review_record_signed_data`, `_review_record_finish` in `review_rejected.py` — split `run_review_record` for ruff C901 without behaviour change.
- `refused_text`, `refused_by_model`, `extend_handoff_refused`, `print_refused_list`, `review_list_payload` in `review_run_status.py` — display, handoff JSON, and list JSON payloads.
- `refused` / `extend_handoff_refused` / `review list --json` wiring in `review_cli.py`.
- `relative_age` in `orphaned_claims.py` — shared ``Nd``/``Nh``/``Nm``/``under 1m`` formatter (renamed from `_age`; used by orphaned-claim reports and `rejected_state`).
- `tests/test_review_rejected_m15_33.py` — A1–A3 plus fix-round boundary tests for list JSON, missing notes, and roster ordering.
