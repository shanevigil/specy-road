# Implementation summary: M22.37 (cursor-cli-harness-test-pass)

## What changed

Checked the documented Cursor CLI default on agent 2026.11.05-86047df (2026-11-08), sandbox on and no `--force`, and recorded it in `docs/orchestration-workers.md` (Cursor CLI, checked 2026-11-08). These are `agent` CLI results. IDE findings stay in the roster and model docs.

- **Worker turn.** `agent -p --trust --sandbox enabled` in a linked worktree ran `git add` and `git commit` to exit 0. The shell policy was `TYPE_WORKSPACE_READWRITE` with only the worktree as a writable root, and a sibling path outside the workspace failed with `Permission denied` in that same turn, so the commit was sandboxed. The worktree gitdir and the common git dir's `objects`, `refs`, `logs` and a new file in the common dir were writable; `.git/config` returned `Read-only file system`. The executor launch still passes `--add-dir` only for the reviews directory. A git `--add-dir` was not added: the commit already succeeds, and granting the common git dir would widen the sandbox past the commit. M22.44's carve-out (objects, refs, logs, `worktrees/<name>`) is the worker-sandbox bind, separate from this CLI sandbox.
- **Model.** `system/init` reports `model`. `composer-2.5` reports `Composer 2.5`; `composer-2.5-fast` reports `Composer 2.5 Fast`. `same_model` matches each pair and does not match them to each other. A launch with no `--model` still reports a model (this account: `Composer 2.5 Fast`). Every turn printed one. The gate's treatment of a missing model stays the decision after 0.3.1.
- **Resume.** `agent create-chat` prints the chat id. `agent -p --resume <id>` with a new prompt keeps that `session_id` and answers the new prompt.
- **Reviewer.** The reviewer launch is `--mode ask` and `--trust`, without `--sandbox` or `--force`. Told to create a file, and told to run a shell redirect, the turn wrote nothing and called no tool. It suits a reviewer.
- **Denial.** A refused shell write stays on the tool result (`failure`, or `success` stderr when the script continues) and the turn's `result` line stays `success`. `Cursor.parse_events` emits one `permission_denied` when that stderr contains `Permission denied`, `Read-only file system` or `Operation not permitted`.
- On 2026-11-08 the same agent build that exited before its first event on 2026-11-05 started here while `kernel.apparmor_restrict_unprivileged_userns` was 1. The AppArmor exit stays the failure mode of a host where the sandbox does not start. The delegate-refusal branch was not taken: the executor can commit.

## Touch zones

Final list: `docs/orchestration-workers.md`, `sr/planning/`, `specy_road/worker_adapter_cursor.py`, `CHANGELOG.md`, `tests/test_worker_adapters.py`. The test file was not in the leaf's zones. The denial event is pinned by extending the existing parser test there; no other out-of-zone file changed. Call sites of the adapter stay unchanged.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worker_adapters.py tests/test_cursor_usage_segments.py tests/test_cursor_usage_cost.py tests/test_cursor_display_name_cost.py tests/test_harness_launch.py tests/test_worker_resume_permissions.py tests/test_worker_turn_check.py tests/test_review_record_write.py tests/test_worker_handoff_writable.py`: 212 passed.
- `ruff check specy_road/worker_adapter_cursor.py tests/test_worker_adapters.py`: clean.
- `specy-road file-limits`: OK (existing warnings on other files).

## Added

- `_DENIAL`: the three sandbox-refusal strings a Cursor shell result prints.
- `_shell_bodies`: the `failure` and `success` objects of a completed shell tool call, because a denial can sit on either.
- `_sandbox_denial`: one `permission_denied` from a matching stderr, so the post-run check sees a refusal the turn result calls a success.
- `Cursor.parse_events`: appends that event after the line's other events.
- Assertions in `tests/test_worker_adapters.py::test_parsers_map_each_harness_output_to_events`: a `failure` of `Permission denied` and a `success` stderr of `Operation not permitted` each emit `permission_denied`, and a clean shell stays one `output` event.
- Mocks: none.
