# Work (ephemeral)

Session notes, scratchpads, and generated briefs can live here. **Not** the source of truth — the roadmap and `shared/` contracts are.

Suggested pattern (`M1.1` is the node’s **display `id`**; the same id works for `specy-road brief`):

```bash
specy-road brief M1.1 -o work/brief-M1.1.md
```

**Git:** The repository `.gitignore` ignores everything under `work/` except this file and [`.gitkeep`](.gitkeep), so scratch files stay local by default. To track a specific file (for example a checked-in example brief), add an exception in `.gitignore` (e.g. `!work/example-brief.md`) and commit that path intentionally.
