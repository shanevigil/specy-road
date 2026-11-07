# Steering files

Some files an executor can write are later read or run by trusted code outside it: git runs the hooks and reads
the config in the common git dir, which every worktree of the repository shares. The one list is `specy_road/steering_paths.py`; the worker flags and the post-run check are in [orchestration-workers.md](orchestration-workers.md). For each worker
turn it is snapshotted in the worker's worktree and in the main checkout (one real path is stored once; paths are
named project-relative in the worker's tree, as `zone_matches` compares them, and absolute elsewhere):

| Class | What |
|---|---|
| `git_hook` | the hooks directories: the one git names at the turn's start (`rev-parse --git-path hooks`, asked before the executor acts), plus `<common-git-dir>/hooks`, `<worktree-gitdir>/hooks` and each `core.hooksPath` value read from the config files below (relative to the checkout); after the turn read from the filesystem only, direct regular-file names with sha256, not recursive, or the one marker `capped` past 200 children |
| `git_config` | the bytes of every config file git names at the turn's start (`config --list --show-origin --includes`: global, system, the common `config`, `config.worktree` and their includes, conditions evaluated), plus the common `config`, `config.worktree` and every file they name by `include.path` or `includeIf.*.path` as `specy_road/git_config_text.py` reads them (conditions not evaluated, git's depth of 10); after the turn read from the filesystem only, no git command. The finding also names the changed values of `core.hooksPath`, `core.fsmonitor`, `core.sshCommand`, `include.path` and `includeIf.*.path` |

**After each turn** the post-run check compares these from the filesystem, before any post-turn git
command: on a change it records the finding and a `git_probes_skipped` finding and runs none of the git probes, so
`git status` never runs under a `core.fsmonitor` or hook the turn changed. Otherwise the git probes run. Each change is one `steering_file` finding (`path`, `class`, `before`, `after`: a sha256,
`link:<target>` (followed by `@<sha256>` when the link resolves to a regular file, so a write through an
unchanged link changes it; a link to a directory is not walked), `absent`, or for `git_config` the digest followed by `;key=value` per changed watched key), which
replaces any `porcelain` or `committed_outside_zones` mention of the same path. It sets the sticky `steering_changed`
flag (`worker status --json` `flags`, `handoff status --json` `workers[].flags`); `worker reconcile W` lists the
findings and clears it.

**An input that cannot be read.** One rule covers every class: each file and directory is listed, read, decoded,
parsed and hashed on its own, and any failure there (invalid UTF-8, a permission error, a dangling link or a link
loop, a parsed file over 8 MiB, a file gone mid-read) is one `check_error` finding naming that path
and its class. The comparison goes on for every other path, so their findings and the `steering_changed` flag are
kept. A path that cannot be read is never reported as unchanged, and it counts as git steering not verified, so no post-turn git command runs. Only a path that does not
exist is `absent`; a missing include is left out, as git leaves it out.

**What git is asked, and when.** Git is asked only at the turn's start, before the executor acts, which hooks
directory and config files it uses; after the turn those files and directories are compared from the filesystem.
The text parser (`specy_road/git_config_text.py`: a byte-order mark, CRLF, quoting, escapes, comments and continued
lines as git reads them) only adds candidates to what git named, so it does not decide coverage. Its limit: a hooks
directory or config file git would use only because of a change made during the turn is not watched itself; the
change that points git there is, by its file's digest. The check fails closed: with no snapshot from the turn's start
(it could not be taken) or a git-steering comparison that fails, a `check_error` is recorded and no post-turn git
command runs.

**Outside detection:** a change made and reverted within one turn is not seen. Nothing is restored: the check detects, and
the human decides.
