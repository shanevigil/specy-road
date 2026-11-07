# Steering files

Some files an executor can write are later read or run by trusted code outside it: git runs the hooks and reads
the config in the common git dir, which every worktree of the repository shares. The one list is `specy_road/steering_paths.py`; the worker flags and the post-run check are in [orchestration-workers.md](orchestration-workers.md). For each worker
turn it is snapshotted in the worker's worktree and in the main checkout (one real path is stored once: a config
file by the file it resolves to, so one file reached by two names is one entry; paths are named project-relative in the worker's tree, as `zone_matches` compares them, and absolute elsewhere):

| Class | What |
|---|---|
| `git_hook` | the hooks directories: `core.hooksPath` when set (each value read from the config files below, relative to the checkout), else `<common-git-dir>/hooks` and `<worktree-gitdir>/hooks`. A value that only an `includeIf` names may not apply (its condition is not evaluated), so with no other value the default directories are watched as well; direct entries only, not recursive: each regular file (a link followed) by name with its sha256, a subdirectory skipped. A hooks directory with more than 200 direct children is one `check_error` naming that directory on every comparison, changed or not (the listing stops reading after 201 entries) |
| `git_config` | the bytes of the common `config` and `config.worktree` and every file they name by `include.path` or `includeIf.*.path` as `specy_road/git_config_text.py` reads them (conditions not evaluated, git's depth of 10). The finding also names the changed values of `core.hooksPath`, `core.fsmonitor`, `core.sshCommand`, `include.path` and `includeIf.*.path` |

Both are read from the filesystem only, at the turn's start and at its end; no git command is run for them.

**After each turn** the post-run check compares this snapshot before any post-turn git command: on a change it
records the finding and a `git_probes_skipped` finding and runs none of the git probes, so `git status` never runs
under a `core.fsmonitor` or hook the turn changed. Otherwise the git probes run. Each change is one `steering_file`
finding (`path`, `class`, `before`, `after`: a sha256, `absent`, or for `git_config` the digest followed by
`;key=value` per changed watched key), which replaces any `porcelain` or `committed_outside_zones` mention of the
same path. It sets the sticky `steering_changed` flag (`worker status --json` `flags`, `handoff status --json`
`workers[].flags`); a clean turn leaves it set, and `worker reconcile W` (without `--dismiss`) prints one
`path class before after` line per `steering_file` finding recorded while it was set, then clears it.

**Runner order.** The wrapper runs this check before it reads the turn's READY. A READY that cannot be parsed
(invalid UTF-8 included) is the turn's completion error (`exit 0; READY file invalid: ...`), not an exception, so
the turn still ends with exactly one `post_run_check`.

**An input that cannot be read.** One rule covers both classes: each file and directory is listed, read, decoded,
parsed and hashed on its own, and any failure there (a permission error, a special file such as a FIFO, which is
never opened for a blocking read, a dangling link or a link loop, a parsed file over 8 MiB, a file gone mid-read,
the snapshot past its 30 s budget, a hooks directory over 200 entries) is one `check_error` finding naming that path and
its class. What that path lists or includes is not compared at that end: a hook of an unreadable or over-cap hooks
directory, or a file an unreadable config includes, is not reported as `absent`, since that end could not see it.
The same holds for a hooks directory the config no longer names: its hooks are not reported, the config change is. The comparison goes
on for every other path, so their findings and the `steering_changed` flag are kept. A path that cannot be read is
never reported as unchanged, and it counts as git steering not verified, so no post-turn git command runs. With no
snapshot from the turn's start (it could not be taken) or a comparison that fails, the check fails closed the same
way: a `check_error` per class naming the worktree, and the git probes skipped. It never aborts the turn. Only a
path that does not exist is `absent`; a missing include is left out, as git leaves it out.

**What the parser covers.** Git is never asked what it reads: the text parser (`specy_road/git_config_text.py`: a
byte-order mark, CRLF, quoting, escapes, comments and continued lines as git reads them) decides which hooks
directories and included files are watched. Its limit: a hooks directory or config file git would use only because
of a change made during the turn is not watched itself; the change that points git there is, by its file's digest.
Global and system config files are not watched.

**Outside detection:** a change made and reverted within one turn is not seen. Nothing is restored: the check detects, and
the human decides. Harness config and hooks, the roadmap policy files, other leaves' registry entries,
`work/reviews/` files, shell startup files, `env_bin` and symlinks are M22.30; finish's refusal is M22.31; the
Claude Code launch denies are M22.32.
