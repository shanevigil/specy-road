## specy-road

Written by specy-road {{SPECYRD_VERSION}} (minimum {{SPECYRD_VERSION}}); `specy-road upgrade` rewrites only this section. The rest is the project's own.

**Read `.specyrd/AGENTS.md` before any roadmap, registry or git work:** it holds specy-road's full rules (load order, task loop, review, lean changes). Then read `.specyrd/AGENTS.team.md` (this repository's additions) and `.specyrd/AGENTS.local.md` (yours, gitignored) when present; they add to the rules, never relax the floor below.
<!-- prevents: an agent working from this stub alone, or reading the addenda as permission to relax the toolkit's rules | enforced: advisory; validate warns when this stub or .specyrd/AGENTS.md is missing or stale | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md, 2026-11-04 -->

The rules below repeat the floor of `.specyrd/AGENTS.md` on purpose, so an agent that reads only this file (Codex) still has it; `"agents_block": "minimal"` in `.specyrd/manifest.json` drops them.
The rules below hold even if you read nothing else:

- **Floor:** specy-road's rules on the registry, branches, review and a shared working tree are a floor; project rules may add to them, never relax them. On a conflict, stop and ask a human.
<!-- prevents: a project rule or addendum quietly relaxing the toolkit's rules, or an agent picking a side on a conflict | enforced: advisory | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md decision 4 -->
- **Shared checkout:** other agents may be working here. Before any git write run `git status` and `git worktree list`, treat files you did not create as someone else's, and work in your own worktree.
<!-- prevents: one session's commit or cleanup landing on another session's uncommitted work | enforced: session check exits 1 when staged paths overlap another live session's (bundled_scripts/session_cli.py) | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md, what happened -->
- **Git writes:** commit only with `git commit --only <paths>`; never stash, hard-reset, discard changes (`git restore`, `git checkout -- <path>`), clean, rebase, amend or switch branches in a tree another session may be using. The opt-in tool-call guard refuses all of these, and `git add -A`/`commit -a`, while another session is live.
<!-- prevents: a stash, reset, discard, branch switch or git add -A destroying or capturing another session's work, which no later step can undo | enforced: session guard denies these while another session is live, once the opt-in harness hooks are installed (specy_road/tool_call_guard.py) | ref: docs/orchestration.md, Presence; tests/test_tool_call_guard.py -->
- **Claims:** `specy-road do-next-available-task` registers the claim on the integration branch, then creates `feature/rm-<codename>`; take roadmap work only that way, and never hand-edit `roadmap/registry.yaml`.
<!-- prevents: two agents implementing one leaf because a claim was hand-written or never reached the remote | enforced: pickup syncs, registers and pushes by default | ref: docs/git-workflow.md, tests/test_do_next_task_pickup.py -->
- **Abort:** never run `specy-road abort-task-pickup` as cleanup after `finish-this-task`: it deletes the branch, which under `on_complete: pr` is the only place the finished work exists.
<!-- prevents: finished work lost when abort deletes the only branch that holds it | enforced: finish-this-task warns that abort would delete the branch | ref: CHANGELOG v0.2.3-rc2, finish spells out what on_complete pr leaves behind -->
- **Review:** never review or approve your own leaf, and never run `mark-implementation-reviewed --yes` on your own work.
<!-- prevents: work merged with no independent review | enforced: mark-implementation-reviewed --yes refuses without recorded reviews that meet the policy (specy_road/review_gate.py) | ref: docs/orchestration.md, tests/test_mark_implementation_reviewed_gate.py -->
- **Generated files:** never hand-edit `roadmap.md` or `roadmap-context.md`; edit the graph under `roadmap/`, then run `specy-road export` and `specy-road digest`.
<!-- prevents: hand edits to generated files that the next export or digest silently overwrites, or that drift from the graph | enforced: export --check and digest --check drift gates | ref: docs/roadmap-authoring.md -->
