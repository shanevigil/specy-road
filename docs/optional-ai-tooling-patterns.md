# Optional AI tooling patterns

## Agent quickstart

**Use this doc when:** you are deciding how to layer a coding harness (Claude Code, Cursor, Codex) on a specy-road project — entry files, rules, hooks, worktrees — beyond what the CLI installs.
**Not for:** the review contract and shared-checkout rules themselves ([`orchestration.md`](orchestration.md)) or the branch and registry contract ([`git-workflow.md`](git-workflow.md)).

**Must know without reading on:**
- Nothing here is part of the specy-road contract; the canonical invocations are `specy-road validate|brief|export|file-limits`, and tracked docs win over any harness memory or rule.
- `specyrd init [PATH] --ai cursor|claude-code|codex|generic` installs one skill per command under `.agents/skills/<name>/SKILL.md` plus managed blocks in `.gitignore`, `.cursorindexingignore` and `CLAUDE.md`; `specy-road init project` keeps the specy-road section of `AGENTS.md`. Upgrade with `specy-road refresh-stubs`, not `init --force`.
- Hooks are not installed for you: `specy-road session guard --format claude-code|codex|cursor --print-config` prints the shared-checkout guard snippet, `specy-road worker hook --format … --print-config` the intervention witness.
- specy-road ships no MCP server; agents reach it through the skills and the CLI.

**Read further for:**
- what the CLI writes and what `--force` may touch → "Optional: `specyrd init` (install-time IDE commands)"
- the principles behind docs-as-source-of-truth and the five layers → "Core idea: documentation as source of truth", "Optional “five layers” (product repos)"
- entry files, rule files, app-repo docs, gates, MCP → "Optional: `CLAUDE.md` or equivalent entry file", "Optional: Cursor (or IDE) rules", "Optional: `docs/` in an application repository", "Optional: verification gates", "Optional: MCP servers"
- the per-harness hook snippets and their verified caveats → "Optional: a shared-checkout guard hook"
- worktrees, prompt habits, checklists → "Optional: git worktrees for parallel agents", "Optional: prompt habits", "Checklists (adapt to your repo)"

**Related:** [`orchestration.md`](orchestration.md), [`git-workflow.md`](git-workflow.md), [`install-and-usage.md`](install-and-usage.md), [`philosophy-and-scope.md`](philosophy-and-scope.md).

**This document is not part of specy-road’s core contract.** It collects patterns some teams use when layering **coding agents** (Claude Code, Cursor, Copilot, etc.) on top of a product repository. You may adopt none, some, or all of them.

Consumer projects coordinate through their own [`roadmap/registry.yaml`](git-workflow.md) after `specy-road init project`. In this toolkit repository, [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](../tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) belongs to the dogfood test fixture only; it is not the canonical toolkit product roadmap. Some application repos use a markdown table such as `docs/roadmap-status.md` instead—that is a **team convention**, not what specy-road requires by default.

---

## Optional: `specyrd init` (install-time IDE commands)

The **`specyrd`** CLI (installed with this package) lays down **thin** markdown skills that tell the agent to run **`specy-road`** from the repo root — they are not a second source of truth. Each command is **one file**, `.agents/skills/<name>/SKILL.md`: Cursor and Codex read that directory natively, and the `claude-code` pack adds a symlink per skill under `.claude/skills/` so Claude Code reads the same file. `--ai generic` writes flat `.md` files into a directory you choose.

