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
