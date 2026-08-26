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
specy-road list-archives              # what is archived (add --json)
specy-road show-archive <ARCHIVE_ID>  # detail, including git provenance
specy-road restore-archive <ARCHIVE_ID>
```

Nothing here commits. An archive is an ordinary roadmap change left in the
working tree; publish it the way you publish any other roadmap edit.

## What moves

```
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

Completion age currently comes from `milestone_execution.closed_at`, which only
milestones that went through a rollup carry. **Subtrees with no rollup history
have no completion timestamp yet and `--auto` will skip them**; archive those by
id. A per-node activity timestamp is coming and will close that gap.

The PM GUI exposes the same threshold as a preference.

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

## See also

- [`pm-workflow.md`](pm-workflow.md) — the PM-side roadmap commands
- [`roadmap-authoring.md`](roadmap-authoring.md) — chunks, the manifest, node fields
