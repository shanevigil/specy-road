---
node_id: M11.24
model: cursor-grok-4.6-high
date: '2026-11-03'
verdict: approve
commit: 7b8ca7a28cd1831263a7f2637b6f6046ad102e8c
delta_from: b4f551b0b280c0aff1296d607165b4fb731f2467
acceptance:
  A1: pass
  A2: pass
findings:
  correctness: []
  regression: []
  boundary: []
  test_integrity: []
commands_rerun:
- python -m pytest -q tests/test_worker_handoff_writable.py tests/test_worker_m310_reconcile_status.py
  tests/test_worker_adapters.py tests/test_worker_cli_fixes.py tests/test_review_files.py
- specy-road file-limits
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: d260f7c1957be16982dae9faa29bda03012726464ab627ca27d2685e362724a2
launch_mode: full
family: xai
independence: distinct-family
---

# Review notes: M11.24 (delta)

Packet commit `7b8ca7a28cd1831263a7f2637b6f6046ad102e8c` on `feature/rm-worktree-handoff-writable`. Delta from prior approval `b4f551b0b280c0aff1296d607165b4fb731f2467`: two files, a test parametrize trim and a matching summary line. No production-code change.

## Acceptance

- **A1 pass.** Unchanged since the prior approval. Custom `channels.cli` still substitutes `{reviews_dir}` (bare or one pair of quotes) via `reviews_dir_into`; the two refusal cases remain. This delta does not touch `worker_adapters.py`.
- **A2 pass.** Unchanged since the prior approval. Codex launch and Cursor launch/resume still pass `--add-dir` in a linked worktree; Codex resume still omits it, documented. Claude default launch coverage remains in `tests/test_worker_m310_reconcile_status.py::test_claude_passes_add_dir_only_in_a_linked_worktree` (re-run with this packet). The delta only drops the duplicate `claude-code` parametrize from `test_default_launch_adds_the_handoff_dir_only_in_a_linked_worktree`, leaving `codex` and `cursor`.

## Findings

No correctness, regression, boundary, or test-integrity findings.

Changed paths match the packet: `tests/test_worker_handoff_writable.py` (touch zone) and `sr/work/implementation-summary-M11.24.md` (leaf artifact). The covering Claude launch test still asserts `--add-dir` only in a linked worktree, then not in the main checkout.

## Excess

The summary still has a `## Added` inventory; this commit updates the launch-test bullet to name the existing Claude coverage instead of listing `claude-code` in the new parametrize.

- *Test pins internals:* none proven. Remaining tests still call `adapter_for(…).launch` / `.resume` and assert public argv or `sh` output.
- *Unreachable defence:* none. No new guards.
- *Duplicated logic:* none. No new functions.
- *Overlapping test:* the `claude-code` launch case this model previously noted is gone. Codex and Cursor remain as distinct input classes.

No excess item belongs in `required_changes`.

## Commands re-run

```
python -m pytest -q tests/test_worker_handoff_writable.py tests/test_worker_m310_reconcile_status.py tests/test_worker_adapters.py tests/test_worker_cli_fixes.py tests/test_review_files.py
```

98 passed (99 on the prior commit; one parametrize case dropped).

```
specy-road file-limits
```

OK: file limits satisfied.