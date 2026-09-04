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
sheets are folded into a single **capsule** —
`roadmap/archive/deep/<archive_id>.json` — the loose files are deleted, and what
stays behind is `roadmap/archive/refs/<archive_id>.json`, a small standalone
reference naming the nodes and the git refs they were delivered on. Deep
archives are **not** browsable in the PM GUI; only their reference is.

```text
roadmap/archive/
  index.json
  deep/M0.2-e7fcdb23-20260826.json      # the only copy of the nodes
  refs/M0.2-e7fcdb23-20260826.json      # what it was, where it landed
```

The index record survives deepening with its `node_keys` and `nodes_summary`
intact, so a deep archive is still listable, still satisfies live dependencies,
and still shows its node titles — without opening the capsule.

`restore-archive` handles both tiers in one command: on a deep archive it
unfolds the capsule and then restores as usual. `deepen-archive` goes the other
way for an archive already on disk.

**The capsule checksum is verified before anything unfolds.** A capsule that
does not match the `sha256` on record is refused outright rather than partially
restored — putting silently-altered roadmap nodes back into the live graph
would be worse than failing.

### Why the capsule is not compressed

The deep tier exists to cut **file count**, not bytes. A long-running roadmap
accumulates one planning sheet per node; folding each archive into one file is
what keeps `roadmap/archive/` in hand. Compressing it would be a separate
choice, and inside a git repo it is the wrong one:

- **Git already compresses.** Every blob is zlib-compressed in the object store
  and delta-compressed against similar blobs in packfiles. A `.tar.gz` is opaque
  to that — git cannot delta it, so each version is stored in full.
- **You lose the tools.** `git diff`, `blame`, `log -p`, `git grep` and code
  search all stop working on exactly the content someone — or an agent reading
  `specy-road history` — would later want to read.
- **The savings are not there.** At roughly 500-600 bytes of chunk JSON and
  600 bytes of planning markdown per node, a 5,000-node roadmap is about 6 MB
  of text. Git does not notice that.
- **Reproducibility.** A capsule is written with canonical JSON (`indent=2`,
  sorted keys, trailing newline), so the same content produces byte-identical
  output and a stable `sha256`. Gzipped tarballs cannot: the gzip header carries
  a timestamp and tar headers carry per-file mtime, uid and gid, so re-bundling
  identical content produced a different blob and a different checksum every
  time.

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
through a rollup, and otherwise from the git-derived
[last-worked-on](#last-worked-on) date — so `--auto` reaches work that never
went through a rollup. A subtree git cannot date at all is skipped; archive
those by id.

The PM GUI exposes the same threshold as a preference.

## Last-worked-on

The PM GUI shows a **Last worked** column on leaf rows, answering "when did
anything about this item last change?".

It is **derived from git history, never stored.** There is no sidecar file to
create, seed, commit, or migrate — which means an existing repo is fully
populated the first time you open it, with no setup step of any kind.

Per node, in order:

1. **Planning sheet** — the last commit touching the node's `planning_dir`.
   Per-node and precise; this is the answer you normally see.
2. **Roadmap chunk** — used *only* when the sheet has never been committed.

The two are deliberately **not** blended. A chunk holds many nodes, so
crediting its commit date to all of them would make every sibling look freshly
worked the moment one node's status changed — destroying exactly the staleness
signal the column exists to give.

Merge commits do not count as a touch. A merge that only carries someone
else's edit across is not the moment the node was worked on, and counting it
would make the whole roadmap look freshly touched after every integration
merge.

**It reflects committed work only**, so it is a lower bound: work in progress
that has not been committed yet still shows its previous commit. The **Dev**
column and `roadmap/registry.yaml` are what show active claims.

### Cost

One `git log --name-only` walk for the whole roadmap, memoized on `HEAD` —
commit dates cannot change while `HEAD` is still, so the cache is exact rather
than a timeout guess. Asking git per node instead is linear in node count and
was the reason a stored sidecar looked necessary at all: on a 400-node roadmap
that is ~31s against ~0.17s for a single walk.

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

## Archived work stays visible in history

Archiving takes a subtree out of the live graph and out of `roadmap.md`, so
nothing in the current roadmap says it ever existed. `roadmap/archive/index.json`
records it, and [`specy-road history`](roadmap-history.md) reads that ledger
alongside the graph:

```bash
specy-road history --archived        # everything that has left the live graph
specy-road history M0.2              # an archived node is still addressable by id
```

Every brief's `## 9. History` section names archived work on the same branch of
the outline, which is how an agent learns that a phase used to be bigger rather
than assuming the area was never built.

## See also

- [`roadmap-history.md`](roadmap-history.md) — how the roadmap got here, derived from git
- [`agent-search.md`](agent-search.md) — searching archived work that is hidden from IDE indexing
- [`pm-workflow.md`](pm-workflow.md) — the PM-side roadmap commands
- [`roadmap-authoring.md`](roadmap-authoring.md) — chunks, the manifest, node fields
