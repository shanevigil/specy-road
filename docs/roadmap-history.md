# Roadmap history

A roadmap tells you where things stand. It does not tell you how they got there
— which statuses a milestone passed through, which dependency someone added and
later removed, that M1.2 used to be M1.4, or that half a phase was archived last
quarter. On a long-running project, and especially one driven by agents, that
missing context gets re-derived over and over: decisions are remade, dropped
dependencies are re-added, and archived work looks like work that was never done.

`specy-road history` answers those questions from git.

```bash
specy-road history M1.2                 # one node's timeline
specy-road history                      # roadmap-wide feed, newest first
specy-road history --since 2026-01-01
specy-road history --archived           # only work that left the live graph
specy-road history --json               # for tooling
specy-road history --rebuild            # discard the cache and re-walk
```

Every brief also carries a `## 9. History` section built from the same index, so
an implementing agent gets this context without asking for it. `specy-road brief
--no-history` omits it.

## Derived, never stored

**There is no history file to commit.** Git already records every roadmap
change; a second copy in the repo would be a thing to seed, migrate, resolve
conflicts in, and keep honest. `roadmap/archive/index.json` is the one durable
ledger specy-road keeps, and it exists because archiving *removes* information
from the graph — history does not have that problem.

What is stored is a **cache**, at `.specyrd/cache/roadmap-history.json`, and it
is gitignored. Because git is always authoritative, the cache is never migrated:
a version it does not recognise is discarded and rebuilt.

| Situation | What happens |
| --------- | ------------ |
| `HEAD` unchanged | The cache is reused verbatim. |
| `HEAD` moved forward | Only the new commits are walked and appended. |
| History rewritten (rebase, amend, force-push) | Full rebuild — the cached commit is no longer reachable, so its events describe commits that no longer exist. |
| Cache missing, corrupt, or a different `cache_version` | Full rebuild. |
| Cache directory unwritable | Rebuild each time. Nothing fails. |

Only `.specyrd/cache/` is ignored — `.specyrd/manifest.json` stays tracked.

## Events are keyed by `node_key`, not `id`

This is the load-bearing decision. `node_key` is an immutable UUID; `id` is a
**position in the outline** and renumbers freely as work is reorganised. An
id-keyed history would lose a node's past every time a milestone was inserted
above it.

So a renumbering is recorded as an ordinary event and the node's story stays
continuous across it:

```
M1.2  node_key 3f9a…
2026-02-03  a1b2c3d  created as M1.4
2026-02-11  d4e5f6a  status Not Started -> In Progress
2026-02-14  b7c8d9e  no longer depends on M0.4 — Payment gateway
2026-03-09  c3d4e5f  renumbered M1.4 -> M1.2
2026-04-20  e6f7a8b  status In Progress -> Complete
```

The same fact makes `specy-road history M1.2` ambiguous when several nodes have
held that id and none holds it now. specy-road **says so and exits 2**, listing
each candidate `node_key` with the ids it carried, rather than guessing and
silently showing the wrong node's past.

Resolution order for a `NODE_ID` argument: the live graph, then the archive
ledger, then — if it looks like a UUID — the key itself, then history.

## What is recorded

| Kind | Meaning |
| ---- | ------- |
| `created` / `removed` | A `node_key` entered or left the live graph. `removed` means a hard delete; archiving is reported separately. |
| `status` | Own status changed. Not `rollup_status`, which is derived on load and never persisted, so it has no history to read. |
| `renumbered` / `retitled` / `recodenamed` / `reparented` | Identity and placement changes. |
| `dep_added` / `dep_removed` | One dependency edge each. A removed edge is a decision someone already made. |
| `sheet_edit` | A commit touched the node's planning sheet — where the thinking behind a feature actually changes. |
| `archived` / `restored` | From `roadmap/archive/index.json`, carrying the `archive_id` to inspect. |

Archiving and restoring would otherwise show up as `removed` and `created`,
which is misleading — nothing was deleted or invented. Those are reconciled away
in favour of the ledger's richer event. A genuine hard delete still reports
`removed`.

## Cost

One `git log --raw` pass plus one long-lived `git cat-file --batch` process, for
the whole history.

`--raw --no-abbrev` prints the new blob SHA of every changed file alongside each
commit, so the walk learns what to read without a second query per commit, and a
graph is rebuilt only on commits that actually changed the manifest or a chunk.
Parsed chunks are memoised by blob SHA, so a chunk unchanged across a thousand
commits is parsed once. Planning-sheet events cost nothing at all: the flat-
`planning/` naming rule puts the `node_key` in the filename, so a sheet touch is
attributed from the path.

The approach deliberately **not** taken is `load_roadmap_nodes_at_ref` per
commit, which costs `1 + chunks` subprocesses each time. That is the same trap
[`node_activity`](../specy_road/node_activity.py) documents for per-node git
lookups — about 31s against 0.17s on a 400-node roadmap — and over thousands of
commits it is hopeless.

## The walk follows `--first-parent`

History is read along the mainline: each step is a state the integration branch
actually passed through, and a merged feature branch arrives as a single step.
Work in progress on the branch is not history the mainline can tell.

Walking with `--no-merges` instead would interleave parallel branches and
manufacture flip-flop events — a status reading A→B→A→B when nothing of the sort
happened on the branch anyone reads.

This differs from [last-worked-on](archiving.md#last-worked-on), which *excludes*
merges, and the difference is deliberate. That question is "when was real work
done on this node?", where a merge carrying someone else's edit is not work.
This question is "what did the roadmap look like at each step?", where a merge
*is* a transition.

## The JSON contract

`--json` is what an agentic IDE should consume. A node query returns:

```json
{
  "node_key": "3f9a…",
  "ids": ["M1.4", "M1.2"],
  "events": [
    {
      "seq": 41,
      "at": "2026-03-09T14:02:55-07:00",
      "commit": "c3d4e5f…",
      "author": "pat",
      "node_key": "3f9a…",
      "kind": "renumbered",
      "id": "M1.2",
      "from": "M1.4",
      "to": "M1.2"
    }
  ]
}
```

A feed query returns `{"events": [...]}` with the same event shape.

`seq` is the event's position in the walk, and it is what to sort by. Commit
timestamps are second-resolution, so several roadmap commits made in the same
second tie; breaking that tie any other way can order a status change before the
one that preceded it.

Every event carries its `commit`, so anything this does not answer can be
resolved against git directly — `git show <commit>`, `git log -p` on the node's
planning sheet, and so on.

## Limits

- **Committed work only.** Uncommitted edits are not history yet.
- **Shallow clones** yield only the history they contain.
- **A very long history is bounded** at 50,000 commits, matching
  `node_activity`. Beyond that the earliest events are not walked.
- **Deleted planning sheets** still produce a `sheet_edit`: the node was
  touched, and the path is recorded as it was at that commit.

## See also

- [`archiving.md`](archiving.md) — where archived work goes, and why history is
  the only place it stays visible
- [`roadmap-authoring.md`](roadmap-authoring.md) — `node_key` vs `id`, chunks,
  the manifest
- [`pm-workflow.md`](pm-workflow.md) — the PM-side roadmap commands