- **CLI-first:** Canonical invocations remain `specy-road validate|brief|export|file-limits`.
- **No Spec Kit collision:** `specyrd` is not the Spec Kit `specify` CLI. **specy-road** uses flat **`planning/*.md`** feature sheets per node — not that tool.
- **Second IDE later:** Run `specyrd init` again with a different `--ai` (or `--ide`) value.
- **After upgrading specy-road:** Run **`specy-road refresh-stubs`**, not `init --force`. It rewrites exactly the paths `.specyrd/manifest.json` records, adds stubs that shipped since you initialized, and leaves everything else alone. See [Keeping a consumer repo current](install-and-usage.md#keeping-a-consumer-repo-current-after-an-upgrade).
- **Flags (overview):** `specyrd init [PATH] --ai cursor|claude-code|codex|generic` with optional `--here`, `--dry-run`, `--force`. For `generic`, pass `--ai-commands-dir <relative-path>` under the repo root. Running it again for a second harness adds only that harness's links; the skill files are shared.

### What `--force` may touch

`--force` overwrites the paths listed in `.specyrd/manifest.json` for the pack being installed — the command stubs and `.specyrd/README.md` — and nothing else.

Three files belong to **you**, and `specyrd init` only maintains one delimited block inside each, marked `>>> specy-road managed block — do not edit inside <<<`:

| File | Block contents |
| --- | --- |
| `.gitignore` | `.specyrd/cache/` (derived, disposable indexes) |
| `.cursorindexingignore` | archived and duplicated material, excluded from the IDE index but still readable |
| `CLAUDE.md` | the specy-road load order, roadmap model, and non-negotiables (`--ai claude-code`) |

`specy-road init project` keeps the specy-road section of `AGENTS.md` the same way (load order, task loop, review roles, shared-checkout rules). Everything outside those markers is never read and never rewritten, with or without `--force`. Re-running is a no-op when the block is already current, and `--dry-run` reports what each block would do.

See `.specyrd/README.md` after init for a short pointer (and `manifest.json` for which packs were applied).

---

## Core idea: documentation as source of truth

Treat durable rules, architecture decisions, and conventions as **version-controlled artifacts** agents can read. Chat and comments are not substitutes for files when a rule must hold across sessions.

Principles that age well:

1. **Docs over verbal agreements** — If it matters, it lives where an agent (or a new teammate) can find it.
2. **Design for careful readers** — Be explicit; ambiguity becomes wrong assumptions.
3. **Multi-agent coordination is structural** — Codenames, touch zones, and registration reduce collisions (see [`git-workflow.md`](git-workflow.md)).
4. **Small, cohesive files** — Easier to load fully and reason about; align with [`constraints/file-limits.yaml`](../constraints/file-limits.yaml) in *this* repo, or define your own limits in *your* product repo.
5. **Enforce what must stick** — “Guidelines” that are never checked drift; put must-hold rules in CI or validators where possible.

---

## Optional “five layers” (product repos)

Many teams combine:

| Layer | Typical location | Role |
| ----- | ---------------- | ---- |
| Entry point | `CLAUDE.md` or vendor equivalent | Dense project contract (stack, structure, pointers) |
| IDE rules | `.cursor/rules/*.mdc` or similar | Scoped rules by path or always-on |
| Specifications | `docs/*.md` | Architecture, API, commands, hosting |
| Session memory | Vendor-specific store | High-signal, lean notes (avoid duplicating repo docs) |
| Verification | CI, scripts, compose | Pass/fail gates |

When layers conflict, **tracked docs in the repo** should win.

---

## Optional: `CLAUDE.md` or equivalent entry file

`specy-road init project` writes the specy-road section of `AGENTS.md`, and `specyrd init --ai claude-code` the one in `CLAUDE.md`, as managed blocks; the rest of each file is yours. If your tool reads a root entry file, keep that part **short** and link out to `docs/`. Useful sections: project identity, tech stack with versions, directory map, workflow pointers, and a table of canonical docs.

For **roadmap-driven branches** and registration, point to your git workflow doc. In **this** repository that is [`git-workflow.md`](git-workflow.md) and **`roadmap/registry.yaml`** — not a free-form status file unless your team chose one.

---

## Optional: Cursor (or IDE) rules

The `/specyrd-…` skills under `.agents/skills/` come from `specyrd init`; rule files are yours to add. Rule files can scope instructions by glob (e.g. backend vs frontend). Prefer **pointers** to canonical docs over pasting large policies in every rule. Keep “do not refactor unrelated code”-style scope rules if your team needs them.

---

## Optional: `docs/` in an application repository

Typical high-value docs for app repos:

- **Architecture** — Layering, imports, errors, configuration access.
- **API or contract** — Schemas, endpoints, type mapping if you have a split stack.
- **Commands** — Exact dev, test, and lint commands (including PATH quirks).
- **Git workflow** — Branch naming, merge policy, **registration** and touch zones.

specy-road already separates **merged roadmap graph** (manifest + chunk files under `roadmap/`) from **active claims** (`registry.yaml`). Extra markdown tables or `docs/roadmap-status.md` are optional patterns for repos that want a human status board in addition to the registry.

---

## Optional: verification gates

Many teams define a small set of **mandatory** checks before merge (e.g. typecheck + lint, tests, container build). Tune gates for speed and clarity; document them so agents and humans run the same commands. This kit validates the roadmap with `specy-road validate`; your **application** may add language-specific gates.

---

## Optional: MCP servers

[Model Context Protocol](https://modelcontextprotocol.io/) servers expose structured tools (git, Docker, issue trackers) instead of ad hoc shell. Useful when your workflow benefits from scoped, typed actions—not required for specy-road, which ships no MCP server: agents reach it through the installed skills and the CLI.

---

## Optional: a shared-checkout guard hook

When more than one agent session works in one checkout, `specy-road session
guard` denies the git commands that move or discard another session's work
(see `docs/orchestration.md`, Presence). Wire it into the harness's
"before a shell command runs" hook. `specy-road session guard --format <harness>
--print-config` prints the snippet on stdout, pure JSON you can paste whole,
and the harness's caveats on stderr.

**Claude Code** (verified against the hooks docs, 2026-10): a `PreToolUse` hook
matched to `Bash` in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "specy-road session guard --format claude-code", "timeout": 30}
        ]
      }
    ]
  }
}
```

The hook reads `tool_input.command` from stdin; exit 2 blocks the call and the
reason on stderr reaches the model; on a non-denial the guard emits context
only (an `additionalContext` note, which is how it warns when a command
would be refused if another session were live) and never an `allow`, so
Claude's own permission policy still applies to the call. Any other exit code lets the
call proceed, so the guard exits 2 on an internal error rather than fail
open. Hooks run in `claude -p`; `claude --bare` skips every hook; a sandbox
run (2026-10-28) saw the hook fire and block under
`claude -p --dangerously-skip-permissions` (`bypassPermissions`). Export
`SPECY_ROAD_AGENT_ID` in the session so the guard knows which presence record
is its own.

**Codex** (verified against the hooks docs, 2026-10): the same stdin shape,
as a `PreToolUse` hook on `Bash` in `.codex/hooks.json` (or `[hooks]` in
`.codex/config.toml`). Exit 2 with stderr denies; exit 0 with no output is
the documented allow, and Codex marks a hook failed on keys it does not
support, so the guard's allows are silent there. Project hooks load only
when the project's `.codex/` layer is trusted, and each hook definition
must be trusted in `/hooks` (or run with `--dangerously-bypass-hook-trust`).
Codex skips an untrusted hook silently, with nothing in the output, so a
headless run looks guarded when it is not. Hooks fire under `codex exec`; a
sandbox run (2026-10-28) saw the guard block under
`--dangerously-bypass-approvals-and-sandbox` too. The IDE extension is
unverified.

**Cursor** (verified against the hooks docs, 2026-10): a
`beforeShellExecution` hook in `.cursor/hooks.json`. The command arrives as
top-level `command` on stdin; the answer is JSON on stdout,
`{"permission": "allow" | "deny", "agent_message": "…"}`. Empty output on exit
0 counts as a hook *failure*, which fails open unless `failClosed: true`, so
the guard answers every event explicitly and the printed snippet sets
`failClosed: true`. Whether the hook fires in `agent -p` and under auto-run is
unverified; community reports say `deny` holds there.

Get each snippet with `specy-road session guard --format cursor --print-config`
(or `codex`). The repo's own test suite runs every adapter as a subprocess
with its harness's documented payload (`tests/test_hook_adapters.py`), so an
adapter that drifts from its contract fails in CI, not in someone's IDE.

**Intervention witness.** When a human takes over a worker (`specy-road
worker handoff`), the same three harnesses' prompt-submit hooks can record
what the human said so `worker reclaim` reports it: `specy-road worker hook
--format claude-code|codex|cursor --print-config` prints the snippet
(`UserPromptSubmit` for Claude Code and Codex, `beforeSubmitPrompt` for
Cursor). It never blocks a prompt. See `docs/orchestration-workers.md`.

**Skills, one source for every harness.** Cursor and Codex both read
`.agents/skills/<name>/SKILL.md` natively and follow symlinked skill folders;
Claude Code reads `.claude/skills/<name>/SKILL.md` and loads a skill directory
that is a symlink. That is the layout `specyrd init` writes (verified against
each harness's docs, 2026-10). Where a symlink cannot be created, the skill is
copied into place and the manifest records the copy.

## Optional: git worktrees for parallel agents

Separate worktrees give isolated working trees while sharing history. Pair with **non-overlapping touch zones** and registration so two agents do not edit the same paths blindly. See [`git-workflow.md`](git-workflow.md) for this repo’s protocol.

---

## Optional: prompt habits

- **Atomic tasks** — One clear scope per request; mirrors roadmap discipline.
- **Curated context** — Prefer briefs and cited docs over pasting entire trees.
- **Tests as guardrails** — Test or contract sketches before large implementations often reduce rework (especially for generated code).
- **Review, cleanup and security passes** — Use your harness's built-in skills for these; specy-road's own review contract (`review-packet`, `review record`, the review gate) is in [orchestration.md](orchestration.md).

---

## Checklists (adapt to your repo)

**New roadmap-driven work (specy-road style):**

- Confirm gates and dependencies for the milestone.
- Read `roadmap/registry.yaml` for overlapping touch zones.
- Register on the integration branch, then branch `feature/rm-<codename>` per [`git-workflow.md`](git-workflow.md).
- Implement; remove registry entry before merge.

**Greenfield product repo (optional, if you use markdown status):**

- Some teams maintain `docs/roadmap-status.md` instead of YAML—equivalent **discipline** (still register on integration before feature work), different storage. Prefer **one** system per repo.

---

## See also

- [`philosophy-and-scope.md`](philosophy-and-scope.md) — what specy-road requires vs leaves open
- [`architecture.md`](architecture.md) — validation and brief generation in this repository
- [`git-workflow.md`](git-workflow.md) — branches, registry, merge-back
- [`orchestration.md`](orchestration.md) — review packets, review records, and the review gate
