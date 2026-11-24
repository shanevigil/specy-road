# Codex rollout fixture

`rollout-*.jsonl` is a `codex exec --json` run's rollout as codex-cli 0.166.0 wrote it under `CODEX_HOME/sessions/`,
cut to its `session_meta`, `turn_context` and `task_complete` rows, with ids, account fields and paths replaced. The
run's `--json` stream named no model (only `thread.started`'s `thread_id`); the rollout's `turn_context.model` does.
