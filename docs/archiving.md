# Archiving completed work

Roadmaps only grow. Every finished milestone keeps sitting in
`roadmap/phases/*.json`, its planning sheet keeps sitting in `planning/`, and
both keep loading, validating, exporting and rendering forever. On a
long-running project that eventually pushes chunks against
`roadmap_json_chunk_max_lines`, slows `brief` assembly, and buries live work in
the PM GUI.

Archiving moves a **completed subtree out of the live roadmap** and into
`roadmap/archive/`, reversibly.

> Archiving is not the PM GUI's **Hide Complete** button. That is a view filter
> and nothing more — it hides rows, touches no files, and is unaffected by
> anything on this page. Archiving changes what is on disk.

## Quick reference

```bash
specy-road archive M0.2               # archive one Complete subtree
specy-road archive M0.2 --dry-run     # show the plan, write nothing
specy-road archive --auto             # everything Complete for 90+ days
specy-road archive --auto --older-than-days 180
specy-road archive M0.2 --deep        # archive and bundle it away in one step
specy-road deepen-archive <ARCHIVE_ID>
specy-road list-archives              # what is archived (add --json)
specy-road show-archive <ARCHIVE_ID>  # detail, including git provenance
specy-road restore-archive <ARCHIVE_ID>
```

Nothing here commits. An archive is an ordinary roadmap change left in the
working tree; publish it the way you publish any other roadmap edit.

## What moves

```text
roadmap/
  manifest.json                          # the archived chunk leaves `includes`
  phases/M0.json                         # rewritten without the archived nodes
  archive/
    index.json                           # the ledger
    chunks/<archive_id>.json             # the archived nodes, still readable
    planning/<archive_id>/*.md           # the archived planning sheets
```

`manifest.json`'s `includes` list is what makes this work. The roadmap loader
merges only the chunks named there, so a chunk file that no include names is
already invisible to every command. Archiving is therefore a file move plus one
manifest edit — no loader changes, no node rewriting.

**Planning sheets land under `roadmap/archive/planning/`, not
`planning/archive/`.** `validate` rejects any subdirectory or nested `.md`
under `planning/` (the flat-`planning/*.md` rule), so parking them there would
break the next validate. Keeping them beside the archived chunk also means one
self-contained directory per archive.

## Two tiers

**Shallow** (the default) leaves the archived nodes on disk as ordinary JSON
under `roadmap/archive/chunks/`. They are out of the live graph but still
readable, greppable, and browsable in the PM GUI.

**Deep** is for work nobody expects to open again. The chunk and its planning
sheets are packed into a single `roadmap/archive/deep/<archive_id>.tar.gz`, the
loose files are deleted, and what stays behind is
`roadmap/archive/refs/<archive_id>.json` — a small, standalone reference naming
the nodes and the git refs they were delivered on. Deep archives are **not**
browsable in the PM GUI; only their reference is.

```text
roadmap/archive/
  index.json
  deep/M0.2-e7fcdb23-20260826.tar.gz    # the only copy of the nodes
  refs/M0.2-e7fcdb23-20260826.json      # what it was, where it landed
```

The index record survives deepening with its `node_keys` and `nodes_summary`
intact, so a deep archive is still listable, still satisfies live dependencies,
and still shows its node titles — without unpacking anything.

`restore-archive` handles both tiers in one command: on a deep archive it
unpacks the bundle and then restores as usual. `deepen-archive` goes the other
way for an archive already on disk.

**The bundle checksum is verified before anything unpacks.** A bundle that does
not match the `sha256` on record is refused outright rather than partially
restored — putting silently-altered roadmap nodes back into the live graph
would be worse than failing.

## Eligibility

A subtree can be archived when its **rollup status is `Complete`** — every leaf
descendant is done. That is the same rollup the PM GUI shows, so what looks
finished is what can be archived.

Two refusals:

- **Not Complete.** `--force` overrides this if you really mean it.
- **An active milestone rollup.** A subtree under a live `milestone_execution`
  is locked, because moving files out from under an in-flight rollup branch
  would strand it. `--force` does *not* override this one.

Any node type works. Archiving a phase takes its milestones with it.

## Dependencies keep working

This is the part worth understanding.

`validate` fails on a dependency whose `node_key` is not in the graph. Archiving
a milestone that live work depends on would trip exactly that check.

specy-road does **not** solve this by rewriting dependencies. Live nodes keep
their `dependencies` arrays byte-for-byte unchanged, and `archive/index.json`
records every archived `node_key`. `validate` consults it as a second source of
resolvable keys: archived implies Complete implies the edge is satisfied.

