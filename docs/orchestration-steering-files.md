# Steering files

Some files a leaf's branch can change are later read or run by trusted code outside the executor: the coordinator's
harness, the coordinator's shell, and specy-road's own gate. The list and finish's refusal are in
`specy_road/steering_gate.py`. Paths are matched project-relative, as touch zones are, and the harness and shell
paths also at the git root (in a nested project, where the two differ):

| Class | What |
|---|---|
| `harness` | `.codex/**`, `.claude/settings*.json`, `.claude/hooks/**`, `.cursor/*.json`, `.cursor/hooks/**`, at the git root and the project root |
| `policy_tree` | `roadmap/orchestration.yaml`, `roadmap/orchestration.local.yaml`, `roadmap/git-workflow.yaml` under the project root |
| `shell_startup` | `.bashrc`, `.bash_profile`, `.profile`, `.zshrc`, `.zshenv`, `.envrc` at the git root and the project root |

`roadmap/registry.yaml` is not on the list: finish writes it itself.

**At finish:** `finish-this-task` refuses, before its bookkeeping commit, a branch whose diff against the merge base
changes a path on the list unless a touch zone names that exact path; a directory or glob zone does not count. This
is the merge-point check on every platform, with or without a worker sandbox. The message names each path and the
next step: add that exact path to the leaf's touch zones with `specy-road edit-node` and get it reviewed, or revert
it on the branch. If the integration ref, the merge base or the list of changed paths cannot be read, finish refuses
too and names what it could not read; nothing is committed in either case.

A leaf that needs a policy file such as `roadmap/git-workflow.yaml` as its starting point should get it from the
integration branch (commit it there and merge the integration branch into the leaf), so the leaf's own diff does not
change it.
