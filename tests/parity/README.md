# Parity harness

Proof that a change kept the user-visible surface: every later M16 leaf runs it unchanged.

```bash
pytest -m parity            # the harness alone
SPECY_ROAD_PARITY_REGEN=1 pytest -m parity        # rewrite every golden (a new baseline)
SPECY_ROAD_PARITY_REGEN=missing pytest -m parity  # write only goldens that do not exist yet
```

| Test file | What it pins | Goldens |
| --- | --- | --- |
| `test_command_surface.py` | Every `specy-road`/`specyrd` command and subcommand (from `cli.registered_agent_command_names()` and each command's parsers, `cli.command_parsers()`, which its module's `build_parser()` returns): its subparser path, option strings and passthrough, compared both ways; and each one's `--help` transcript at `COLUMNS=100` | `golden/inventory.json`, `golden/help/` |
| `test_option_table.py` | `--json`, `--ref`, `--model`, `--base` and `--remote` on every parser: action, type, choices, required flag, default, destination, nargs and metavar, recorded before `specy_road/cli_args.py` declared them once; and that nothing else declares them | `golden/option_table.json` |
| `test_leaf_loop.py` | One leaf from `init project` to `finish-this-task`, `on_complete: merge` and `pr`, offline: exit code, registry rows, leaf status and git state after each step | `golden/leaf_loop/` |
| `test_generated_outputs.py` | `validate`, `export --check`, `digest --check` and the digest on the dogfood fixture; `upgrade --dry-run` on `fixtures/rc3_consumer/` (`init project --profiles none` from v0.3.1-rc3), and that its one report holds the same lines as `rc3-dry-run-before.txt`, recorded before the report was regrouped, plus only the lines its `ALLOWED_ADDED` list names, each with the bundled file M16.4.2 changed that causes it | `golden/dogfood/`, `golden/upgrade/` |
| `test_refresh_map.py` | Each flag and mode of `refresh-stubs`, `refresh-schemas` and `refresh-profiles` against its `upgrade --only` form on a copy of the rc3 fixture: exit code, stdout and every file under the repo; stderr differs only by the alias's deprecation line and the version-skew warnings | none |
| `test_review_map.py` | `review status` against each `handoff status` and `review list` invocation (no node, one node, `--json`, `--ref`) on a leaf in each review state: every stdout line the old command printed, `handoff status`'s exit, and its JSON payload kept with `review list`'s as `records`; `review packet` and `decisions add\|list --kind lesson` against `review-packet` and `lessons add\|list` on copies of one leaf: exit code, stdout and every file. Each old form adds only its deprecation line on stderr | none |
| `orchestration_state/test_state_rows.py` | The orchestration state table (`orchestration_state/rows.py`): one fixture repo per row (a fresh manual claim, a live worker, a worker that exited clean or failed, an abandoned claim, a review record and no worker, a chore worker, one leaf with two worktrees, an unreadable worker record, a person's live session): `worker list --all` (text and `--json`), `orchestrate plan --json`, `doctor`, and cleanup eligibility (orphaned workers, slot holders, the claims M15.26 reports), recorded before the readers switched to the snapshot; `python -m tests.parity.orchestration_state.replay <REF>` runs that test on `<REF>`'s package against the committed goldens. `test_snapshot.py`: each row's snapshot against the v1 fixture | `orchestration_state/golden/` |
| `workers/test_worker_rows.py` | The worker table (`workers/rows.py`): one fixture repo per row, driven through `specy-road worker` (delegate, sync, message, handoff, reclaim, terminate, reconcile, slot counting under `max_workers`, a dead or closed worker's lease released by `sync`, an op a crash left pending and a replayed op, and the prompt-submit hook of each harness): each step's exit and output, then every file under `work/.workers/` (records, event logs, interventions, ops) and the lease refs, with volatile fields masked; recorded before the worker modules were folded, from modules that exist on both sides of that fold | `workers/golden/` |
| `process/test_process_corpus.py` | The process corpus (`process/corpus.py`): commands run one after the other from two repo roots, `--repo-root` before and after the command name, a shared parser, the four forwarded commands and the guard, `doctor --fix` with a registry row to prune (and with that prune refused), `mark-implementation-reviewed M2 --yes` with its nested validate, export and digest, usage errors, `--version` and `prompt --channel cli`'s `would run` lines: exit code, stdout and stderr of each step, unbuffered, with commit ids, timestamps and file sizes normalised | `process/golden/` |

Paths, the install prefix and the running version (whole tokens only) are normalised. Help
transcripts are compared byte for byte, except that a paragraph holding a toolkit docs URL has its
whitespace collapsed (the URL carries the version's tag, so a version bump reflows it), and the
entries of the options `cli_args` declares are compared by invocation only: their help strings may
change, their names and metavars may not. Digest
sections derived from git history are left out.

The command surface changes only through rows of `command_map.yaml` (old invocation, new
invocation, allowed difference). Each row is applied to the golden inventory as a declared delta
(the rule is in `command_map.py`): an `old` with options may lose those options, an `old` without
may be gone, a `new` with options may gain them, a `new` not in the golden is added. Every other
difference still fails. The names a row covers may have a changed transcript, but every current
name needs a golden transcript: after a row adds a command, run `SPECY_ROAD_PARITY_REGEN=missing`.
A parent whose help lists a changed subcommand needs its own row.
