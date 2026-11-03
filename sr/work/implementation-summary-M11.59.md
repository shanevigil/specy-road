# Implementation summary: `M11.59` — split worker_ops and worker_adapters

Base `5676f903`. A pure move: every function, class and constant is byte-identical to its original (checked by
comparing each top-level definition's source text, leading `#:` comments included, old file vs new module), and
every docstring and comment moved with its code. No test file was changed, import lines included.

## A1 — the split

| Module | Lines | Holds |
|---|---|---|
| `specy_road/worker_ops.py` | 59 (was 400) | module docstring, re-exports, the patch-forwarding facade |
| `specy_road/worker_ops_launch.py` | 224 | `delegate`: roster, eligibility, worktree, launch |
| `specy_road/worker_ops_message.py` | 89 | `message`, `resume`, `interrupt` |
| `specy_road/worker_ops_slots.py` | 75 | dead wrappers, stalls, the `max_workers` slot check |
| `specy_road/worker_ops_lifecycle.py` | 75 | `terminate`, `adopt` |
| `specy_road/worker_adapters.py` | 58 (was 398) | module docstring (unchanged), re-exports, `ADAPTERS`, `adapter_for` |
| `specy_road/worker_adapter_base.py` | 175 | types, constants, helpers, the `generic` `Adapter` |
| `specy_road/worker_adapter_claude.py` | 100 | `ClaudeCode` |
| `specy_road/worker_adapter_codex.py` | 64 | `Codex` |
| `specy_road/worker_adapter_cursor.py` | 66 | `Cursor` |

### Where each moved name went

`worker_ops.py` →
- `worker_ops_launch`: `_target`, `_entry_and_harness`, `_check_eligible`, `_check_tree`, `_worktree_for`, `_cli_for`,
  `_preflight`, `_brief_into`, `delegate`, `_launch_locked`
- `worker_ops_message`: `CONTINUE_PROMPT`, `_send`, `message`, `resume`, `interrupt`
- `worker_ops_slots`: `sweep_dead_wrappers`, `sweep_stalled`, `_slot_or_existing`, `_wrapper_gone`
- `worker_ops_lifecycle`: `terminate`, `_terminate_locked`, `adopt`
- stays in `worker_ops`: the re-exports of `handoff`, `interventions_path`, `reclaim`, `record_hook_prompt`
  (`worker_lease`) and `reconcile`, `sync` (`worker_reconcile`), now at the top of the file (no `E402`)

`worker_adapters.py` →
- `worker_adapter_base`: `Capabilities`, `Launch`, `Parsed`, `Unsupported`, `STDIN_INSTRUCTION`, `EFFORT_FLAGS`,
  `CODEX_POLICY`, `REVIEWS_DIR`, `_model_flag`, `linked_worktree`, `_reviews_handoff_dir`, `reviews_dir_into`, `_bare`,
  `Adapter`
- `worker_adapter_claude`: `ClaudeCode`; `worker_adapter_codex`: `Codex`; `worker_adapter_cursor`: `Cursor`
- stays in `worker_adapters`: `ADAPTERS` (and its `HARNESSES` assert), `adapter_for`

### Still importable from the old paths

Every name either old module **defined** is re-exported from it, plus every name it re-exported before
(`worker_adapters`: the `worker_adapter_parsers` names `_SESSION`, `_init_detail`, `_json`, `_snip`, `_text`,
`_tokens`, `placeholder_problem`, `substitute_prompt`, `usage_fields`; `worker_ops`: the `worker_lease` and
`worker_reconcile` names above), and every collaborator a test patches through `worker_ops` (`spawn`,
`process_alive`, `wrapper_gone`) or the CLI catches from it (`WorkerError`, `Unsupported`). Checked by importing the
base-commit modules side by side with the new ones: no defined name is missing. Not re-exported: the old modules' own
imports of collaborators (stdlib modules, `worker_state` / `worker_lease` / `review_*` helpers such as
`list_records`, `foreign_leases`, `git_text`); a grep of `specy_road/`, `tests/` and `scripts/` finds none of them
read through `worker_ops` or `worker_adapters`.

### Monkeypatch targets

None changed. Tests patch `ops.spawn`, `ops.process_alive`, `ops.wrapper_gone` and `ops._preflight`
(`test_review_round4_sol`, `test_models_and_prompt`, `test_review_round6_ops`, `test_worker_queue_message`,
`test_worker_resume_failed`, `test_worker_adapters`). Before the split one namespace held both those names and the
functions that call them; after it the callers live in the parts, so `worker_ops` swaps its module class for a
`ModuleType` subclass whose `__setattr__` also sets the name in each part that has it (`spawn` → launch and
message; `process_alive` → message and lifecycle; `wrapper_gone` → slots; `_preflight` → launch and message).
`monkeypatch.undo` goes through the same path, so the originals come back everywhere. Nothing patches through
`worker_adapters`, so it is a plain module. A new test can patch the part directly
(`monkeypatch.setattr(worker_ops_launch, "spawn", ...)`) or keep patching `worker_ops`.

## A2 — behaviour

- `pytest -n auto`: 3248 passed, 2 skipped (exit 0), on the final code tree.
- `pytest -p no:xdist` (serial): 3248 passed, 2 skipped (exit 0, 37 min). It started on `45ea0107`; the only
  later code change is the comment-only `942e6c37` (noqa → `# re-exported`), and the parallel run above is on it.
- `specy-road integrity M11.59 --ref HEAD`: no removed tests, new skips, lost asserts or pytest config edits. It
  exits 1 with three `new-suppression` findings, all comments moved verbatim with their code (it counts per
  file, so a moved comment is new to its new file): `worker_adapter_base.py:76` (`PLC0415` in
  `_reviews_handoff_dir`), `worker_ops_launch.py:136` (`S602` in `_preflight`), `worker_ops_message.py:44`
  (`PLC0415` in `_send`). A2 requires comments to move with their code, so they stay. The old `F401` noqa on the
  `worker_ops` re-exports is now a plain `# re-exported` comment (ruff here selects only `C901`, so it suppressed
  nothing). Because integrity exits non-zero it is not a `--verify` line; it is reported here instead.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: clean.

## Touch zones

Accurate as listed: every new file matches the `specy_road/worker_ops_` or `specy_road/worker_adapter_` prefix, and
nothing outside the zones needed a change. `worker_runner` (lazy `from specy_road.worker_ops import _send`) and
`worker_reconcile` (lazy `sweep_dead_wrappers`, `sweep_stalled`) keep working through the re-exports. Docs that cite
`worker_adapters.py:<lines>` (`docs/design-notes/agent-performance-research-triage.md`) or `worker_ops.py:101`
(`docs/design-notes/lean-code-census.md`) are dated design notes and were left as they are.

## Added

- `specy_road/worker_ops_launch.py`, `worker_ops_message.py`, `worker_ops_slots.py`, `worker_ops_lifecycle.py`: new
  modules holding moved code; each gets a short module docstring saying what it holds and that it was split from
  `worker_ops`, in the style `worker_lease` / `worker_reconcile` already use.
- `specy_road/worker_adapter_base.py`, `worker_adapter_claude.py`, `worker_adapter_codex.py`,
  `worker_adapter_cursor.py`: likewise, split from `worker_adapters` (the module docstring describing all adapters
  stays in `worker_adapters.py`).
- `worker_ops.py` docstring paragraph: names the four parts, so a reader finds the code.
- `worker_ops._PARTS` and `worker_ops._Facade` (with `sys.modules[__name__].__class__ = _Facade`): keeps
  `monkeypatch.setattr(ops, name, ...)` reaching the moved callers without editing tests (A2). Guard: names
  starting with `__` are not forwarded, so a part's own `__file__` / `__name__` never change.
- Re-exports in `worker_ops` of `spawn`, `process_alive`, `wrapper_gone`, `WorkerError`, `WorkerRecord`,
  `Unsupported`: the patch targets and the types callers reach through `ops`; all were names of the old module.
- `import uuid` in `worker_adapter_claude.py`: `ClaudeCode.launch` uses it (it came from the old module's imports).
- Mocks: none. Tests: none.
