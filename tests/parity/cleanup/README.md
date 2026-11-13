# Cleanup parity fixture

`fixture.py` builds one repo with every case a cleanup command decides: a merged feature branch,
an unmerged one, a branch whose leaf is Complete, a claimed branch, a live worktree, a merged clean
worktree, a merged dirty worktree, a registry row with no branch, a registry row for a Complete
leaf, a specy-road stash and a foreign stash. Each has a fixed row id (the table in `fixture.py`).

`golden/old_selections.json` is what `doctor`, `branches prune`, `registry-prune`,
`worktree prune <ID>` and `grind-session --delete-merged-branches` selected on that fixture before
the cleanup planner existed. `python -m tests.parity.cleanup.record` rewrites it from the commands
as the checkout has them; run it on that commit to check the record.

`reconciliation.yaml` fixes, for each fixture row, the action and reason under each old command and
under `doctor --prune` and each `--kind` (branches, worktrees, registry, stashes). A row whose
action differs from the old record is a `decided` reduction, never a new removal.
`test_reconciliation.py` runs every command on a fresh fixture and holds it to the table, and checks
that applying `doctor --prune --yes` and `branches prune --delete` removes exactly the planned rows.
