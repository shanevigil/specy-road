# Linked worktrees: project root and environment

`do-next-available-task --worktree` and `worker delegate` put each leaf in a linked git worktree (by default
`work/.worktrees/<codename>` under the main checkout's project root). This page covers two things that work
differently there: how a command finds the project root, and how the new worktree gets its environment.

## Which checkout a command uses

Commands resolve the project root as follows: `--repo-root`, then `SPECY_ROAD_REPO_ROOT`, then the root
recorded in `.specyrd/manifest.json`, then discovery (see `specy_road/runtime_paths.py`).

If `SPECY_ROAD_REPO_ROOT` names a checkout and the current directory is inside a **different worktree of the
same repository** (git reports the same common git directory for both), the command uses the same
project-relative path in the worktree you are in, and prints nothing about it. So an exported
`SPECY_ROAD_REPO_ROOT=/path/to/main/sr` does not send `specy-road ready` in a leaf worktree back to the main
checkout, where it would be refused for being on the wrong branch. If the current directory is in a different
repository, or outside git, the variable is used as written, as before.

`worker delegate` (and the resumed turns of `worker message` / `resume`) also sets `SPECY_ROAD_REPO_ROOT` in
the worker's environment to the worker's own project root in its worktree.

## Worktree environment (`env_setup`)

A linked worktree holds tracked files only. Virtual environments, `node_modules` and ignored files such as
`.python-version` or `.env` stay in the main checkout. Declare what a new leaf worktree gets under
`env_setup` in **`roadmap/git-workflow.yaml`** at the project root (schema:
`schemas/git-workflow.schema.json`). It runs once, when pickup or delegate creates the worktree; `doctor`
checks it in the main checkout. Each path is project-relative; `../` may climb from a nested project root to
its git root, and no further.

Command form: build the environment in the new worktree.

```yaml
env_setup:
  copy:
    - .python-version
    - {from: .env.example, to: .env}
  cmd: uv sync --all-packages --all-groups --locked
```

Link form: share the main checkout's environment through symlinks.

```yaml
env_setup:
  link: [node_modules, .venv]
```

The steps run in this order: `copy`, then `link`, then `cmd`. You can combine the forms. A missing source, or
a link path that already exists in the worktree, stops the pickup or launch, and the worktree stays as it is.

### Why linked names go in `.git/info/exclude`

Git treats a symlink as a file, even when it points to a directory, so a directory-only ignore pattern such
as `node_modules/` does not match the symlink, and `git status` would list it as untracked. For each `link`
path, specy-road adds an anchored line (`/node_modules`, or `/sr/node_modules` in the nested layout) to
the exclude file that `git rev-parse --git-path info/exclude` names in the worktree. Git keeps `info/exclude`
in the **common** git directory, so this file is `.git/info/exclude` of the main checkout and applies to
every worktree of the repository. In the main checkout the line matches the real directory, which was
already ignored. `worker delegate`'s clean-tree check also skips untracked entries that are declared `link`
paths, so a symlink someone made by hand before the exclude line existed does not block a launch.

Out of scope: copying a whole environment (use `cmd` to build one, or `link` to share it).
