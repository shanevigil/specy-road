# Implementation summary: M22.15 — sandbox runbook states rc4's real results

## Touch zones (confirmed)

The brief's call-site scan found no Python importers. The only file this leaf changes is the runbook. `tests/test_doc_links.py` checks links in the shipped templates, not these sentences, so it stays outside the zones.

Final touch zones: `docs/agentic-sandbox-runbook.md`.

## Change

Text only, at the four places the rc4 run contradicted. Product behaviour is unchanged.

- §1.1: `export --check` and `digest --check` exit 0 right after `init project`, which writes `roadmap.md` and `roadmap-context.md`. The "exit 1 with `missing`" sentence and the extra `export` / `digest` step are gone.
- §2.6: tampering lists three outcomes — a front-matter value byte (`signature does not verify for <model>`), a notes-body byte (`notes body does not match notes_sha256`), a schema-breaking edit such as an `A1` value (schema-invalid) — and restoring the record makes the gate met again.
- §4.1: `models list` shows C/E/R scores and a trailing `stale` marker on a stale profile's line. `models stale` lists the reasons and exits 1 for a rostered profile whose `researched` date is a fixed date more than 180 days ago; `models show <id>` prints them. With no such profile, `models stale` exits 0.
- §5: where the runbook says "Claim two leaves", the second claim from one checkout is `do-next-available-task --allow-second-claim` (exit 6 without it).

Net change in `docs/agentic-sandbox-runbook.md`: +2 lines (14 insertions, 12 deletions). A5's estimate of about +6 is informational.

`pytest tests/test_doc_links.py -q`: 4 passed.

## Added

### Helpers

- none

### Branches or guards

- none

### Mocks

- none

### Tests

- none — docs only; the brief names the existing link check and asks for no new test.
