# What's new in specy-road

## Agent quickstart

**Use this doc when:** summarising a release for users, or checking what changed for an adopter upgrading.
**Not for:** the complete change list ([`CHANGELOG.md`](../CHANGELOG.md)) or how to cut a release ([`release-runbook.md`](release-runbook.md)).
**Must know:** one `## specy-road X.Y.Z` section per published version, newest first; *Upgrading* lists the breaking changes and adopter commands.

The curated, user-facing summary of each release: what you can now do, and
what to change when you upgrade. Newest first. For every change, including
fixes and internal work, see the [CHANGELOG](../CHANGELOG.md).

## specy-road 0.3.1

*Release candidate `v0.3.1-rc1`, 2026-10-28 (TestPyPI).*

0.3.1 makes specy-road a coordinator for several coding agents at once. You
keep one roadmap; specy-road decides which model should implement, which
should review, and whether a leaf may finish — and it can launch the
executor on Claude Code, Codex or Cursor and keep track of it while you work.
Upgrade if more than one agent (or more than one vendor) touches your repo,
or if you want independent review before work lands. The review gate is a
**breaking change**: read *Upgrading* first.

### Highlights

- **A review gate before finish.** A leaf finishes only when reviews from
  the models your policy names approve the exact commit under review.
  [Read more](orchestration.md)
- **Workers on other harnesses.** `worker delegate` runs a leaf's executor
  on Claude Code, Codex or Cursor in its own worktree and returns at once;
  `worker sync` shows what it did. [Read more](orchestration-workers.md)
- **Model-aware routing.** A roster of models with profiles decides who
  coordinates, executes and reviews each leaf, and writes the prompt for
  each role. [Read more](orchestration-models.md)
- **Safer shared checkouts.** A pre-tool-call guard stops destructive git
  commands while another session works in the same tree.
  [Read more](orchestration.md)
- **Brainstorm v2.** Rounds, independent panel shards, quote-checked
  evidence and cluster-first triage before ideas become roadmap nodes.
  [Read more](brainstorming.md)
- **One set of agent rules everywhere.** A managed block in `AGENTS.md`
  and `CLAUDE.md`, and skills that Claude Code, Codex and Cursor all load.
  [Read more](optional-ai-tooling-patterns.md)

### Review gate and hand-offs

An executor writes a READY hand-off; `review-packet` assembles the brief,
diff and verifier output; reviewers in fresh sessions record verdicts; the
gate counts them against `roadmap/orchestration.yaml` as committed on the
integration branch, so a feature branch cannot lower its own bar. Reviews
can be SSH-signed.

    specy-road review-packet M1.2 && specy-road handoff status M1.2

### Workers

Delegate a claimed leaf, keep working, and check in when you like. You can
send a follow-up into the worker's own session, take it over by hand, and
hand it back with your prompts recorded.

    specy-road worker delegate M1.2 --model claude-opus-5.5

### Models, roster and prompts

`init project` now scaffolds model profiles and a roster. `orchestrate
plan` staffs every ready leaf; `prompt` writes the role prompt with the
model's own rules applied.

    specy-road orchestrate plan

### Shared checkouts

`session start` records who is working where; `session guard` plugs into
Claude Code, Codex and Cursor hooks and refuses stash, hard reset, branch
switches, broad adds and forced removes while another session is live.

    specy-road session guard --format claude-code --print-config

### Brainstorm v2

Round 1 diverges without anchoring on the roadmap; later rounds and panel
shards widen it; `verify` checks each evidence quote on its page (and asks
before fetching); converge clusters ideas with critics and cited verdicts.

    specy-road brainstorm start --topic "Offline notes" --under M3 --rounds 2

### Upgrading from 0.2.x

- **The review gate.** New projects scaffold with it on
  (`require_implementation_review_before_finish: true` in
  `roadmap/git-workflow.yaml`); where it is on, `mark-implementation-reviewed`
  needs review records and `--yes` never creates one. Unattended loops must
  record an independent review first, or turn the gate off on the
  integration branch.
- **`finish-this-task` re-checks the gate at the current commit**; a 0.2.x
  approval with no review record needs a fresh `mark-implementation-reviewed`.
- **The policy comes from the integration branch**, named by the remote's
  default branch. If your clone has no `origin/HEAD`, run
  `git remote set-head origin --auto`, or the gate stays shut.
- **`review record`** refuses `--model human` and models not in the roster.
- Then run, once per repo: `specy-road upgrade --prune`. It refreshes
  schemas, profiles, skills and the managed blocks (including the
  `.gitignore` entries for `work/reviews/`, `work/.workers/`,
  `work/.worktrees/` and `work/.sessions/`), deletes the pre-0.3 command
  stubs, and validates. See
  [Upgrading from 0.2.x](install-and-usage.md#upgrading-from-02x).

### Removed

- The generic copy-paste prompts (`cleanup_prompts.md`,
  `compliance_prompts.md`, `features_changes_debuging_prompts.md`,
  `optional-agent-review-prompts.md`): use your harness's built-in review,
  cleanup and security skills; roadmap review lives in `orchestration.md`.

### Known limitations in this release candidate

- The review gate is cooperative attestation unless you require signed
  reviews: someone who can run commands in the clone that finishes (for
  example retarget `origin/HEAD`) can change what the gate reads.
- `delegate` passes an untracked implementation summary already in the
  worktree through to the worker; remove stale ones before delegating.
- The guard errs towards refusing: `echo git stash` is refused while
  another session is live.
- PM GUI: after changing the LLM key, *Test LLM* can report the old key's
  result until the server restarts; stopping `specy-road gui` can leave its
  server process on the port.

Full list of changes: [CHANGELOG](../CHANGELOG.md#v031-rc1---2026-10-28).
