# Steering files

Some files an executor can write are later read or run by trusted code outside it: the coordinator's harness, git,
the coordinator's shell, and specy-road's own gate. The one list is `specy_road/steering_paths.py` (finish's refusal and the launch denies are in `specy_road/steering_gate.py`); the worker flags and the post-run check are in [orchestration-workers.md](orchestration-workers.md). For each worker
turn it is snapshotted in the worker's worktree and in the main checkout (one real path is stored once; paths are
named project-relative in the worker's tree, as `zone_matches` compares them, and absolute elsewhere):

| Class | What |
|---|---|
| `harness` | `.claude/settings*.json`, `.claude/hooks/**`, `.codex/**`, `.cursor/*.json`, `.cursor/hooks/**`, at the git root and the project root |
| `git_hook` | the hooks directories: the one git names at the turn's start (`rev-parse --git-path hooks`, asked before the executor acts), plus `<common-git-dir>/hooks`, `<worktree-gitdir>/hooks` and each `core.hooksPath` value read from the config files below (relative to the checkout); after the turn read from the filesystem only, direct regular-file names with sha256, not recursive, or the one marker `capped` past 200 children |
| `git_config` | the bytes of every config file git names at the turn's start (`config --list --show-origin --includes`: global, system, the common `config`, `config.worktree` and their includes, conditions evaluated), plus the common `config`, `config.worktree` and every file they name by `include.path` or `includeIf.*.path` as `specy_road/git_config_text.py` reads them (conditions not evaluated, git's depth of 10); after the turn read from the filesystem only, no git command. The finding also names the changed values of `core.hooksPath`, `core.fsmonitor`, `core.sshCommand`, `include.path` and `includeIf.*.path` |
| `policy_tree` | `roadmap/orchestration.yaml`, `roadmap/orchestration.local.yaml`, `roadmap/git-workflow.yaml` in the tree |
| `policy_blob` | the same three as blobs at the local integration branch tip (no fetch), so a roster commit made from another checkout shows |
| `registry` | each `roadmap/registry.yaml` `entries` item whose `node_id` is another leaf |
| `review_file` | every file under each checkout's `work/reviews/` except the leaf's own `READY-*` |
| `shell_startup` | root `.bashrc`, `.bash_profile`, `.profile`, `.zshrc`, `.zshenv`, `.envrc` |
| `env_bin` | for each `env_setup.link` path in each checkout (the worker's link and its source are one directory), its `bin/` entry names, types, link text and resolved regular-file sha256 (a write through an unchanged `.venv/bin/python` link changes the digest, not the link) |
| `symlink` | a porcelain entry in either checkout, new or retargeted during the turn, whose target resolves outside the worker's git root |

**After each turn** the post-run check compares the git half first, from the filesystem, before any post-turn git
command: on a change it records the finding and a `git_probes_skipped` finding and runs none of the git probes, so
`git status` never runs under a `core.fsmonitor` or hook the turn changed. Otherwise the git probes run, then the
rest is compared. Each change is one `steering_file` finding (`path`, `class`, `before`, `after`: a sha256,
`link:<target>` (followed by `@<sha256>` when the link resolves to a regular file, so a write through an
unchanged link changes it; a link to a directory is not walked), `absent`, or for `git_config` the digest followed by `;key=value` per changed watched key), which
replaces any `porcelain` or `committed_outside_zones` mention of the same path. A path two classes reach (a harness
file that is also a new escaping symlink, a hooks directory inside `.claude/hooks`) is one finding, of the class
listed first in the table. It sets the sticky `steering_changed`
flag (`worker status --json` `flags`, `handoff status --json` `workers[].flags`); `worker reconcile W` lists the
findings and clears it.

**An input that cannot be read.** One rule covers every class: each file and directory is listed, read, decoded,
parsed and hashed on its own, and any failure there (invalid UTF-8, a permission error, a dangling link or a link
loop, malformed YAML, a parsed file over 8 MiB, a file gone mid-read) is one `check_error` finding naming that path
and its class. The comparison goes on for every other path, so their findings and the `steering_changed` flag are
kept. A path that cannot be read is never reported as unchanged, and one in the git half (a config file, a hooks
directory or a hook) counts as git steering not verified, so no post-turn git command runs. Only a path that does not
exist is `absent`; a missing include is left out, as git leaves it out.

**What git is asked, and when.** Git is asked only at the turn's start, before the executor acts, which hooks
directory and config files it uses; after the turn those files and directories are compared from the filesystem.
The text parser (`specy_road/git_config_text.py`: a byte-order mark, CRLF, quoting, escapes, comments and continued
lines as git reads them) only adds candidates to what git named, so it does not decide coverage. Its limit: a hooks
directory or config file git would use only because of a change made during the turn is not watched itself; the
change that points git there is, by its file's digest. The check fails closed: with no snapshot from the turn's start
(it could not be taken) or a git-steering comparison that fails, a `check_error` is recorded and no post-turn git
command runs.

**Outside detection:** there is no directory walk for symlinks, so a link under a gitignored path, or one created
and removed within one turn, is not seen; neither is a change made and reverted within one turn. Other workers and
the coordinator write some of these paths too (their own READY, review records and registry rows), and such a write
during the turn is reported like the executor's. Nothing is restored: the check detects, finish refuses (below), and
the human decides.

**At finish:** `finish-this-task` refuses, before its bookkeeping commit, a branch whose diff against the merge base
changes an in-tree steering path (harness config and hooks, the three policy files, root shell startup files) unless
a touch zone names that exact path; a directory or glob zone does not count, and `roadmap/registry.yaml` is ignored.
The message names each path: add that exact path to the leaf's touch zones with `specy-road edit-node` and get it
reviewed, or revert it.

**At launch:** a Claude Code executor's launch and resume deny each steering file per path
([orchestration-harness-launch.md](orchestration-harness-launch.md#steering-files-at-launch)).
