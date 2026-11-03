# Orchestration guard hooks (specy-road M8.5)

Checked-in snippets `specyrd init --install-orchestration-hooks` merges into your harness config.

| Harness | File | Role env in hook command |
|---|---|---|
| Claude Code | `.claude/settings.json` | `SPECY_ROAD_ORCHESTRATION_ROLE=executor` or `reviewer` |
| Codex | `.codex/hooks.json` | same |
| Cursor | `.cursor/hooks.json` | same |

**Denials**

- **Reviewer:** `git commit`, `git push`, `gh pr`
- **Executor:** `git push`, `gh pr`, harness worktree and cloud commands

Print a snippet without installing:

```bash
specy-road orchestration guard --format claude-code --print-config --config-role executor
```

**Codex trust:** project hooks load only when `.codex/` is trusted. In a fresh linked worktree, trust the layer or run hooks once with `--dangerously-bypass-hook-trust` (specy-road hook files only).

**Claude blocking:** exit **2** blocks; exit 1 does not. Hooks set `"onFailure": "block"` so timeout or crash fails closed.

Pair with the shared-checkout guard (`specy-road session guard --print-config`) for stash, reset and branch switches.

**Pre-push:** optional `specyrd init --install-pre-push-hook` installs `.git/hooks/pre-push` from `pre-push` in this directory.
