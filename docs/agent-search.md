# Agent context: digest and search

A specy-road project generates far more documentation than the roadmap it
describes, and most of the volume is duplicated. On a real 48-node repo:

| | files | bytes |
| --- | ---: | ---: |
| `planning/` | 49 | 89 KB |
| `roadmap/` | 8 | 54 KB |
| `shared/` | 2 | 22 KB |
| `work/` | 24 | **458 KB** |
| `docs/` | 11 | 163 KB |

Those are on-disk bytes. `work/` is 58% of them and roughly 70% of that is a
copy: a **brief** inlines its ancestor planning sheets verbatim, and a
**pr-body** then re-inlines the whole brief. The same paragraph can appear N+1
times across a repo.

Briefs used to inline *every* `shared/*.md` on top of that, which made a
brief's size track the repository rather than the task — 436 KB for one leaf
node on a repo with 444 KB of contracts. Since 0.2.1 a brief inlines only the
contracts its planning chain cites in `## References`, plus `shared/README.md`
as the index, and lists the rest as paths. This index is what makes that safe:
nothing became unreachable, only un-inlined.

That duplication is why the search index skips briefs and pr-bodies outright —
see [What is indexed](#what-is-indexed-and-what-is-not) — regardless of what any
ignore file says.

That is what confuses an agentic IDE. Cursor indexes it and returns the same
passage from a dozen near-identical files. Claude Code builds no index but greps
into the same thicket. Meanwhile **archived** work — the material most likely to
be settled — has left the live graph and `roadmap.md` entirely, so it is either
invisible or indistinguishable from a current decision.

Two commands address that, and one ignore file makes them stick.

## `specy-road digest`

```bash
specy-road digest              # writes roadmap-context.md
specy-road digest --check      # CI drift gate
specy-road digest -o -         # stdout
```

One generated, **git-tracked** file holding the current state: the live outline
with rolled-up status, decisions already taken (with dates and ADR references),
open gates, dependencies that were added and later removed, what has been
archived, and what is claimed right now. It is a few kilobytes — a 48-node
roadmap produces about 6 KB — against the ~800 KB it stands in for.

Commit it. It is meant to be the thing your IDE indexes *instead of* the corpus.
`--check` fails if it has drifted, exactly like `specy-road export --check`,
because a stale digest is worse than none: an agent will believe it.

## `specy-road search`

```bash
specy-road search "retry backoff"
specy-road search "retry backoff" --scope archived
specy-road search M1.2                       # everything about one node
specy-road search "x" --kind planning --json
specy-road search --stats
```

Ranked, deduplicated search over planning sheets, shared contracts, governance
documents, roadmap-node prose, implementation summaries and archived work.

Output is a **pointer plus a snippet**, never file contents — enough to judge
relevance and a path to open. That is progressive disclosure: the agent pulls
the rest only if it needs it.

### What is indexed, and what is not

| Indexed | Not indexed |
| --- | --- |
| `planning/*.md` sections | `work/brief-*.md` (inlines its sources) |
| `shared/*.md`, `constitution/`, `vision.md` | the non-summary half of `work/pr-body-*.md` |
| roadmap node `title`/`goal`/`notes`/`acceptance`/`risks` | `roadmap.md` (generated from nodes) |
| `roadmap/archive/**`, including deep capsules | `docs/` |
| `work/implementation-summary-*.md` | |

A pr-body is indexed **only** when its implementation summary file is gone —
`finish-this-task` deletes the summary on landing but always keeps the pr-body,
so the pr-body is the fallback record rather than a second copy.

## How it works, and why it is built this way

### No embeddings

Anthropic replaced Claude Code's early RAG-plus-local-vector-store with agentic
search, reporting that it works better and avoids the staleness, privacy and
reliability problems a vector index brings. A roadmap corpus changes on every
commit, which is exactly where stale embeddings hurt. And the identifiers people
actually search for here — `M1.2`, `retry-queue`, a `node_key` UUID — are what
lexical matching is best at and embeddings are worst at.

The backend is SQLite **FTS5 with BM25**, from the standard library. No new
dependency. If an interpreter's SQLite was built without FTS5, search falls back
to scoring the same chunks in memory; ranking is coarser, results are still
correct. `specy-road search --stats` reports which path is active.

### Derived context, not generated context

Anthropic's Contextual Retrieval prepends an LLM-written 50–100 token summary to
each chunk before indexing, cutting top-20 retrieval failures by about half. The
LLM is there to *infer* structure from unstructured prose.

specy-road does not need it. Every planning sheet already maps to a node with an
id, title, type, codename, ancestor chain and archive state, so the same context
is **derived** — free, exact, and unable to drift from the graph:

```
M1.2 Retry queue · milestone · Complete · retry-queue · under M1 Payments · planning sheet · Approach
```

That line is indexed as its own column and weighted above the body, which is why
a search for "payments backoff" finds a section whose body never says
"payments".

### Ranking

Two ranked lists are fused with Reciprocal Rank Fusion (`1/(60+rank)`), which
needs no score normalisation between them:

- **BM25** over the chunk text, weighting context 3× and heading 5× against the
  body, since both are short and high-signal.
- **Structural** matches, where the query names a node id, codename or
  `node_key` outright. This is why `specy-road search M1.2` works without a
  separate code path.

Archived results are **demoted, not hidden** — a live sheet and the archived one
it superseded often both match, and the current one should win, but an archived
hit is frequently the *final* decision. Duplicate passages are collapsed by
content hash.

### The index is derived and disposable

It lives at `.specyrd/cache/search-index.sqlite3`, gitignored, under the same
contract as the history index: version-mismatched, corrupt or unreadable means
discard and rebuild, so **no migration for it will ever be written**. Rebuilds
are incremental — only files whose `(mtime, size)` changed are re-chunked — and
it tracks the **working tree**, not `HEAD`, so uncommitted edits are searchable
immediately. On the 48-node repo above: 296 chunks, 0.3 s cold build, ~9 ms per
query.

## Keeping it out of the IDE index

`specyrd init` maintains a marked block in two files. Everything outside the
markers is yours and is never touched; re-running changes nothing.

**`.cursorindexingignore`** — `roadmap/archive/`, `work/brief-*.md`,
`roadmap.md`.

How much this removes depends on your `.gitignore`, because an IDE index already
skips whatever git ignores. The shipped scaffold **tracks** briefs deliberately
("they document the work and belong on the feature branch"), and briefs are the
big ones — about 30 KB each. On the 48-node repo above, five tracked briefs are
147 KB against a 203 KB corpus, so excluding them takes the indexed surface from
**351 KB to 205 KB, a 42% reduction**, before archiving contributes anything.

A repo that has already added `work/brief-*.md` to its own `.gitignore` sees
almost no immediate change — its briefs were never indexed. For that repo the
block earns its keep later, once `roadmap/archive/` starts filling up. Either
way `roadmap-context.md` costs about 6 KB, so the block is close to free even
when it removes little.

The choice of file matters. `.cursorindexingignore` excludes files from Cursor's
index and search while leaving them **readable when explicitly referenced**.
`.cursorignore` would block reading too — which would break every path
`specy-road search` returns, making the search tool useless. So the policy is
*unindexed, not unreadable*.

**Claude Code has no equivalent and none is written.** There is no
`.claudeignore`, it builds no semantic index to pollute, and its
`permissions.deny` `Read()` rules would have the same pointer-breaking problem.
It is steered by `CLAUDE.md` and the `specyrd-search` command stub instead.

**`.gitignore`** — `.specyrd/cache/`. `init project` ships this rule for new
repos but skips a `.gitignore` that already exists, so a project scaffolded
before these caches existed would show them as untracked forever.

## Command stubs

`specyrd init` installs `specyrd-search`, `specyrd-digest` and `specyrd-history`
for both the `pm` and `dev` roles.

## See also

- [`roadmap-history.md`](roadmap-history.md) — what changed and when, from git
- [`archiving.md`](archiving.md) — where archived work goes
- [`pm-workflow.md`](pm-workflow.md) — the PM-side commands
