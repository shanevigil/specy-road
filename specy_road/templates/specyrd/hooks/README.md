# Orchestration guard hooks (specy-road M8.5)

Checked-in snippets `specyrd init --install-orchestration-hooks` merges into your harness config. Each harness file gets **one** hook. The command is `specy-road orchestration guard --format …`; the role comes from `$SPECY_ROAD_ORCHESTRATION_ROLE` in the worker environment (`executor` or `reviewer`). `worker delegate` exports `executor`; `review delegate` exports `reviewer`. Do not merge executor and reviewer snippets into the same settings/hooks.json.

| Harness | File |
|---|---|
| Claude Code | `.claude/settings.json` |
| Codex | `.codex/hooks.json` |
| Cursor | `.cursor/hooks.json` |

**Denials** (selected by `$SPECY_ROAD_ORCHESTRATION_ROLE`)

- **Reviewer:** `git commit`, `git push`, `gh pr`
- **Executor:** `git push`, `gh pr`, harness worktree and cloud commands

Print a single-role snippet (pins `SPECY_ROAD_ORCHESTRATION_ROLE` in the command) without installing:

```bash
specy-road orchestration guard --format claude-code --print-config --config-role executor
```

**Codex trust:** project hooks load only when `.codex/` is trusted. In a fresh linked worktree, trust the layer or run hooks once with `--dangerously-bypass-hook-trust` (specy-road hook files only).

**Claude blocking:** exit **2** blocks; exit 1 does not. Hooks set `"onFailure": "block"` so timeout or crash fails closed.

Pair with the shared-checkout guard (`specy-road session guard --print-config`) for stash, reset and branch switches.

**Pre-push:** optional `specyrd init --install-pre-push-hook` installs `.git/hooks/pre-push` from `pre-push` in this directory.
