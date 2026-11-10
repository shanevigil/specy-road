## Intent

Field feedback on the 0.3.1 release candidates that does not block 0.3.1, handled after it ships (maintainer decision 2026-11-06). Findings are written as specy-road behaviour only. Leaves are added here during triage.

## Approach

Constraints, major steps, and how you will verify done.

## Tasks / checklist

Write each acceptance criterion on the node to the acceptance criteria checklist (see `planning/README.md`): state what is out of scope, bound concurrency and input classes, and name the observable check.

- [ ] …

## References

- Roadmap chunk for `M23`
- Add one line per contract this node conforms to, naming its path under
  `shared/`. `specy-road brief` inlines exactly the ones named here and lists
  the rest as paths, so a bare `shared/` cites nothing. Find one with
  `specy-road search "<query>" --kind shared`. Do not leave an example path in
  this section — anything matching a real file under `shared/` counts as a
  citation, including inside a comment or a code fence.

## Intake: adopter field report on rc4 (maintainer approved, 2026-11-09)

From the sanitized field report and its triage; items 7, 13–15, 17, 19 and 21–23(a) became RC5 leaves. The rest are post-0.3.1:

- Presence across sibling clones (session list, doctor) and a safer `doctor --fix` for claims living in other clones (items 1–2).
- `orchestrate plan` shows a preference conflict on the leaf's own line, and warns on a guidance-bypass model even with signed_reviews off (item 3).
- `decisions close`: strip a repeated id; `--record` writes the sheet line and scaffolds the section (item 4).
- Local and shared decision ids in one numbering, or a local prefix; `list` shows shadowing (item 5).
- The policy pin digests only verdict-relevant roster fields (item 6); `doctor` or `handoff status` shows which claims are pinned (item 12).
- Session ids derived from the harness session when a harness marker is set (item 8).
- Cursor runtime model-name alias: name the context-size mismatch and its alias fix; ship the alias (item 10).
- `worker sync --wait --until completion` blocks until the state leaves running, or says why it returned (item 11).
- An idle worker whose leaf is escalated or waiting on a human frees its slot; a built-in watcher for stalled workers (item 13 remainder).
- `chore start --base <commit>` (item 16); `ready` accepts a chore slug (item 18).
- An authorized rerun carries a round count and escalates again when it runs out (item 20).
- A writable temp root for Codex reviewers, with the write check after the run (item 21 remainder); `review record` reads notes from stdin (item 23b).
- The chore reviewer prompt (`chore_cli.chore_prompt`) says `A1` is the task as a whole, given pass or fail, with no other `A#` key; a chore record with only `A1` is still read by the chore verdicts (item 23a, moved out of M22.64).
- A schema-valid verdict from a reviewer attempt that exited non-zero or logged an error is filed today; decide how such a verdict is treated on both filing paths (`review delegate` and `prompt --run`). Mitigation first and bounded (maintainer, 2026-11-09): flag or refuse the observable failed-attempt shapes and document the residual limit; it is not meant to close every stop or denial shape, so it does not chase a non-converging target.

## Intake: adopter feedback part 2 on rc4 (maintainer approved, 2026-11-09)

- `mark-implementation-reviewed` checks for a clean tree before the menu or any record, on both the leaf and milestone paths; `handoff status` says "review recorded; approval not committed" when the gate is met but the registry is not; the `finish-this-task` refusal names the missing half; the clean-tree refusal stops advising stash or discard (finding 29).
- The release runbook's CHANGELOG template says "sha256: see the GitHub release" instead of a placeholder that is never filled in (finding 31).
- `upgrade` and `refresh-stubs` report `added` separately from `replaced` for a managed block, and `--dry-run` shows the block text; the upgrade notes say a `CLAUDE.md` without a block gets one (finding 32).
- The full-review notice names the node's type, or the docs say any node with leaf children is reviewed as a milestone; `upgrade --dry-run` skips or rewords the integration-branch remote-refs line in its scratch copy (finding 33).
- `doctor` and `handoff status` offer `abort-task-pickup` for an unattended claim only "if nobody is working on it", and note that a person working by hand leaves no session record (finding 35).
- The dotted-model-id roster warning is skipped when the entry's `channels.cli` does not use `{model}` (finding 36).
- The human eligibility hint prints the leaf form of `mark-implementation-reviewed`, with no id and run from the feature branch, for a leaf (finding 37).
- The milestone full-review menu lists the leaves it covers, with their landing commits and a diffstat, or points at `review-packet`; `[w]` shows only when there is a walkthrough (finding 38).
- The milestone full review prints the push hint pickup prints after its integration-branch commit (finding 39).
