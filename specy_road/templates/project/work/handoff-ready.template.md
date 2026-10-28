---
# Copy to work/reviews/<NODE_ID>/READY-<your roster id>.md when your implementation
# is committed, then stop. If you work in a separate worktree, write the file
# into the main checkout (specy-road reads work/reviews/ from there).
# Quote SHAs: YAML reads 0123456 as an octal number.
node_id: M1.1
agent: your-roster-id   # the `id` of your entry in roadmap/orchestration.yaml
branch: feature/rm-codename
commit: "full or 7+ char SHA of your last implementation commit"
base: "SHA your branch started from (git merge-base <integration> HEAD)"
changed_paths: [src/example.py]
verify:
  - {cmd: "the verifier or test command you ran", exit: 0, tail: "last lines of its output"}
---
Optional notes for the coordinator: anything you could not finish, and why.
