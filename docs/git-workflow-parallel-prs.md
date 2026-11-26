# Parallel PR-mode leaves: `reconcile-branch`

Under `on_complete: pr` (see [git-workflow.md](git-workflow.md)), several leaves
can have open PRs/MRs against the same integration branch at once. Each finish
commit removes its own row from `roadmap/registry.yaml` and renders
`roadmap.md` and `roadmap-context.md` again, so once the first PR merges, every
other open PR conflicts on those three files, even when no code is shared.
Finish resolves them when it opens the PR; nothing resolves them after another
leaf merges, and hand-editing generated files costs a CI cycle per PR.

## When to run it

Run it when a PR-mode branch's PR shows conflicts on `roadmap/registry.yaml`,
`roadmap.md` or `roadmap-context.md` after another leaf's PR merged:

```bash
cd "$(git rev-parse --show-toplevel)"   # in the leaf's worktree, on feature/rm-<codename>
specy-road reconcile-branch [NODE_ID]   # optional: --base BRANCH --remote NAME
```

It fetches the integration branch and merges it into the feature branch with
the same rule finish uses: the registry is the integration branch's registry,
minus this leaf's row once the leaf has finished (a branch that still holds its
claim keeps the row; a row the integration ref lacks is copied from this branch),
and the two generated files are rendered again from the
merged graph. It commits the merge and pushes the branch when it has an
upstream, so the PR updates and merges cleanly. With `NODE_ID`, it refuses
unless `HEAD` is that leaf's branch.

A conflict on any other path is not bookkeeping: the merge is aborted, the
paths are named, the branch is left where it was and the command exits 1.
Merge the integration branch by hand, resolve, have the result reviewed, then
push.

## Why a command, not a merge driver

A `.gitattributes` merge driver would only help local merges: forge merges
(GitHub, GitLab and the like) never run custom git merge drivers, so the PR
would still show the conflict. A driver also sees one file at a time and
cannot render the generated files from the merged graph. Out of scope here: a
merge driver, and resolving code conflicts.

## Pickup keeps the digest current

Pickup's register commit on the integration branch carries the regenerated
`roadmap-context.md` (and `roadmap.md` when the claim changes it) with the
registry row, so `digest --check` passes on the integration branch and on the
new feature branch right after pickup. `abort-task-pickup` still recognises
that commit as the claim's own registration.
