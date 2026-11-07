# Parity harness

Proof that a change kept the user-visible surface: every later M16 leaf runs it unchanged.

```bash
pytest -m parity            # the harness alone
SPECY_ROAD_PARITY_REGEN=1 pytest -m parity   # rewrite every golden from today's behaviour
```

| Test file | What it pins | Goldens |
| --- | --- | --- |
| `test_command_surface.py` | Every `specy-road`/`specyrd` command and subcommand (from `cli.registered_agent_command_names()` and `--help` output): its subparser path, option strings and passthrough, compared both ways; and each one's `--help` transcript at `COLUMNS=100` | `golden/inventory.json`, `golden/help/` |
| `test_leaf_loop.py` | One leaf from `init project` to `finish-this-task`, `on_complete: merge` and `pr`, offline: exit code, registry rows, leaf status and git state after each step | `golden/leaf_loop/` |
| `test_generated_outputs.py` | `validate`, `export --check`, `digest --check` and the digest on the dogfood fixture; `upgrade --dry-run` on `fixtures/rc3_consumer/` (`init project --profiles none` from v0.3.1-rc3) | `golden/dogfood/`, `golden/upgrade/` |

Paths, the install prefix and the running version are normalised. Help transcripts are compared
with whitespace runs collapsed, so a version bump that reflows a docs URL is not a change. Digest
sections derived from git history are left out.

A golden changes only through a row of `command_map.yaml` (old invocation, new invocation, allowed
difference): the inventory and transcript checks skip that command and its subcommands. Regenerate
the goldens in the same change and say which rows explain the diff.
