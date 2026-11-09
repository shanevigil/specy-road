# M22.63 — a completed worker releases its slot lease

Two worker-runtime defects.

- A turn that ends `completed` now deletes its lease ref, as a `failed` turn does. `worker message` and `worker resume` of a `completed` worker push a new lease (`acquire_lease` with `new=True`), so a recount that refuses the resume deletes that lease again and the worker stays `completed`. An `idle` turn still keeps its lease. `sync_leases` already omits `completed` from `holding_slots`, so `worker sync` agrees.
- The wrapper puts `harness_pythonpath` back on its own `PYTHONPATH` (or removes it) after imports and before the turn. A spawn it then makes, including delivery of a queued message, records the delegating caller's value. The harness of that turn sees `/caller`, or no `PYTHONPATH`, and not the package-path prefix the wrapper was started with. The wrapper is still started with `-P`. `sys.path` is fixed at interpreter start, so the lazy import of `worker_ops` inside `deliver_queued_message` still resolves this package. No explicit `harness_pythonpath` parameter was added: it would have to cross `worker_ops.py`, which is outside the zones.

The idle row is already `test_the_lease_follows_the_record`: a turn with no READY stays `idle` and its lease ref is still on the remote. It was not duplicated.

Touch zones, confirmed and unchanged: `specy_road/worker_runner.py`, `specy_road/worker_ops_message.py`, `specy_road/worker_lease.py`, `tests/test_worker_max_workers_global.py`, `tests/test_worker_queue_message.py`, `docs/orchestration-workers.md`, `CHANGELOG.md`. `worker_ops.py` re-exports message and resume and was not edited. `orchestration_role_env.harness_env` already restores the payload value for the harness and was not edited.

Verifiers: `python -m pytest -n 4 tests/test_worker_max_workers_global.py -q --tb=line` and `python -m pytest -n 4 tests/test_worker_queue_message.py -q --tb=line`. Both passed (49 tests together) before this summary; `ready` re-runs each file.

## Added

### Helpers

- `_completed_worker` (test): one READY turn against a bare remote, shared by the other-clone, resume and refused-resume rows.
- `_COMPLETE` (test): fake harness that writes a fresh READY, and waits on `work/hold-turn` when that file exists.
- `_QUEUED_PATH` (test): fake harness that records `PYTHONPATH` each turn and holds the first turn until released.

### Branches or guards

- `_exit_state` releases the lease when the state is `completed` as well as `failed`. `idle` does not.
- `worker message` / `resume` call `acquire_lease` with `new=True` when the worker is `completed` as well as `failed`.
- `main` sets `PYTHONPATH` from `harness_pythonpath`, or removes it, before `run`.

### Mocks

- none

### Tests

- `test_a_completed_turn_releases_its_lease`: the lease ref is present while the READY turn is held, and gone once it ends `completed`.
- `test_another_clone_is_not_held_by_a_completed_worker`: clone B at `max_workers` 1 can `delegate` when clone A's only worker has completed.
- `test_a_resumed_completed_worker_leases_only_while_its_turn_runs`: `worker message` pushes a lease for the held turn and drops it when that turn ends `completed`.
- `test_a_refused_resume_of_a_completed_worker_leaves_no_lease`: resume is refused, the worker stays `completed`, and only the other clone's lease ref remains.
- `test_a_queued_turn_gets_the_callers_pythonpath`: parametrized. The second turn sees `PYTHONPATH=/caller`, and with no caller value it sees none.
