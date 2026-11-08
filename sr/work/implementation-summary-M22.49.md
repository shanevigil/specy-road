# M22.49 — A sandboxed Claude worker resumes after the executor account changes

A sandboxed claude-code turn copies `$CLAUDE_CONFIG_DIR/.claude.json` (or `~/.claude/.claude.json` when the variable is unset) into the worker's state again when that directory is not the one recorded for the copy. The record is `work/.workers/<id>.state/claude-config-dir`, a sibling of the mounted `.claude` tree, and holds the directory the copy was made from. The same recorded directory leaves the worker's copy as it is, including a copy the harness has rewritten. No record, which is every worker launched before this change, is treated as a change and the copy is replaced from the current directory's file. Replacement is a rename onto the worker's path, so the empty mode-0444 mount placeholder is replaced and the user's file is only read. Transcripts under the worker's `.claude/projects` are not touched. A config directory with no `.claude.json` still does not fail setup and does not invent a file. The home-root `~/.claude.json` seed is still copied once and is not selected by `CLAUDE_CONFIG_DIR`.

Touch zones, confirmed and unchanged: `specy_road/worker_sandbox.py`, `tests/test_worker_sandbox.py`, `CHANGELOG.md`, `docs/orchestration-workers.md`. `specy_road/worker_runner.py` already passes the harness environment into `prepare`, so it stays as it is.

`tests/test_worker_sandbox.py` passed (17 tests) through the existing bwrap fixture. This host mounts `/var/tmp` read-only, which makes that fixture skip, so the run put a tmpfs on `/var/tmp` first.

## Added

### Helpers

- `_refresh_claude_config`: records the resolved config directory beside the mounted `.claude` tree and recopies `.claude.json` when that record is missing or names another directory.
- `_install_seed`: copies a seeded file by rename onto the worker's path, so a mode-0444 placeholder can be replaced without writing the user's file.
- `_claude_account`: builds one config directory and its `.claude.json` for the sandbox test.
- `_config_turn`: runs one sandboxed turn through `worker_runner.run` whose harness parses the config copy and replaces it by rename.
- `CLAUDE_COPY`: the fake harness that test turn runs.

### Branches or guards

- `_harness_binds` sends only the `CLAUDE_CONFIG_DIR` / `.claude/.claude.json` seed through the refresh; every other seed is still copied once when the worker has no copy.
- `_refresh_claude_config` returns without writing when the current directory has no `.claude.json`.
- `_refresh_claude_config` returns without replacing the copy when the recorded directory is the current one and the worker already has a copy.

### Mocks

none

### Tests

- `test_a_sandboxed_claude_worker_refreshes_claude_json_when_the_config_directory_changes`: the same recorded directory keeps a harness rewrite; a different directory recopies, parametrized over a non-empty old copy and a zero-byte mode-0444 copy; no record recopies from the current file. The user's bytes and a transcript written before the switch stay.
