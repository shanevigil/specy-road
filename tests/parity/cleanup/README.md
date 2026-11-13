# Cleanup parity fixture

`fixture.py` builds one repo with every case a cleanup command decides: a merged feature branch,
an unmerged one, a branch whose leaf is Complete, a claimed branch, a live worktree, a merged clean
worktree, a merged dirty worktree, a registry row with no branch, a registry row for a Complete
leaf, a specy-road stash and a foreign stash. Each has a fixed row id (the table in `fixture.py`).

`golden/old_selections.json` is what `doctor`, `branches prune`, `registry-prune`,
`worktree prune <ID>` and `grind-session --delete-merged-branches` selected on that fixture before
the cleanup planner existed. `python -m tests.parity.cleanup.record` rewrites it from the commands
as the checkout has them; run it on that commit to check the record.
