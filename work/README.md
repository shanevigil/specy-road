# Work (ephemeral)

Session notes, scratchpads, and generated briefs can live here. **Not** the source of truth — the roadmap and `shared/` contracts are.

Suggested pattern (`M1.1` is the node’s **display `id`**; the same id works for `specy-road brief`):

```bash
specy-road brief M1.1 -o work/brief-M1.1.md
```

**Closing a task:** By default, **`specy-road finish-this-task`** deletes the toolkit session files for that node after a successful validate/export: `work/brief-<NODE_ID>.md`, `work/prompt-<NODE_ID>.md`, and `work/implementation-summary-<NODE_ID>.md` (if present). Tracked copies are removed and the deletion is staged in the same bookkeeping commit. Planning sheets under `planning/` are unchanged. Skip removal with **`specy-road finish-this-task --no-cleanup-work`** or set **`cleanup_work_artifacts_on_finish: false`** in `roadmap/git-workflow.yaml`.

**Git:** The repository `.gitignore` ignores everything under `work/` except this file and [`.gitkeep`](.gitkeep), so scratch files stay local by default. To track a specific file (for example a checked-in example brief), add an exception in `.gitignore` (e.g. `!work/example-brief.md`) and commit that path intentionally.
