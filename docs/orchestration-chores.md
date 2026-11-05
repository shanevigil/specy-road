# Chores: worker-run work outside the roadmap

## Agent quickstart

**Use this doc when:** environment repair or other ad-hoc work should run on a worker, with its usage and review recorded, but has no roadmap leaf.
**Not for:** roadmap leaves — pick them up and delegate them as in [`orchestration-workers.md`](orchestration-workers.md).

**Must know without reading on:**
- `specy-road chore start <slug> --task TEXT --zone PATH` writes `work/chores/<slug>.json` in the main checkout: no roadmap node, branch or registry row. The chore runs in this checkout (or `--worktree`) on the branch checked out there, and `base` is that branch's head at start.
- `worker delegate <slug>`, `worker usage <slug>` and `review delegate <slug>` take the slug where they take a node id; `worker message`, `resume`, `sync`, `reconcile` and the rest work on its worker id as for a leaf.
- `--zone` (repeatable) declares touch zones as a leaf does: `worker reconcile` flags a change outside them (`needs_reconcile`).
- `--review` makes review possible (`specy-road review delegate <slug> --model <reviewer>`); without it `review delegate` refuses and `chore close` records `unreviewed (no review was run)`.
- `chore close <slug> --summary TEXT` refuses while a worker is still running, ends idle ones, and writes `work/chores/<slug>.md`; a closed chore takes no more turns.
- `chore garden` runs read-only drift scans, one finding per line; `--open-chores --under <PARENT>` files each finding class as at most one roadmap leaf. See [Gardening](#gardening).

**Related:** [`orchestration-workers.md`](orchestration-workers.md), [`orchestration-review.md`](orchestration-review.md).

## Starting

```bash
specy-road chore start fix-env --task "Repair the pinned toolchain" --zone scripts/ --zone .tool-versions --review
```

The slug is lower-case letters, digits and `-`, never a node id and never
starting with `w-` (a worker id). The checkout must be on a branch, not a
detached head. `--model` and `--harness` set the defaults `worker delegate
<slug>` uses. The model may be off the roster (`roadmap/orchestration.yaml`) when
`--harness` names where it runs (`claude-code`, `codex`, `cursor`); such a
model runs with the harness's default command and no roster checks. A rostered
model keeps its roster harness, profile and executor-role checks.

## Running

```bash
specy-road worker delegate fix-env            # the chore's --model, or pass --model ID
specy-road worker sync                        # as for any worker
specy-road worker reconcile w-0007            # changed paths since base vs the chore's zones
specy-road worker usage fix-env               # tokens and cost per attempt, and the total
```

The executor's prompt is the task, the zones and the commit rules; it has no
brief. The tree must be clean, as for a leaf: delegate refuses uncommitted
changes. A chore's worker is never reported orphaned for lack of a claim; once
the chore is closed, a worker still held on it is.

## Review

With `--review`, `specy-road review delegate fix-env --model <reviewer>` runs a
rostered reviewer in the chore's worktree on `git diff <base>..<head>`. Its
prompt names `work/reviews/<slug>/REVIEW-<model>.md` and the record's form, with
the task as acceptance `A1`. The run is `complete` once a valid record for the
current head is on file. There is no gate: the verdict is recorded, not enforced.

## Closing

```bash
specy-road chore close fix-env --summary "Pinned toolchain repaired; make check passes"
```

`work/chores/<slug>.md` holds the task, worktree, branch and `base..head`, the
zones, the summary, `worker usage`'s lines for every attempt, and one line per
valid review record (`<model>: approve|block at <commit>`), or `unreviewed`.
The chore's JSON keeps `closed_at`, so the slug cannot be started again.

## Gardening

```bash
specy-road chore garden                                   # report: one finding per line
specy-road chore garden --json                            # the same, for machines
specy-road chore garden --open-chores --under M12         # also file each finding class as a leaf
```

`chore garden` finds drift between what the toolkit enforces and what the docs
and agent files claim. Each finding is one line, `<class>: <path>:<line>: <detail>`,
with paths relative to the git root; the exit code is 0 whether or not there are
findings, because it is a report. It edits nothing tracked.

| Class | What it reports |
| --- | --- |
| `stale-command` | A `specy-road` or `specyrd` command this version does not register, named in `docs/**/*.md`, `AGENTS.md`, `CLAUDE.md` (project and git roots), `.specyrd/AGENTS.md` or `.specyrd/AGENTS.team.md`. It is the scanner `validate` runs on the agent files, over more files and over whole files, managed blocks included (`validate` skips those); it checks command names, not flags. |
| `advisory-rule` | A provenance comment (`<!-- prevents: … \| enforced: advisory … \| ref: … -->`) in a managed agent file, or in the templates they are rendered from when those are in this checkout (rendering strips the comments): one line per rule nothing checks. |
| `ratchet-grew` | A `policy.ratchet_paths` baseline with lines added since the newest tag (`git describe --tags --abbrev=0`), reported as `<path>: +N line(s) since <tag>`. With no tag, or no integration branch to read the policy from, the scan reports nothing and says why once on stderr. |

`--open-chores --under <PARENT>` adds at most one leaf under `PARENT` per class
with findings by running `add-node` itself, so every check `add-node` makes
applies (parent exists, milestone lock, unique id, title and codename, chunk
routing). The leaf gets its title from the class (for example `Garden: stale
command mentions`), codename `garden-<class>`, one acceptance line per finding
path (the first 10, then a count of the rest) and the finding paths as touch
zones. A node belongs to a class when its codename (`garden-<class>` or
`garden-<class>-N`) or its title (`<title>` or `<title> (N)`) says so, under
any parent. While a live leaf of the class is not Complete, a run adds nothing
for it and prints that leaf's id. Otherwise the new leaf is generation N + 1,
where N is the highest generation any live or archived node of the class
carries, so a number is never reused. When `add-node` refuses, the run exits 1
with its reason. The leaves are picked up,
delegated and reviewed like any other; gardening never fixes a finding itself.

### Cadence

```yaml
# roadmap/orchestration.yaml
policy:
  garden_cadence_days: 14
```

Each run records its date in `work/chores/.garden.json`, which the managed
`.gitignore` block ignores (`specy-road refresh-stubs` adds the line to an older block). With `policy.garden_cadence_days` set, `specy-road validate`
warns "gardening due: last run <date>, every N days; run `specy-road chore garden`"
once more than N days have passed, or `never run` when there is no record. The
warning is never fatal; unset, there is none.

### Unattended

Run the report on a schedule and let a person or coordinator decide what to file:

```bash
# cron or a scheduled CI job, from the checkout root
specy-road chore garden --json > work/garden-report.json
# then, after reading it
specy-road chore garden --open-chores --under <PARENT>
```

Each run, report or not, resets the cadence clock.

## Cleanup

```bash
specy-road worktree cleanup <ID>            # after finish-this-task lands <ID>, from the main checkout
specy-road worktree sweep --dry-run         # every landed worktree nothing holds: what would go
specy-road worktree sweep                   # remove them; --delete-local-branch also drops their local branches
```

`worktree cleanup <ID>` first moves the hand-off files in the leaf worktree's
own `work/reviews/<ID>/` (review `history/` copies, `RUN-*` logs) into the main
checkout's shared hand-off directory. It never overwrites a different file: a
same-named file with other bytes is kept beside it as
`<name>.from-worktree<n>`. Then it runs `worktree prune`'s checks (branch merged
into the remote's integration tip, nothing uncommitted, untracked or stashed,
no running worker, no other repository's worktree inside) and also refuses on
ignored files that are not regenerable: anything but `__pycache__/` and the
tool caches, `node_modules/`, `work/prompt-*.md`, `work/brief-*.md`,
`work/.on-complete-*.yaml` and `.specyrd/cache/`. Every check reads the
worktree as it is, before anything moves: a refusal moves and removes nothing
and prints one line per reason. A directory under `work/reviews/` holding
another repository (a `.git` file or directory, a bare layout) refuses and
stays where it is; it is never treated as hand-off files. Otherwise it terminates the leaf's idle worker,
removes the worktree and ends the session records (worker, reviewer, session)
tied to the worktree or its branch, so `session list` shows none for the leaf.

`worktree sweep` looks at every linked worktree, wherever it lives
(`work/.worktrees/`, `.claude/worktrees/`, a temp directory). It removes one
only when its branch tip or detached `HEAD` is an ancestor of the
integration branch (`git merge-base --is-ancestor`; a branch with no commits
of its own counts, a squashed or same-patch one does not), no registry claim,
non-terminal worker or live session holds it (`doctor`'s live rules), and the
cleanup checks pass, saving hand-off files first. Each worktree gets one line: `removed`, `would remove`
or `kept <path>: <reason>`. It ends orphaned workers first. Once a worktree is
gone, its branch is no longer checked out anywhere, so branch pruning no
longer skips it as `(worktree)`.

Remote branches are never deleted. A local branch is deleted only with
`--delete-local-branch`, and only when the integration branch contains it. The
main checkout's own `work/` files are `finish-this-task`'s to clean.

**Before `gh pr merge --delete-branch`:** deleting a leaf's branch does not
look inside its worktree, which may still hold uncommitted or ignored hand-off
files (`work/reviews/<ID>/history/`). Run `specy-road worktree cleanup <ID>`
first; it saves those files before anything is removed.

### In grind-session

`grind-session` runs `worktree cleanup <ID>` after each leaf it lands (a
`worktree_cleanup` event; never fatal). With

```yaml
# roadmap/orchestration.yaml
policy:
  worktree_sweep: between_leaves   # default: off
```

it also runs `worktree sweep` between leaves (a `worktree_sweep` event).
