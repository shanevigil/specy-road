# Implementation summary: M21.11 — Help text names installed commands

## What changed

- `specy_road/cli_usage.py`: add-node → `see: specy-road add-node -h`; scaffold-planning →
  `see specy-road scaffold-planning -h`; gui line → `(after: specy-road init gui --install-gui,
  or pip install 'specy-road[gui-next]')`. No command or flag removed (A1).
- `specy_road/cli.py`:
  - `main` prints `link_toolkit_docs(USAGE_TEXT)`, so `docs/orchestration-workers.md` and
    `docs/orchestration-chores.md` become versioned URLs (A3).
  - `_run` starts the child with `python -c "<runpy bootstrap>" <prog> <args...>`: the bootstrap
    sets `sys.argv[0] = prog`, drops it from argv, and `runpy.run_module(module,
    run_name='__main__')` (default `alter_sys=False`, so argv[0] stays). `prog` defaults to
    `specy-road` (CRUD / archive / forwarded commands, whose subparsers add the command name);
    `_SCRIPTS` pass `specy-road <cmd>`. Exit-code handling unchanged. Scripts with an explicit
    `prog=` are unaffected (argparse ignores argv[0] then) (A2).
- `bundled_scripts/roadmap_crud_argparse.py` (`apply` description) and
  `bundled_scripts/do_next_task_args.py` (`--on-complete` help): wrapped in `link_toolkit_docs` (A3).
- `tests/test_cli_help_text.py`: new (A4).
- `CHANGELOG.md`: `[Unreleased]` Fixed entry (A4).

Touch zones: confirmed accurate; no file outside them changed. No file-limits impact
(`specy-road file-limits` OK).

## Verification

- `pytest tests/test_cli_help_text.py -n 4`: 70 passed.
- Red without the fix (package changes reverted, test kept): 32 failed, 38 passed.
- `pytest tests/test_cli_*.py` (+ cli.py importers' tests): 213 passed.
- Full suite `pytest -n 4`: 5083 passed (the `_run` change touches every bundled command).
- `specy-road add-node -h | head -1` → `usage: specy-road add-node ...`.

## Added

- `_run(..., prog=...)` parameter and runpy bootstrap in `cli.py`: sets argparse's program name once for every bundled entrypoint (A2).
- `link_toolkit_docs` call in `cli.main`, `roadmap_crud_argparse._p_apply`, `do_next_task_args` `--on-complete`: bare docs/*.md → published URL (A3).
- `tests/test_cli_help_text.py::test_help_names_installed_commands` (parametrized over `--help` and every public registered command `-h`, orchestration as `orchestration guard -h`): exit 0, usage starts `usage: specy-road`, no `bundled_scripts/`, no usage/python line naming a `.py`, no bare unshipped docs/*.md (A4).
- `tests/test_cli_help_text.py::test_top_level_help_names_canonical_commands`: canonical gui / `<cmd> -h` lines present, `specy-road init --install-gui` absent (A4).
- Mocks: none. Guards: none.
