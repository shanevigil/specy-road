# Implementation summary: M16.1.1 parity harness

All of the work is in `tests/parity/` (the touch zone, which turned out to be correct). No package
code changed, and no private `specy_road` name is imported or patched. Every test module sets
`pytestmark = pytest.mark.parity`, and `tests/parity/conftest.py` registers the marker, so
`pytest -m parity` runs the harness on its own (160 items, about 40 s with `-n 4`).
`SPECY_ROAD_PARITY_REGEN=1` rewrites every golden from today's behaviour (documented in
`tests/parity/README.md`).

## Acceptance

- **A1:** `help_surface.crawl()` gets the top-level names from
  `cli.registered_agent_command_names()` (both `specy-road` and `specyrd`, aliases included). It
  then runs `--help` for each name and follows subcommands down. It finds them from argparse's
  `{a,b}` choices, or from plain words after the path in a usage line. That second source catches
  `orchestration`, whose bare `--help` exits 2 and prints only `usage: specy-road orchestration guard …`.
  For each of the 147 paths, `golden/inventory.json` records the subparser path, the sorted option
  strings, the subcommands, and whether the command passes the remaining arguments through (a bare
  `...` from `argparse.REMAINDER`, or a bare `--` in usage; none do today).
  `test_inventory_matches_golden_both_ways` compares the inventory with the golden in both
  directions. It skips any command or subcommand named in a `command_map.yaml` row (the command
  words of the row's `old` or `new` invocation, with its subcommands), and every other difference
  is listed with its name, e.g. `specy-road history: options lost ['--json'], gained []`.
- **A2:** `golden/help/<prog>__<cmd>__<sub>.txt` holds one transcript (exit code, stdout, stderr)
  for each of the 147 paths. `command_map.yaml` exists with `rows: []` and a header that names the
  row fields (`old`, `new`, `allowed`). `test_help_transcript_matches_golden[<name>]` fails when a
  transcript differs from its golden, unless that name is a row.
- **A3:** `test_leaf_loop_matches_golden[merge|pr]` runs these steps in a temp repo:
  `init project`, a two-reviewer roster with `count_human_filed_reviews: true`, `on_complete` set,
  push to a local bare origin, `add-node`, `scaffold-planning`, the sheet written and landed,
  `do-next-available-task --under M1.2`, the implementation committed, `ready`, two
  `review record --human-filed`, `mark-implementation-reviewed --yes` (the gate check), and
  `finish-this-task`. After each CLI step the test asserts the exit code and records a snapshot:
  - registry rows (checkout and `main`)
  - the leaf's status (checkout and `main`)
  - git state: current branch, local and origin branches, whether the feature tip is in `main` and
    in `origin/main`, the HEAD subject, and `git status --porcelain`

  The snapshots are compared with `golden/leaf_loop/<mode>.json`.
  - **merge run:** also asserts the end state directly: exit 0, Complete on both sides, no
    registry rows, feature merged into `main` and `origin/main`.
  - **pr run:** its end state was recorded from today's behaviour and runs offline to the end.
    `finish` exits 0. The bookkeeping commit on the feature branch has the leaf Complete and its
    row removed. `main` still has the row (`pending`) and `Not Started`. Nothing is pushed.

  Neither run makes a network call. `gh` and `glab` on PATH are stubs that log any call (the test
  asserts the log does not exist), and `GIT_ALLOW_PROTOCOL=file` is set.
  `test_leaf_loop_gate_refuses_one_review_short` shows the loop really goes through the gate: with
  one review missing, `mark-implementation-reviewed --yes` exits 1 and the row stays `pending`.
- **A4:**
  - **rc3 fixture:** `tests/parity/fixtures/rc3_consumer/` (38 files, 256K) is what
    `init project --profiles none` wrote when run from `git archive v0.3.1-rc3`.
  - **What the tests run:** the dogfood fixture and the rc3 fixture are each copied into their own
    temp git repo, so the output does not depend on the toolkit checkout. On the dogfood copy:
    `validate`, `export --check`, `digest --check` and `digest -o -`. On the rc3 copy:
    `upgrade --dry-run`, with PATH holding only git's directory so the install listing is the same
    on every machine.
  - **Normalisation:** temp roots, `<REPO>`, `<PREFIX>`, `<HOME>`, the running version and the
    docs tag are replaced with placeholders. No output contains a timestamp.
  - **Digest:** the golden leaves out the history-derived sections ("Dependencies that were
    removed", "Quality by area"); a small test checks the stripper.
  - **No writes:** the upgrade test also asserts that the dry run leaves the copy clean.
- **A5:** the harness is green on HEAD, and the full suite is too (6700 passed, 8 skipped, `-n 6`).
  It adds no package code.
- **A6 (informational):** package 0. The harness code, README and map are about 775 lines. The
  goldens and the rc3 fixture are data (about 9,000 lines).

## Choices a reviewer should check

- **Whitespace in transcript comparison.** Help transcripts are compared with whitespace runs
  collapsed (`support.words`). The docs URLs in help text carry the version's tag (`v0.3.1-rc2`),
  so a version bump changes their length and argparse reflows the paragraph. Without collapsing,
  every bump would need map rows. Any changed word, option or exit code still fails.
- **Clean environment for every CLI run.** `cli_env()` removes `SPECY_ROAD_*`, `CLAUDE*`, `CODEX_*`
  and `CURSOR_*` and sets `COLUMNS=100`. A worker's own session (`SPECY_ROAD_REPO_ROOT`,
  `SPECY_ROAD_ORCHESTRATION_ROLE`) would otherwise steer the commands.
- **Inventory paths include the roots.** The inventory also has `specy-road` and `specyrd` keys,
  so the top-level `--help` text is pinned too.

## Checks run (the "Done but wrong" list), in a scratch copy of the tree

- **Option removed from a forwarded command:** removing `history --json` failed the inventory test
  with `specy-road history: options lost ['--json'], gained []`. Adding a row
  `{old: "specy-road history --json", new: "specy-road history"}` made it pass.
- **Help text changed:** editing one option's help text failed
  `test_help_transcript_matches_golden[specy-road history]`.
- **Alias removed:** removing the `remove-node` alias failed with
  `specy-road remove-node: in the golden inventory, gone from the CLI`.
- **Review missing:** with one of the two reviews left out, the gate check fails (kept as a test).

A note for whoever runs the full suite: with `COLUMNS=100` exported in the shell,
`tests/test_worker_m310_reconcile_status.py::test_finish_help_and_merge_notice` fails, because it
reads wrapped help text. This leaf does not touch that test or the code it reads, and without the
variable it passes.

## Touch zones

Final list: `tests/parity/`. Nothing outside it was changed.

## Added

- `tests/parity/__init__.py`: makes `tests.parity` importable for the shared helpers.
- `tests/parity/conftest.py` (`pytest_configure`): registers the `parity` marker.
- `tests/parity/support.py`:
  - `cli_env`: a clean environment for each CLI run (no harness or session variables, `COLUMNS=100`).
  - `run_cli`: runs the CLI as a user would.
  - `normalise`: replaces paths, the version and the docs tag with placeholders.
  - `transcript`: one command's exit code and output, in golden form.
  - `words`: collapses whitespace so a version bump that reflows a URL is not a change.
  - `check_golden`: compares with a golden, or writes it under `SPECY_ROAD_PARITY_REGEN=1`.
  - `command_map_rows`: reads the rows of `command_map.yaml`.
  - `mapped`: decides whether a row covers a key.
- `tests/parity/help_surface.py`:
  - `crawl`: the command surface from the registered names and `--help` output.
  - `parse_help`: reads subcommands, option strings and passthrough from help text.
  - the usage-line subcommand branch: catches `orchestration`, whose `--help` only prints a usage
    line.
- `tests/parity/command_map.yaml`: empty rows list; the only way a later leaf may change a golden.
- `tests/parity/README.md`: the marker, the regeneration variable, what each file pins.
- `tests/parity/test_command_surface.py`:
  - `test_inventory_matches_golden_both_ways`: A1, the two-way comparison after map rows.
  - `test_inventory_starts_from_the_registered_names`: the top-level set equals
    `registered_agent_command_names()`.
  - `test_help_transcript_matches_golden`: A2, one per name.
  - `test_passthrough_is_read_from_usage`: checks that the passthrough field can tell REMAINDER
    from a `*` positional. No command uses REMAINDER today, so without this nothing would show the
    field works.
  - `inventory_differences`: names each difference.
- `tests/parity/test_leaf_loop.py`:
  - `test_leaf_loop_matches_golden[merge|pr]`: A3.
  - `test_leaf_loop_gate_refuses_one_review_short`: proves the loop goes through the gate.
  - the `gh`/`glab` logging stubs and `GIT_ALLOW_PROTOCOL=file`: prove the runs are offline.
  - `Loop.state`: snapshots the registry, status and git state after each step.
- `tests/parity/test_generated_outputs.py`:
  - `test_dogfood_command_matches_golden[validate|export-check|digest-check]`: A4.
  - `test_dogfood_digest_matches_golden`: A4.
  - `test_rc3_consumer_upgrade_dry_run_matches_golden`: A4.
  - `test_history_sections_are_left_out_of_the_digest_golden`: checks the history-section
    stripper, since the fixture copy has no history to strip.
  - `without_history_sections`: removes the history-derived digest sections.
- `tests/parity/golden/`: inventory, 147 help transcripts, two leaf-loop step lists, dogfood and
  upgrade outputs.
- `tests/parity/fixtures/rc3_consumer/`: the 0.3.1rc3-shaped consumer repo.
- Mocks: none (the `gh`/`glab` stubs are PATH executables that log calls; no Python mock).
