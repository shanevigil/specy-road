# Parity harness

Proof that a change kept the user-visible surface: every later M16 leaf runs it unchanged.

```bash
pytest -m parity            # the harness alone
SPECY_ROAD_PARITY_REGEN=1 pytest -m parity        # rewrite every golden (a new baseline)
SPECY_ROAD_PARITY_REGEN=missing pytest -m parity  # write only goldens that do not exist yet
```

| Test file | What it pins | Goldens |
| --- | --- | --- |
| `test_command_surface.py` | Every `specy-road`/`specyrd` command and subcommand (from `cli.registered_agent_command_names()` and `--help` output): its subparser path, option strings and passthrough, compared both ways; and each one's `--help` transcript at `COLUMNS=100` | `golden/inventory.json`, `golden/help/` |
| `test_leaf_loop.py` | One leaf from `init project` to `finish-this-task`, `on_complete: merge` and `pr`, offline: exit code, registry rows, leaf status and git state after each step | `golden/leaf_loop/` |
| `test_generated_outputs.py` | `validate`, `export --check`, `digest --check` and the digest on the dogfood fixture; `upgrade --dry-run` on `fixtures/rc3_consumer/` (`init project --profiles none` from v0.3.1-rc3) | `golden/dogfood/`, `golden/upgrade/` |

Paths, the install prefix and the running version (whole tokens only) are normalised. Help
transcripts are compared byte for byte, except that a paragraph holding a toolkit docs URL has its
whitespace collapsed: the URL carries the version's tag, so a version bump reflows it. Digest
sections derived from git history are left out.

The command surface changes only through rows of `command_map.yaml` (old invocation, new
invocation, allowed difference). Each row is applied to the golden inventory as a declared delta
(the rule is in `command_map.py`): an `old` with options may lose those options, an `old` without
may be gone, a `new` with options may gain them, a `new` not in the golden is added. Every other
difference still fails. The names a row covers may have a changed transcript, but every current
name needs a golden transcript: after a row adds a command, run `SPECY_ROAD_PARITY_REGEN=missing`.
A parent whose help lists a changed subcommand needs its own row.