Two consequences:

- Restore is lossless. There is no edge to reconstruct because none was removed.
- **`roadmap/archive/index.json` is not disposable.** Delete it and every live
  dependency pointing at archived work becomes a hard validation error. Commit
  it like any other roadmap file.

A malformed index raises rather than being treated as empty, for the same
reason — silently starting over would strand every archived edge at once.

## Restore puts things back exactly

Each record stores where every node sat: its chunk and its index in that
chunk's `nodes` array. Restore replays those positions, so an
archive-then-restore round trip leaves **no diff** — including when the subtree
shared a chunk with live nodes, or spanned several chunks. A chunk that the
archive emptied is recreated and re-added to `includes`.

## Auto-archive

`--auto` archives every eligible subtree that has been complete longer than the
threshold (default 90 days, `--older-than-days N` to change it). When subtrees
nest, only the top one is offered — archiving a phase already takes its
milestones.

Completion age comes from `milestone_execution.closed_at` when the subtree went
through a rollup, and otherwise from a `finished` entry in
[`roadmap/activity.json`](#last-worked-on). A subtree with neither has no
completion date and `--auto` skips it; archive those by id.

The PM GUI exposes the same threshold as a preference.

## Last-worked-on

`roadmap/activity.json` records when each node was last touched, keyed by
`node_key`:

```json
{ "version": 1,
  "nodes": { "44ef4a9d-…": { "at": "2026-05-01T09:12:00+00:00", "kind": "finished" } } }
```

`kind` is one of `picked_up`, `reviewed`, `finished`, `edited`, or
`backfilled`. It is written by `do-next-available-task`,
`mark-implementation-reviewed`, `finish-this-task` and `edit-node`, and the PM
GUI shows it as a **Last worked** column on leaf rows.

**Why a sidecar rather than a node field.** `<repo_root>/schemas/roadmap.schema.json`
is consumer-owned and uses `additionalProperties: false`, so a new node field
would fail every existing adopter's `validate` until they hand-edited that file.
Activity also changes on every pickup and finish, which would churn the chunk
diffs that land in each PR for data nobody reviews.

**Writes are best-effort and never fatal.** A read-only checkout or a mangled
sidecar must not be the reason `finish-this-task` fails, so recording failures
are swallowed.

### Seeding an existing repo

Live write points only record from the moment they ship, so an established
roadmap starts with an empty column. `specy-road backfill-activity` derives a
timestamp per node from the last commit touching its planning sheet:

```bash
specy-road backfill-activity --dry-run
specy-road backfill-activity
```

Backfilled entries are recorded as `kind: backfilled` — a **lower bound** on
real activity, not an observation. Backfill never overwrites a newer observed
timestamp, so it is safe to run at any point.

## Git provenance

Every record captures what git still knows about the delivery: the rollup and
integration branch names, the rollup tip, the merge commit that landed it, the
nearest reachable tag, and `closed_at`. `show-archive` prints them.

All of it is best-effort and every field may be null — a repo with no rollup
history, with deleted branches, or with no tags archives cleanly and simply
records less. **Archiving never creates git objects**; it only reads refs.

## `archive` vs `archive-node`

Unrelated, despite the names. `archive-node --hard-remove` is a legacy
**destructive delete** that removes a node outright and refuses if anything
references it. `archive` is the reversible feature described here. Use
`archive`.

## In the PM GUI

The **Archive** button in the toolbar (next to Hide Complete) opens a drawer
that lists what is archived, offers eligible subtrees, previews a plan before
committing to it, and restores or deep-archives with one click. Eligibility is
computed server-side from the same gate the CLI uses, so the drawer never offers
something `specy-road archive` would refuse.

Two preferences under **Settings → Completed work**:

| Preference | What it does |
| ---------- | ------------ |
| Hide completed work by default | Starts each session with the Hide Complete filter on. **View filter only** — no files move. |
| Auto-archive work completed long ago | Offers completed subtrees for archiving past the day threshold. **Moves files.** |

The threshold input is the same `--older-than-days` the CLI takes, and applies
to auto-archiving only. Every write from the drawer carries the same
optimistic-concurrency token as any other PM GUI mutation, so a stale tab cannot
archive against a graph it has not seen.

## See also

- [`pm-workflow.md`](pm-workflow.md) — the PM-side roadmap commands
- [`roadmap-authoring.md`](roadmap-authoring.md) — chunks, the manifest, node fields
