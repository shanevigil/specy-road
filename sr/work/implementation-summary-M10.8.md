# Implementation summary: M10.8 — Reviewers launch without repo hooks or MCP

## What changed

- **A1** — `specy_road/schemas/review-record.schema.json` gains an optional
  `launch_mode` (`full` | `bare` | `explicit`). `specy_road/review_files.py`
  exports `REVIEW_LAUNCH_MODES` with the same three values. `review record`
  (`specy_road/bundled_scripts/review_cli.py`) takes `--launch-mode` (argparse
  choices from that tuple) and writes it into the record's front matter before
  signing, so a signature covers it. `handoff status` shows it on each review
  line (`…, launch mode bare`) and in `--json` as each review's `launch_mode`,
  for counted reviews and for the unclaimed listing alike. When the flag is
  given it wins over a `launch_mode` already in the notes file.
- **A2** — `ClaudeCode.reviewer_launch` (`specy_road/worker_adapters.py`)
  builds `claude -p <instruction> --bare --model <api_id> [--effort <lvl>]
  --permission-mode acceptEdits --allowedTools Read,Edit,Bash --add-dir
  <work/reviews/NODE_ID>`, with the prompt on stdin. The instruction comes
  right after `-p` because `--add-dir` is variadic. `prompt --role reviewer
  --channel cli` (`role_prompt.run_cli_channel` → `run_bare_reviewer`) uses it
  for a roster entry with `harness: claude-code` and no `channels.cli`, and
  prints a note that bare mode needs `ANTHROPIC_API_KEY` (or an
  `apiKeyHelper`). Hooks and MCP servers are off because of `--bare`; the
  command adds nothing that would turn them back on. A `channels.cli`, other
  harnesses, and the other roles behave as before. The effort level is now
  computed before the branch; that order does not change it.
- **A3** — The reviewer prompt (`LAUNCH_MODE_LINES` in `role_prompt.py`,
  appended after `reviewer_preamble`) tells the reviewer to add
  `--launch-mode full|bare|explicit` to its `review record` command and
  explains each value. `sr/tools/claude-review.sh` now passes `--bare`, with a
  comment saying why and that it needs an API key.
- **A4** — `docs/orchestration-review.md` has a new **Reviewer launch mode**
  section: why a fresh-session reviewer runs without repository hooks or MCP
  (cites the headless docs), the built command, the API-key requirement, and
  the field's three values with a table, plus the fact that the gate ignores
  the field. Tests in `tests/test_review_files.py` cover A1, A2 and the A3
  prompt line.

## Touch zones (confirmed)

Changed: `specy_road/review_files.py`, `specy_road/bundled_scripts/review_cli.py`,
`specy_road/schemas/review-record.schema.json`, `specy_road/bundled_scripts/role_prompt.py`,
`specy_road/worker_adapters.py`, `docs/orchestration-review.md`, `sr/tools/claude-review.sh`,
`tests/test_review_files.py`.

Left unchanged: `tests/test_models_and_prompt.py` is at 399 of its 400-line
cap, so the A2/A3 prompt tests are in `tests/test_review_files.py` and import
that module's helpers (`make_profile_repo`, `commit_profile`, `run_main`).

Outside the touch zones and left alone:
- `docs/orchestration-workers.md` (roster setup). The planning sheet names it,
  but acceptance does not, and the touch zones leave it out. The new
  orchestration-review.md section covers the roster condition
  (`harness: claude-code`, no `channels.cli`).
- `specy_road/bundled_scripts/role_prompt_rca.py`, which holds
  `reviewer_preamble`. The launch-mode line is added from `role_prompt.py`
  instead.
- The `review-record.template.md` template. The field is optional and set by
  the flag.

`review_cli.py` was at its 400-line cap. I collapsed its 14-line
`review_files` import block into 4 lines so the flag fits without an
exemption. It is now 397 lines.

## Not done / notes

- The `rca` role still uses the profile's `access.cli`. Acceptance names only
  the reviewer.
- `launch_mode` is self-attested, like `fresh_session`, and the gate does not
  read it.

## Verification

- `python -m pytest tests/test_review_files.py tests/test_models_and_prompt.py -q`: 54 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: all checks passed.
- The 43 test files that import the changed modules, plus the baseline, file-limit and docs gate tests: 571 passed (12m11s).
- Full `pytest`: not completed. The serial suite ran past its 20-minute limit on this machine and was stopped; `pytest-xdist` is not installed.

## Added

- `REVIEW_LAUNCH_MODES` (review_files.py): one source for the three values `review record --launch-mode` accepts.
- `launch_mode` schema property (review-record.schema.json): lets a record carry the mode (A1).
- `--launch-mode` flag and the `if ns.launch_mode:` store before signing (review_cli.py): A1; set before signing so the signature covers it.
- `launch_mode` key in `handoff status` review dicts (counted and unclaimed) and the `mode` suffix in `_render` (review_cli.py): A1 "handoff status prints it per review".
- `ClaudeCode.reviewer_launch` (worker_adapters.py): builds the bare reviewer command (A2).
- `run_bare_reviewer` (role_prompt.py): runs that command with the prompt on stdin, prints the API-key note, and reports an `OSError` (no `claude` on PATH) as exit 1 instead of a traceback.
- Branch in `run_cli_channel` for reviewer + claude-code + no `channels.cli` (role_prompt.py): selects the bare command (A2). New kwargs `model` and `reviews` carry the roster id (used when there is no profile) and the hand-off dir.
- `api_id` "unknown"/empty → no `--model` guard (role_prompt.py): matches `worker_ops._cli_for`, where an unknown api_id means the harness default.
- `LAUNCH_MODE_LINES` (role_prompt.py): the reviewer-prompt instruction (A3).
- `--bare` in sr/tools/claude-review.sh: A3.
- Test `test_review_launch_mode_is_optional_and_one_of_three`: the schema accepts each mode and its absence, and rejects other values (A1).
- Test `test_review_record_stores_launch_mode_and_status_prints_it`: the CLI stores the flag, text and JSON status print it, and argparse rejects an unknown mode (A1).
- Test helpers `_claude_code_reviewer_repo` and `_fake_run`: a claude-code roster with a packet, and a stand-in for `role_prompt.subprocess` so nothing launches. They patch the module reference only, so git calls are unaffected.
- Test `test_claude_code_reviewer_without_channels_cli_runs_bare`: `--bare`, `--add-dir` for the reviews dir, model and effort, no settings/MCP flags, prompt on stdin, the API-key note (A2).
- Test `test_claude_code_reviewer_with_channels_cli_runs_it_as_written`: a `channels.cli` still wins and is not made bare (behaviour preserved).
- Test `test_reviewer_prompt_asks_for_launch_mode`: the reviewer prompt has the line and the executor prompt does not (A3).
