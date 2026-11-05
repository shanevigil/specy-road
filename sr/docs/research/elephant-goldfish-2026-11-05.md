# Elephant-Goldfish Model (EGM): research and buy-vs-build (2026-11-05)

Requested by the maintainer as a harness-landscape item. Sources: the Google Open Source blog post,
the `google/elephant-goldfish-model` repository (shallow clone of `main` at `0dfb5bf`, 2026-11-04,
read as data only; nothing installed or run), and its docs. Dave Rensin's originating essay returned
HTTP 403 and was **not read**; anything attributed to it below comes from the blog or README.

## 1. What it is

**"Model" means a working method, not an ML model or a memory store.** EGM is a set of Markdown
skills and reviewer personas that a coding agent follows. It runs on the host harness's own models
and subagent tool. It has no runtime code, no service, and no persistent memory of its own.

The pattern (blog post, https://opensource.googleblog.com/2026/10/introducing-elephant-goldfish-model-plugin.html):

- **Elephant.** One long, context-rich session co-designs with the developer under a "No Code"
  rule, then drafts a Markdown design doc. The doc covers the problem, the plan, the alternatives
  considered, and a file-level implementation plan.
- **Goldfish.** Fresh, zero-history subagents review that doc. The README says they examine "the
  draft and referenced source material without the earlier conversation, helping expose unstated
  assumptions and blind spots".
- **Human.** The developer resolves trade-offs and approves before any implementation.
- The blog's thesis is "Design is the new code." Its stated goal is "for the AI to correctly produce
  the code you wanted the first time after you press Enter."

**Skills** (`skills/*/SKILL.md`, about 1,900 lines in total):

- `egm-brainstorm`: co-design, with fresh critics, ending in `concepts_brief.md`.
- `egm-draft`: section-by-section drafting of `design_draft.md`, with a human gate after each
  section.
- `egm-review`: five sequential stages (Zoom Out, Comprehension, Design Critique, Intermediate Zoom
  Out, Implementation Readiness), each run by fresh reviewer personas.
- `egm-resolve`: the Elephant sorts each finding into CONTEST, ESCALATE, PROPOSE FIX or DECLINE.
- `egm-review-loop`: a configurable group of reviewers.
- `egm-bootstrap`: writes README "contracts" across a source tree.
- `egm-drift-report`: compares the design docs with the code.

**Personas.** Nine personas live in `agents/*.md`. The Claude adapters in
`.claude-plugin/agents/` set `tools: [Read, Grep, Glob]` and `omitClaudeMd: true`.

**Packaging and licence.** Apache-2.0, and "not an officially supported Google product" (README).
`plugin.json` is at version 0.1.0. The only release is `v0.1.0` (2026-10-27).

**Install surfaces.** Install commands come from `docs/harnesses.md`:

- Antigravity CLI: `agy plugin install …`
- Claude Code: `claude plugin marketplace add google/elephant-goldfish-model && claude plugin install egm@egm`
- Codex: `codex plugin marketplace add … && codex plugin add egm@egm`
- Also: Claude Cowork, ChatGPT, omp and Muse, plus GitHub Copilot agent files.
- **Cursor: experimental and unverified.** `docs/cursor.md` says "Installation, workflow, and
  isolation remain unverified."

Two points correct the blog:

- The blog reportedly names only Antigravity and calls other environments "upcoming". The repository
  has moved past that: Claude Code and Codex pass its own installation and end-to-end fixtures
  (`TESTING.md`, harness test record).
- I read the blog through a summarising fetch, so treat its wording as paraphrase except for the
  three quotes above.

**How it is invoked.** It runs only interactively. In Claude Code the commands take the plugin
prefix: `/egm:egm-brainstorm`, `/egm:egm-draft`, `/egm:egm-review <doc>`.

- The skills set `disable-model-invocation: true`, so an agent cannot auto-invoke them, and
  `docs/claude.md` says the `Skill` tool refuses them.
- The skills require "ONE QUESTION AT A TIME" and explicit consensus gates.
- Headless runs are possible but awkward. Claude Code needs hand-written `Read(...)` permission rules
  for the plugin cache. Link approvals fall back to "leave them all out" when no one can answer.

**Maturity and evidence.**

- The repository was created 2026-09-13. It has about 12.4k stars, 891 forks, 68 open issues and 29
  contributors (GitHub API, 2026-11-05). It is active (last push 2026-11-04).
- Usage claim: "Thousands of Googlers use this plugin every day to ship production Google code"
  (blog; also in the README). **Unverified**, and there is no data behind it.
- **No benchmarks, no paper, and no measured outcomes.** `TESTING.md` records workflow fixtures
  ("did the stages run, in order, with fresh reviewers"), not design quality or defect rates.
- Its own isolation findings matter to specy-road (`docs/harnesses.md`, issue #237):
  - **Codex CLI 0.166.0 put project and user `AGENTS.md` into "fresh" subagents** despite
    `fork_turns: "none"`.
  - Antigravity did the same with `AGENTS.md` and `GEMINI.md`.
  - Only Claude Code's `omitClaudeMd` is a verified exclusion control.

## 2. Relevance to specy-road

specy-road already uses the Goldfish half of the pattern: specy-road's review gate is a Goldfish
gate.

- Reviewers are fresh sessions reading a branch they did not write (`docs/orchestration-review.md`).
  Their records carry `fresh_session`, and Claude reviewers run `--bare`, which skips CLAUDE.md,
  hooks and MCP.
- Panel shards in `docs/brainstorming.md` are told not to read each other, because "workers that see
  each other converge".
- The coordinator plays the Elephant in both cases.

So EGM confirms the design rather than filling a gap.

| specy-road problem | Does EGM address it? |
|---|---|
| Context or memory across sessions and fix rounds (briefs, `roadmap-context.md` digest, start-up reading budget) | **No.** EGM has no memory mechanism. The Elephant is just a long session, and its "memory" is the host transcript. Briefs and the digest solve a problem EGM does not touch. |
| Review rounds that re-discover findings | **Partly, as a pattern.** `egm-resolve` makes the author classify every finding, and a CONTEST must cite evidence the reviewer could read. specy-road already has delta review, `--rework` carry-over (M18.15) and project review lessons. |
| Reviewer consistency and leniency | **Partly.** The personas use anti-sycophancy rules ("Never agree by default", "No Glazing"). specy-road's "not a defect because" rule is stricter: it is enforced structurally by `review record`, where EGM only writes it into prompts. |
| **Spec quality before implementation** | **Yes. This is the real gap.** specy-road reviews code after implementation. The planning sheet and brief get no fresh-context, multi-lens review before an executor starts. The only spec review is the optional single-pass `review-node` / PM GUI LLM Review. EGM's Comprehension ("paraphrase first, or it is a Blocker") and Implementation Readiness checks target exactly the failures that M18.12 and M18.13 chase: acceptance text a reviewer reads in the leaf's favour, and touch zones that miss what acceptance needs. |
| Doc/code drift | Weakly. `egm-drift-report` is one prompt with no deterministic check. specy-road's `export --check`, `digest --check` and touch-zone checks are stronger where they apply. |
| Long-running workers, leases, cost | No. EGM is interactive and single-session, and adds model spend (9 to 16 reviewer subagents per review in the recorded fixtures). |
| Reviewer isolation evidence | **Yes, and useful.** Issue #237 says Codex (and Antigravity) fresh subagents still load `AGENTS.md`. `fresh_session` is self-attested, so a Codex reviewer that says `fresh_session: true` may still have read the leaf's edited `AGENTS.md`. That is the same branch-runs-into-reviewer concern behind `--bare`. **Not verified against specy-road's codex reviewer command** (`codex exec`, not subagents); worth a probe. |

## 3. Buy vs build

Scores are 1 to 5 (5 is best for specy-road).

| Criterion | Score | Notes |
|---|---|---|
| Fit with constraints | 3 | It never calls an LLM itself and runs inside the user's harness on their subscription, which fits. Its interactive gates do not fit unattended workers or the gate's machine-readable records. |
| Licence | 5 | Apache-2.0, compatible with everything. |
| Maturity and maintenance | 2 | 0.1.0 and pre-1.0 ("Version 1.0 requires a stable contract for skill names, parameters, output paths, and report formats"). It is about 7 weeks old but very active. There is no outcome evidence. |
| Dependency weight and supply chain | 4 as an optional user plugin; 1 as a specy-road dependency | It has no runtime packages. It is still **prompt supply chain**: `marketplace.json` uses `"source": "./"`, so a marketplace install tracks the default branch rather than a tag. Pinning to a tag or commit would need to be done by the user, and I did not verify whether each harness supports it. |
| Local and offline | 4 | Files only. It uses the host's models; no EGM service or telemetry (`docs/privacy.md`). |
| Coverage of specy-road's problem | 2 | It covers design-doc review only. It does nothing for memory, digests, workers, leases or the gate. |
| Integration effort | 3 | Recommending it costs about one doc paragraph. Wiring it into planning-sheet review means mapping our sheet format to its `## Implementation Plan` split and its output files. |
| Optionality | 5 | It is a harness plugin that a user installs or removes, and specy-road never needs to know. |

**Verdict: borrow the pattern, and integrate it optionally as a documented recommendation. Do not
adopt it.**

- Do not depend on it, vendor its prompts, or launch its skills from `specy-road`. Its skills cannot
  be model-invoked, are interactive, and are pre-1.0.
- In `docs/optional-ai-tooling-patterns.md`, mention it as an optional plugin for designing large
  leaves before `promote`. Include the caveats: interactive only, pin a version, and Cursor is
  unverified.
- Borrow three things:
  - a fresh-context **spec** review before claim;
  - the "paraphrase first" comprehension test;
  - CONTEST-must-cite-readable-evidence for coordinator rebuttals.

**Harness-landscape triggers: none fires.** EGM does not drive CLIs, report usage, or replace
launch, resume or parse. No vendor CLI mode changed. It is a watchlist entry, not a reopening of
buy vs build.

## 4. Candidate roadmap items

1. **M18: Fresh-context spec review before claim.** Add an opt-in policy, for example
   `policy.spec_review` keyed by sensitivity or touch zone. Before a leaf can be claimed by a worker,
   one or two rostered reviewers in fresh, bare sessions read only the brief and its cited contracts.
   They then:
   - paraphrase what the leaf asks for;
   - report each acceptance item they cannot paraphrase, and each touch-zone gap;
   - file a `SPEC-REVIEW-<model>.md` that `orchestrate plan` reads.

   This reuses `review delegate` launch and filing, so no new entrypoint is needed. It complements
   M18.12 and M18.13, which are deterministic, with a reader test. Acceptance: a deliberately vague
   fixture leaf is flagged, and a clear one passes.
2. **M18 or M20: Probe instruction-file leakage into "fresh" reviewers per harness.** Add a
   harness-facts check, extending M18.2, that plants a marker in the worktree's `AGENTS.md` and
   `CLAUDE.md` and asks the reviewer command whether it saw it. Record the result per harness and CLI
   version. Then `handoff status` warns when a reviewer claims `fresh_session: true` on a harness
   known to leak. Motivated by EGM issue #237 (Codex 0.166.0, Antigravity).
3. **M19 (small, docs only): Mention EGM in `docs/optional-ai-tooling-patterns.md`.** Say where it
   fits: before `brainstorm promote` or before writing a large planning sheet, never inside workers.
   Add the version-pinning caveat.

**Watchlist line** for `sr/docs/research/harness-landscape.md`:

| Entry | What it is | Watch for |
|---|---|---|
| Elephant-Goldfish Model (EGM) | Google's Apache-2.0 plugin of Markdown skills: design in one long session, review with fresh-context subagent personas; Claude Code, Codex, Antigravity (Cursor experimental) | 1.0 contract for skill names and report formats; a non-interactive or headless review mode; outcome evidence beyond "thousands of Googlers"; host fixes for instruction-file leakage into fresh subagents (issue #237); pinned or tagged marketplace installs |

## 5. Evidence quality

**Strong** (repository files read directly):

- skill and persona content;
- licence and version;
- harness list and verification status;
- isolation caveats;
- unpinned marketplace source.

**Medium:**

- blog wording, read through a summarising fetch;
- GitHub counts as of 2026-11-05.

**Unverified:**

- Google internal usage claim;
- any effect on defect rates;
- Rensin essay content (403);
- whether issue #237's Codex leak applies to `codex exec` as specy-road launches it;
- whether each harness's marketplace supports pinning a ref.
