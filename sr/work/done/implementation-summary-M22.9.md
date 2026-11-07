# Implementation summary: M22.9 — Local roster entries need allow_local_cli for preflight, cli_resume and harness_bin; a Codex reviewer runs memory-off in its own CODEX_HOME

Branch `feature/rm-local-roster-and-codex-reviewer-isolation`. Base `cdd7b9e7`.

## What changed

- `specy_road/roster_local.py`: a local `roster_add` entry with a non-empty `preflight`, `channels.cli_resume` or `harness_bin`, or with `cursor_force: true`, is refused unless the same file sets `allow_local_cli: true`. The message is the `channels.cli` sentence, with that field's name. `channels.cli` and a profile `access.cli` are unchanged. Committed roster entries are not read here.
- `specy_road/worker_adapter_codex.py`: `Codex.reviewer_launch` passes `CODEX_MEMORY_OFF` on a fresh turn and on resume, keeps `-m` on resume, and sets `CODEX_HOME` to `profile_home(model)` on a fresh turn and to `session_home(id)` (else `profile_home(model)`) on resume. Worker launch and resume already did this.
- `specy_road/review_record_write.py`: `delegate_turn` merges `launch.env` into the harness env before `reviewer_env`, as `run_logged` already does for `prompt --channel cli --run`. A delegated Codex review therefore gets the isolated home. Claude and Cursor reviewer launches are unchanged.
- `tests/test_roster_worktree_dry_run.py`: the existing `channels.cli` / profile `access.cli` opt-in case is unchanged. A new test parametrizes the four fields over `allow_local_cli` absent, false and true.
- `tests/test_harness_launch.py`: a Codex reviewer test pins both argv shapes and `CODEX_HOME`, including the session home when a rollout exists.
- `tests/test_review_record_write.py`: the exact Codex reviewer argv test expects the memory-off switches and the isolated home. The fake-codex `review delegate` case records the `CODEX_HOME` and the memory-off argv the binary saw, with the caller's own `CODEX_HOME` set so a missed merge fails the test.
- `docs/orchestration-roster.md`: the local-roster paragraph lists every field that needs `allow_local_cli`.
- `docs/orchestration-reviewer-output.md`: the Codex reviewer row names memories-off and the isolated home (the session's home on resume).
- `CHANGELOG.md`: two `[Unreleased]` / `### Fixed` bullets.

`tests/review_delegate_helpers.py` (`FAKE_CODEX`) stays outside the zones. The delegate test rewrites the script it installs so that one case records `CODEX_HOME`; other callers of `FAKE_CODEX` still receive an argv list.

## Acceptance

- **A1:** `merge_local_roster` refuses those four fields without `allow_local_cli: true`, naming the field, and merges them when the flag is true. The parametrized test asserts the marker file the preflight or `cli_resume` would create is absent, so the refusal happens before any command runs. The existing positive opt-in case still merges `channels.cli` and a profile `access.cli`.
- **A2:** Fresh and resumed reviewer argv include the three memory-off `-c` pairs, and resume still includes `-m`. `CODEX_HOME` is the profile home, or the session home when `session_home` finds the thread. `delegate_turn` passes that env through; the fake-codex case records it. `run_logged` already merged `launch.env` and was left as it was.
- **A3:** Both docs name the fields and the Codex isolation. Changelog Fixed entries are under `[Unreleased]`.
- **A4:** Informational. Package about +34 lines (`roster_local.py` +21, `worker_adapter_codex.py` +10, `review_record_write.py` +3), tests about +71, docs and changelog about +7. Not a gate.

## Final touch zones

`specy_road/roster_local.py`, `specy_road/worker_adapter_codex.py`, `specy_road/review_record_write.py`, `tests/test_roster_worktree_dry_run.py`, `tests/test_harness_launch.py`, `tests/test_review_record_write.py`, `docs/orchestration-roster.md`, `docs/orchestration-reviewer-output.md`, `CHANGELOG.md`. No zone added or removed.

## Verification

- `pytest -n 4 tests/test_roster_worktree_dry_run.py tests/test_harness_launch.py tests/test_review_record_write.py`: 88 passed.
- `specy-road file-limits`: OK. The warnings it prints are on files this leaf did not touch.
- `ruff check` on the six edited Python files: passed.

## Added

- Helper: `_local_command_field` in `specy_road/roster_local.py`. It returns the one field name (`channels.cli`, `preflight`, `channels.cli_resume`, `harness_bin`, or `cursor_force`) so every refusal uses the `channels.cli` message (A1). `cursor_force` is returned only when the value is true, because false is the default and must not need the opt-in.
- Branch: `Codex.reviewer_launch` on resume sets `CODEX_HOME` from `session_home(id)` when that rollout exists, otherwise from `profile_home(model)` (A2). A fresh turn always uses `profile_home(model)`.
- Test: `tests/test_roster_worktree_dry_run.py::test_roster_add_command_fields_need_allow_local_cli`, parametrized over the four fields and `allow_local_cli` absent, false and true. Absent and false must refuse by name before the command runs; true must merge the entry (A1, S-RC10). The existing `test_roster_add_cli_needs_allow_local_cli` positive opt-in case stays.
- Test: `tests/test_harness_launch.py::test_codex_reviewer_runs_memory_off_in_an_isolated_home`. It pins the fresh and resumed argv, the profile `CODEX_HOME`, and the session home once a rollout exists (A2).
- Mock: none. The fake-codex script installed by `test_a_codex_review_delegate_files_the_verdict_from_its_output_file` now also writes the `CODEX_HOME` it saw, so the delegate path is checked through the binary (A2). The test file does not import or patch a `_`-prefixed name.
- Guards: none.
