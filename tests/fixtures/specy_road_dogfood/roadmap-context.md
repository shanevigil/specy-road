# Roadmap context

<!-- specy-road: generated context digest — do not edit by hand. Regenerate with `specy-road digest`. -->

The current state of this project's roadmap, generated from the merged graph, the archive ledger and git history. Read this before crawling `planning/` or `work/` — it is the authoritative summary, and those directories contain a great deal of duplicated text.

## Live roadmap

Status is the computed rollup: a non-leaf is Complete only when every leaf descendant is.

- `M0` Foundation — architecture and contracts — phase — **Not Started**
  - `M0.1` Establish shared contracts and ADR skeleton `contracts-bootstrap` — milestone — **Complete**
  - `M0.2` Roadmap validator in CI `roadmap-ci` — milestone — **Not Started**
  - `M0.3` Define API contract outline in shared/ `api-contract-outline` — task — **Complete**
- `M1` Implementation track — phase — **Not Started**
- `M2` testing `testing` — task — **Not Started**

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
