## Intent

Fix what three adopters hit when they upgraded to 0.3.1rc3 and ground leaves with several harnesses: an RC install recipe that breaks with extras, Claude Code reviewers that cannot run on a subscription login, a `prompt --channel cli` path that launched an unrostered reviewer whose verdict counted, bookkeeping conflicts in every parallel PR-mode leaf, workers that took over the author's screen or changed shared services, a rework prompt that dropped the accepted root-cause analysis, a measurement change that failed file-limits silently, and promoted leaves that pickup could never take. Lower-priority items remove setup and loop friction: roster setup and trial, chore parity, worker sync, review packet and record friction, acceptance evidence classes and project preferences.

## Approach

- **Order.** Siblings follow the adopters' priorities: M15.1 (RC install with extras), M15.2 (subscription reviewers), M15.3 (prompt-channel safety), M15.4 (parallel PR bookkeeping), M15.5 (host effects), M15.6 (rework carries the RCA), M15.7 (file-limits baseline), M15.8 (promoted leaves never stuck); then the rest.
- **M8.3 first where it overlaps.** M8.3 (in review) already makes reviewer runs read-only, files the record from structured output, gives cursor reviewers `--mode ask --trust` without `--force`, and routes a claude-code/codex/cursor reviewer without `channels.cli` to the adapter's command with the rostered model. It still launches Claude Code reviewers `--bare` (subscription logins fail), still puts the cursor prompt on the command line (E2BIG over 128 KiB), still launches on `prompt --channel cli` without an explicit run flag, runs from the invoking checkout, and never compares the harness-reported model. M15.2, M15.3, M15.9 and the other leaves touching the same files depend on M8.3.
- **Existing leaves took the rest.** M13.8 (stale registration guidance, including this toolkit's own `docs/roadmap-authoring.md`), M13.9 (CLAUDE.md import via upgrade, team-file wording), M13.12 (duplicate ignore patterns, repeated context warnings), M13.13 (the hand-written upgrade prompt as baseline), M14.5 (what the evidence would not catch), M12.5 (session records, merged worktrees, `--delete-branch`), M14.6 (notes per round), M14.9 (plan-time no-analyst warning).
- Every file within about 30 lines of the 400-line cap is paired with a new sibling module or doc in its leaf's zones.
- **Themed-milestone restructure (maintainer, 2026-11-05).** M15 takes no new leaves; rc4 fixes from now on go into M16's feedback-and-fix intake (M16.65), not M15. M15 stays open until its in-flight leaves land (M15.2, M15.3, M15.32, M15.33, M15.34, M15.36, M15.37, M15.38, M15.39, M15.40), then is set Complete and archived. Its not-started leaves go to M18 (M15.5, M15.16, M15.20, M15.25, M15.28, M15.29, M15.30) or M19 (M15.7, M15.14).

## Tasks / checklist

- [ ] M15.1 — RC install docs: extras, direct wheel URL, never TestPyPI as an index; runbook announcement line.
- [ ] M15.2 — Claude Code reviewer: bare only with a key, explicit mode otherwise, preflight and plan notice.
- [ ] M15.3 — `prompt --channel cli` launches only with `--run`; roster model, leaf worktree, model check.
- [ ] M15.4 — `reconcile-branch` for parallel PR-mode leaves; pickup's register commit regenerates the digest.
- [ ] M15.5 — `policy.host_effects`, guard deny-list, protected services, `worker message --interrupt`.
- [ ] M15.6 — Rework prompt carries the accepted RCA as the governing design.
- [ ] M15.7 — `file-limits --write-baseline`, pointer line, upgrade's file-limits count.
- [ ] M15.8 — Promote placeholder and `author-approach`.
- [ ] M15.9 — Prompts never on argv; harness binary resolution.
- [ ] M15.10 — Roster dry-run from the worktree; local roster entries; models list diff.
- [ ] M15.11 — Roster generator, local profile validation, consistent ids, coordinator line, `--spread`.
- [ ] M15.12 — Shared doc zones do not serialize batches.
- [ ] M15.13 — `sync --until`, collapsed tool-use events, rework after completion, READY-only resume, quieter pickup hint.
- [ ] M15.14 — Chore parity.
- [ ] M15.15 — upgrade ships work/ templates; README step list.
- [ ] M15.16 — `observed(...)` acceptance and coordinator probes.
- [ ] M15.17 — Review packet and record friction.
- [ ] M15.18 — `planned_test_changes` editable; unplanned removals a required check.
- [ ] M15.19 — Cursor display-name cost.
- [ ] M15.20 — Zone coverage warning; brief importer cap.
- [ ] M15.21 — Linked worktree root; symlinked environments.
- [ ] M15.22 — Local decisions, PR footer, summary rule, root local landing.
- Out of scope: version numbers and release notes (human-owned), and any adopter-specific names.

## References

- Roadmap chunk for `M15` (`roadmap/phases/M15.json`)
- M8.3's planning sheet and `docs/orchestration-reviewer-output.md` (read-only reviewer runs)
- `docs/orchestration.md`, `docs/orchestration-review.md`, `docs/orchestration-workers.md`, `docs/install-and-usage.md`
- No `shared/` contract applies.
