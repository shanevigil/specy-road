# Work (ephemeral)

Session notes and generated briefs can live here. The roadmap graph and `shared/` contracts are the source of truth.

```bash
specy-road brief M1.1 -o work/brief-M1.1.md
```

When `roadmap/git-workflow.yaml` sets `require_implementation_review_before_finish: true`, the implementer (or agent) writes **`work/implementation-summary-<NODE_ID>.md`** before human review. Copy `implementation-summary.template.md` as a starting point. The developer then runs `specy-road mark-implementation-reviewed`, then `specy-road finish-this-task`.

Add a `.gitkeep` or tune `.gitignore` for what should stay local vs checked in.
