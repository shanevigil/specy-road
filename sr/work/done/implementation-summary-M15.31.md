# Implementation summary: M15.31

## Touch zones (confirmed)

- `specy_road/review_delegate.py`
- `specy_road/review_delegate_harness.py` (split from review_delegate for file-limits)
- `specy_road/orchestration_config.py` (re-exports routing helpers)
- `specy_road/orchestration_routing.py` (split from orchestration_config for file-limits)
- `docs/orchestration-models.md`
- `tests/`

## Behaviour

- **A1:** `_Harness` resolves the launch model like `worker_ops_launch._cli_for`: profile → `harness_model(entry, prof.api_id)`; no profile → `harness_model(entry)` (roster id).
- **A2:** Before `save_run`, `delegate` raises `DelegateError` when `api_id` is `None` and `routing` is not `dynamic` (no RUN record).
- **A3:** After attempts, `check_run` on the last attempt log drives `file_review(model_check=…)`; RUN json records `requested_model` and `reported_model`; stderr uses `check_note` on mismatch.
- **A4:** `entry_launch_model` / `entry_routing` treat any harness with no resolved model as `dynamic` (cursor without profile still uses empty profile api for routing); `routing_problem` names `harness_model` before `pinned: true` when launch model is `None`.

## Verification

```bash
pytest tests/test_review_delegate.py tests/test_dynamic_routing_reviewers.py tests/test_prompt_channel_cli_run.py tests/test_roster_harness_model.py -n 4 -q
specy-road file-limits
```

## Added

- `specy_road/review_delegate_harness.py` — `_Harness` and `HarnessSetupError`; keeps `review_delegate.py` under the line cap.
- `specy_road/orchestration_routing.py` — `entry_launch_model`, `entry_routing`, `routing_problem`; keeps `orchestration_config.py` under the line cap.
- `_no_model_refusal` in `review_delegate.py` — exact A2 CLI sentence.
- `_delegate_locked` in `review_delegate.py` — locked turn body extracted so `delegate()` stays at merge-base ruff complexity.
- Refusal branch in `delegate()` before `save_run` — A2, no RUN when model is none and not dynamic.
- `requested_model` / `reported_model` on RUN dict — A3 audit fields.
- `model_check` passed to `file_review` in `delegate()` — A3 record + gate exclusion.
- `tests/test_review_delegate.py` — four tests for A1–A3 (no-profile argv, refusal, dynamic launch, mismatch + `review list`).
- `tests/test_dynamic_routing_reviewers.py` — A4 unit test for claude-code `api_id: unknown`; relaxed gate problem assertion for no-model entries; fresh-process routing import regression (fix round 2).
- Docs paragraph and routing table row in `docs/orchestration-models.md` — review delegate + any-harness dynamic routing.

## Probes

- `review_delegate_harness.py` vs pre-split `review_delegate.py` `_Harness` (parent of 44f67d0a): all six launch-path comments restored; no other `_Harness` lines lost comments.
- `review_delegate.py` after the split: launch-path logic lives only in the harness module; inline comments on `_attempts`, `delegate`, and `_close` unchanged from merge base.
- `orchestration_routing.py` / `orchestration_config.py`: new routing code, not a move from an commented block; no launch-path comments applicable.
- `orchestration_config` ↔ `orchestration_routing` import order (fix round 2): module-level imports removed from routing; fresh-process `python -c` import of routing alone succeeds.
- `review_delegate_harness.py` ↔ `review_delegate.py`: harness imports config helpers only inside functions except the cycle-safe `HarnessSetupError` path; no config re-import of harness at module level.
- `docs/orchestration-models.md` and tests/: no module-split comment class; spot-checked for duplicated launch-path prose — none added.
- `ruff check` on `delegate` vs merge base `8f684959`: complexity back within limit after extracting `_delegate_locked`.

## Fix round 1 (grok-4.7-low)

Restored launch-path comments in `review_delegate_harness.py` when `_Harness` moved for file-limits (chore default command, harness_bin, Codex `-o` output, RUN log, symlink replacement, custom-command resume, structured-output flags).

## Fix round 2 (gpt-6.1-sol-low)

Lazy-import `harness_model` and `roster_entry` inside `orchestration_routing` so importing routing before `orchestration_config` finishes re-exporting it does not raise `ImportError`.
