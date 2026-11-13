# Work (ephemeral)

Session notes and generated briefs can live here. The roadmap graph and `shared/` contracts are the source of truth.

**Everything here is gitignored by default** (`work/*` in the managed `.gitignore` block): briefs, implementation summaries, prompts, brainstorm sessions, chore records, review hand-offs, run state and the `work/done/` archive. This `README.md`, `.gitkeep` and the top-level `*.template.md` files stay tracked as scaffold. A project may re-include other paths (`!work/worker-logs/`, `!work/done/`) after the block. Files already tracked under `work/` stay tracked until you run the `git rm --cached` command `specy-road upgrade` prints.

```bash
specy-road brief M1.1 -o work/brief-M1.1.md
```

When `roadmap/git-workflow.yaml` sets `require_implementation_review_before_finish: true`, the implementer (or agent) writes **`work/implementation-summary-<NODE_ID>.md`** before review. It is local by default (`implementation_summary: local`): the review packet reads it from the leaf's worktree, and a reviewer in another clone does not see the summary. Copy `implementation-summary.template.md` as a starting point. Review hand-offs live under **`work/reviews/<NODE_ID>/`** (gitignored): the executor's `READY-<agent>.md` (`specy-road ready <NODE_ID> --model <id> --run '<cmd>'`, which records each verifier's exit and output tail; or copy `handoff-ready.template.md`, which can also carry `blocked_on`), the `PACKET.md` reviewers read (`specy-road review packet`), and one `REVIEW-<model>.md` per reviewer (`specy-road review record`, from `review-record.template.md`). The developer then runs `specy-road mark-implementation-reviewed`, then `specy-road finish-this-task`. See `docs/orchestration.md` in the specy-road repository.

By default, **`finish-this-task`** removes **`work/brief-<NODE_ID>.md`**, **`work/prompt-<NODE_ID>.md`**, and **`work/implementation-summary-<NODE_ID>.md`** after validate/export/digest (staging deletion if a project still tracks those paths). Durable design stays in **`planning/`** and cited **`shared/`** contracts. Use **`--no-cleanup-work`** or **`cleanup_work_artifacts_on_finish: false`** in `roadmap/git-workflow.yaml` to keep those three.

Two files do not follow that switch. **`work/.on-complete-<NODE_ID>.yaml`** is internal handoff state rather than a document, so it always goes. **`work/pr-body-<NODE_ID>.md`** always stays: it is the snapshot the printed `gh pr create --body-file` command reads, and nothing tells `finish-this-task` when the PR was opened. Both are gitignored, and `specy-road file-limits` skips every file in this list.

**Brainstorm sessions** live here too: `work/brainstorm-<slug>.yaml` holds the ideas, frame, clusters, evidence and decisions; the prompts beside it, one per pass (`…-r1-prompt.md`, `…-r2-prompt.md`, `…-r1-sN-prompt.md`, `…-recommend-prompt.md`, `…-evidence-prompt.md`), are regenerated. Both are gitignored; re-include `work/brainstorm-*.yaml` after the block to keep sessions in git.

**Agent coordination state** (all gitignored, always in the main worktree): `work/.sessions/<agent>.yaml` presence records (`specy-road session`), `work/.workers/` worker records, event logs and the ops outbox (`specy-road worker`), and `work/.worktrees/` for leaves a worker runs in a linked worktree.

**Worker logs in git** are opt-in: with `track_worker_logs: "events"` in `roadmap/git-workflow.yaml`, each worker's event log is also copied, at the end of each turn, to **`work/worker-logs/<NODE_ID>/<worker id>.events.jsonl`** in the worker's checkout (`"full"` adds the raw `<worker id>.log`), and `finish-this-task` commits that directory with the leaf. Under the default `"off"`, logs live only in `work/.workers/`. If you opt in, re-include it with a `!work/worker-logs/` line after the managed block.

