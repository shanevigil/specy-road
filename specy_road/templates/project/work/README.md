# Work (ephemeral)

Session notes and generated briefs can live here. The roadmap graph and `shared/` contracts are the source of truth.

```bash
specy-road brief M1.1 -o work/brief-M1.1.md
```

When `roadmap/git-workflow.yaml` sets `require_implementation_review_before_finish: true`, the implementer (or agent) writes **`work/implementation-summary-<NODE_ID>.md`** before human review. Copy `implementation-summary.template.md` as a starting point. The developer then runs `specy-road mark-implementation-reviewed`, then `specy-road finish-this-task`.

By default, **`finish-this-task`** removes **`work/brief-<NODE_ID>.md`**, **`work/prompt-<NODE_ID>.md`**, and **`work/implementation-summary-<NODE_ID>.md`** after validate/export (staging deletion if those paths are tracked). Durable design stays in **`planning/`** and cited **`shared/`** contracts. Use **`--no-cleanup-work`** or **`cleanup_work_artifacts_on_finish: false`** in `roadmap/git-workflow.yaml` to keep those three.

Two files do not follow that switch. **`work/.on-complete-<NODE_ID>.yaml`** is internal handoff state rather than a document, so it always goes. **`work/pr-body-<NODE_ID>.md`** always stays: it is the snapshot the printed `gh pr create --body-file` command reads, and nothing tells `finish-this-task` when the PR was opened. Both are gitignored by the scaffold, and `specy-road file-limits` skips every file in this list.

Add a `.gitkeep` or tune `.gitignore` for what should stay local vs checked in.
