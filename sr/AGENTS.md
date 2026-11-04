# Agents — load order

<!-- >>> specy-road managed block — do not edit inside <<< -->
## specy-road

Written by specy-road 0.3.1rc2 (minimum 0.3.1rc2); `specy-road upgrade` rewrites only this section. The rest is the project's own.

**Read `.specyrd/AGENTS.md` before any roadmap, registry or git work:** it holds specy-road's full rules (load order, task loop, review, lean changes). Then read `.specyrd/AGENTS.team.md` (this repository's additions) and `.specyrd/AGENTS.local.md` (yours, gitignored) when present; they add to the rules, never relax the floor below.

The rules below hold even if you read nothing else:

- **Floor:** specy-road's rules on the registry, branches, review and a shared working tree are a floor; project rules may add to them, never relax them. On a conflict, stop and ask a human.
- **Shared checkout:** other agents may be working here. Before any git write run `git status` and `git worktree list`, treat files you did not create as someone else's, and work in your own worktree.
- **Git writes:** commit only with `git commit --only <paths>`; never stash, hard-reset, discard changes (`git restore`, `git checkout -- <path>`), clean, rebase, amend or switch branches in a tree another session may be using. The opt-in tool-call guard refuses all of these, and `git add -A`/`commit -a`, while another session is live.
- **Claims:** `specy-road do-next-available-task` registers the claim on the integration branch, then creates `feature/rm-<codename>`; take roadmap work only that way, and never hand-edit `roadmap/registry.yaml`.
- **Abort:** never run `specy-road abort-task-pickup` as cleanup after `finish-this-task`: it deletes the branch, which under `on_complete: pr` is the only place the finished work exists.
- **Review:** never review or approve your own leaf, and never run `mark-implementation-reviewed --yes` on your own work.
- **Generated files:** never hand-edit `roadmap.md` or `roadmap-context.md`; edit the graph under `roadmap/`, then run `specy-road export` and `specy-road digest`.
<!-- >>> end specy-road managed block <<< -->
