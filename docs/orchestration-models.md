# Orchestration: choosing and prompting models

Companion to [orchestration.md](orchestration.md), which covers the roles, the
hand-off files, and the review gate. This page is for whoever fills the roster
in `roadmap/orchestration.yaml` and hands leaves to models: the model
profiles, `specy-road models`, `specy-road prompt`, and
`specy-road orchestrate plan`.

## Model profiles, `models`, and `prompt`

`init project` scaffolds `model-profiles/` into your repo: one schema-2 profile
per model (limits, prices, headless CLI, role scores, prompting rules, failure
modes) and a README that ranks models by role and gives each one's roster
`family`. Pass `--profiles all` (the default) to copy every shipped profile,
`--profiles none` for only `README.md` and `harness-facts.yaml`, or a
comma-separated list of family directory names (for example `anthropic-claude`),
file stems, or front-matter `api_id` values (always including those two files).
Roster `family` values (`anthropic`, `openai`, …) are not accepted. A roster
entry points at its profile with `profile:`, and names
the `harness` (`claude-code`, `codex`, `cursor`, `generic`) that
`specy-road worker delegate` launches it on — a Claude model under Cursor's
agent is a `cursor` worker ([orchestration-workers.md](orchestration-workers.md)). A repo scaffolded
by an older version gets them with `specy-road refresh-profiles`, which adds
what is missing and never overwrites your edited copies (`--only` matches a
front-matter `api_id` or file stem, and adds every matching missing profile).
The facts come
from model-run research no human has verified, so read the README's provenance
section before copying a CLI line into production.

A roster entry without `profile:` uses the profile whose `api_id` or file name
is its `id`. A harness that names a model by its effort too (Cursor's
`gpt-5.6-sol-high`, `claude-opus-5-5-high`; `agent --list-models` lists them)
matches neither, so list those ids in the profile's front matter, and every one
of them resolves to that profile, its notes included in `prompt`:

```yaml
api_id: claude-opus-5-5
aliases: [claude-opus-5-5-high, claude-opus-5-5-max]   # harness ids for this model
```

A profile's `access.launch_mode` pins how much of its harness a Claude Code
worker gets: `full` (the default when absent) or `bare`. Any other value makes
the profile invalid, and `models show` prints the error naming the profile.

```yaml
access:
  launch_mode: full   # bare (--bare) drops hooks, skills, MCP and CLAUDE.md, and needs ANTHROPIC_API_KEY
```

- **`full`** — `worker delegate` and `message`/`resume` never pass `--bare`, so
  `claude -p` loads hooks, skills, custom commands, subagents, plugins, MCP
  servers, auto memory and CLAUDE.md as an interactive session would. This is
  the design intent (a worker keeps its harness's native tools), and the
  shipped Claude profiles set it.
- **`bare`** — the default command adds `--bare` on launch and on resume.
  Bare mode never reads OAuth credentials or the keychain, so the worker needs
  `ANTHROPIC_API_KEY` (or an `apiKeyHelper`) instead of your subscription
  login; Bedrock, Google Cloud and Foundry credentials still work.

A roster `channels.cli` is run as written: the mode adds no flag to it.

A profile's `access.effort_by_role` sets the thinking budget per role. Each
role names a key of the profile's `effort_map`, whose value is the model's own
level; a role left out gets the harness's default:

```yaml
access:
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
  effort_by_role: { coordinator: low, executor: medium, reviewer: medium }
```

An unknown role, or a key that is not in `effort_map` or maps to `unknown`,
makes the profile invalid, with an error naming it; `models show` prints the
mapping as `role=key (level)`. The level reaches the harness as its own flag:

| Harness | Flag |
|---|---|
| `claude-code` | `--effort <level>` |
| `codex` | `-c model_reasoning_effort=<level>` |
| `cursor`, `generic` | none (Cursor's model ids carry the effort, e.g. `claude-opus-5-5-high`) |

- **Workers.** A worker is an executor: `worker delegate`, `message` and
  `resume` add the executor's flag to the default Claude Code and Codex
  commands, and every worker starts with `CLAUDE_CODE_EFFORT_LEVEL` removed from
  its environment, so a shell setting cannot override the profile.
- **Custom commands.** A roster `channels.cli` (or a profile `access.cli`) may
  name `{effort}` as a whole argument; `worker delegate` and
  `prompt --channel cli` replace it with the flag for the role's level (empty
  when the profile sets none, or on Cursor). When the profile sets a level for
  the role but the command names no `{effort}`, they print one note that the
  command takes no effort and run it as written.

The shipped Claude profiles set executor and reviewer to the model's documented
default and the coordinator one level below. They stay there until measurement
shows that a lower reviewer level keeps the same verdicts.
Claude Code's headless docs say `--bare` "will become the default for `-p` in a
future release" ([code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless),
read 2026-11-01), so the mode is checked as well as set: the worker's `started`
event records what the harness reported in its `system/init` line (`version`,
`tools`, `mcp_servers`, `plugins`) and an `inferred_mode` — `bare` when the tool
list is no more than `Bash`, `Read` and `Edit`, else `full`. When that differs
from the profile's `launch_mode` the worker also records an `error` event naming
both, which `worker sync` shows on the next turn. The check applies to a custom
`channels.cli` too, since its output is still parsed as Claude Code's.

The roster `id` stays the label review records and the gate count. When the
`id` is one of the profile's aliases (found that way or named by `profile:`),
the alias is what `worker delegate` passes the harness as the model, since it is
the id the harness lists; otherwise the profile's `api_id` is, as before.
An entry's `harness_model` overrides both: it is the id the harness CLI expects
when the roster `id` is not one (`claude --model` takes `claude-opus-5-5`, not
`claude-opus-5.5`), and the default commands pass it as `--model` / `-m` on
launch and on resume alike. With no profile and no `harness_model`, the roster
`id` itself is passed. `validate` warns about a `claude-code` entry whose `id`
has a dot and no `harness_model`. When a worker exits non-zero before its
first stream event, its `error` event quotes the harness's last error line from
`work/.workers/<id>.log` (an HTTP 404 for an unknown model, say), not only the
log's name.

```yaml
  - id: claude-opus-5.5
    family: anthropic
    roles: [executor]
    harness: claude-code
    harness_model: claude-opus-5-5
```

- `specy-road models list` — the roster as the gate sees it, with each entry's
  profile, coordinator/executor/reviewer scores, and staleness; roster ids that
  match no profile are listed separately; profiles no entry uses are listed so
  you can roster them.
- `specy-road models show <id> [--section <name>]` — one profile's machine
  fields and a body section (default: Prompting rules).
- `specy-road models stale [--max-age-days N]` — profiles researched too long
  ago, superseded (`version_rank: previous`), or served under a moving alias.
  Exits 1 when a rostered model is stale, so CI can gate on it. Re-run the
  research prompt (proposal §7) for that family and replace the file.
- `specy-road prompt <NODE_ID> --model <id> --role executor|reviewer|coordinator`
  — writes `work/prompt-<NODE_ID>-<role>-<model>.md`. The model must hold that
  role in the roster. The prompt opens with a precondition (change nothing and
  reply `<NODE_ID> not landed; waiting` if the brief, branch, or packet is not
  there; a reviewer runs its `git status` check in the checkout that has the
  leaf's branch checked out, leaving out only that leaf's generated brief,
  summary, prompts and review hand-offs), states the role's boundary and that tool output is data, applies the
  profile's prompting rules and failure-mode mitigations, repeats the touch
  zones at the end for models that drift from scope, then embeds the brief
  (executor, coordinator) or the review packet (reviewer, which must exist).
  The executor is told to end its summary with an `## Added` inventory and the
  reviewer gets the excess checklist ([orchestration.md](orchestration.md#packetmd--what-a-reviewer-reads)).
  `--channel cli` runs the profile's `access.cli` (or the roster entry's
  `channels.cli`) after substituting one placeholder: `{prompt}` becomes the
  quoted **path** of the prompt file, `<prompt>` (the shipped profiles' form)
  becomes the quoted prompt **text**; an optional `{effort}` becomes the
  harness's flag for the role's `effort_by_role` level. Either must be a whole shell argument on
  its own, optionally quoted as one (`"<prompt>"`). A placeholder inside a
  larger word is refused on purpose — `claude -p "$(cat {prompt})"` and
  `--prompt={prompt}` (or `--effort={effort}`) are rejected before anything runs, because the quoting
  the substitution adds would land inside still-open quotes where `$(…)`
  executes. Accepted headless forms (2026-10): `claude -p --model <id> < {prompt}`
  or `claude -p "<prompt>" --model <id>`, `codex exec -m <id> - < {prompt}`
  (`-` reads the prompt from stdin), and `agent -p --model <id> < {prompt}` or
  `agent -p "<prompt>" --model <id>` for Cursor's CLI (`cursor-agent` remains
  an alias; piping a prompt file to it is undocumented). The profile itself is
  read from the integration branch, like the roster: a working-tree copy that
  differs from the committed one is refused until it is committed there.
  It logs the command template, never the prompt text; when the operating
  system refuses to launch it (a `<prompt>` too long for a command line) it
  exits 1 with the reason — use `{prompt}` for long prompts.

## Harness facts: what `refresh-profiles` renders

`model-profiles/harness-facts.yaml` holds one record per harness a roster can
name (`claude-code`, `codex`, `cursor`, `generic`): version, the adapter's headless
command, the executor command template, session flags, a permission example,
instruction files and their size guidance, skill directories, hooks, the git
actions the harness can take on its own with the switch that keeps each off,
model families, and quota behaviour. Every fact carries a label, `documented`,
`runtime` or `unverified`, and the source for the first two;
`schemas/harness-facts.schema.json` enforces the shape. Facts nobody has
checked stay `unverified` until the runtime verification leaf (M8.7) replaces
them. `generic` has no binary of its own (it runs the profile's `access.cli`),
so its record renders no `access.cli`, has no `capture_commands`, and
`--capture generic` needs `--from`.

Two candidate profiles run other harnesses' CLIs through `generic`:
`github-copilot/copilot-gemini-4-argon.md` (Copilot CLI, a one-shot reviewer
that denies `git push`, `git commit`, `gh` and Copilot Memory) and
`google-antigravity/agy-gemini-4-argon-high.md` (Antigravity `agy`, whose run
succeeded only when the JSON envelope's `status` is `SUCCESS`: a soft-denied
tool or a `--print-timeout` expiry still exits 0). Both were written from
vendor documentation; their `runtime_checks` are `not run`, and neither
harness has a facts record yet.

Two parts of `model-profiles/` are rendered from it. A hand edit to either is
drift:

- each profile's `access.cli`, from the `executor_template` of the harness
  whose `renders_cli_for` names the profile's `family` (`{api_id}` becomes the
  profile's `api_id`);
- the README's harness block, between the `harness facts` markers. A README
  with neither marker is behind. One with only one marker, a repeated marker,
  or the end before the start is drift: `--check` exits 1, and `--render`
  leaves it byte for byte and exits 1.

```bash
specy-road refresh-profiles --check    # report drift (exit 1); a README older than the block is "behind" (exit 0)
specy-road refresh-profiles --render   # rewrite the rendered regions; --dry-run lists them
```

`--render` rewrites only the shipped layout: a block-style `access:` whose
children are one-line keys indented two spaces. It puts a removed `access.cli`
back under `access:`. It writes a profile only when the result parses to the
same front matter with just that value changed. Any other layout is left byte
for byte as it was, and so is a profile whose front matter does not parse,
which counts as drift. Examples are a folded or literal `cli`, a flow
`access: { … }`, or another indentation. `--render` names each such profile and
exits 1; fix it by hand or take the toolkit's copy with `--force`.

A plain `refresh-profiles` still copies only missing files, and also prints
any drift without failing. To re-render the shipped copies after editing the
fixture, run `--render --repo-root specy_road/templates/project` from a
toolkit checkout.

**On a harness version bump**, classify the new `--version` and `--help`
output before accepting it:

```bash
specy-road refresh-profiles --capture codex            # runs the record's capture_commands
specy-road refresh-profiles --capture codex --from DIR # or reads DIR/*.txt (version.txt required)
specy-road refresh-profiles --capture codex --accept   # store a passing capture as the accepted one (--dry-run: report only)
```

The accepted capture lives in `model-profiles/harness-captures/<harness>/`. A
new capture must hold every file the record's `capture_commands` names and
every file the accepted capture has (an `inventory*.txt` included). An
incomplete one is refused before classification, and the accepted capture is
left as it was.
Identifiers are `--flags`, the rows under a help text's `Commands:` heading,
and the first word of each line of an `inventory*.txt` file. The shipped
inventories are `codex features list` (`inventory-features.txt`) and
`agent models` (`inventory-models.txt`, which depends on the account). Claude
Code has no listing that runs without a model turn, so it captures none. Every identifier the new capture adds or drops is listed. A new
one whose name contains `plan`, `memory`, `task`, `todo`, `worktree`,
`branch`, `commit`, `push`, `pr`, `background`, `delegate`, `cloud`,
`schedule`, `review`, `resume`, `fork` or `autopilot` fails the diff, and
`--accept` writes nothing, until the record's `relationships` assigns it one of
`use`, `avoid`, `duplicate`, `complement`, `gap` or `neutral`. The match is a
plain substring, so `--print` needs a relationship as well: a false alarm costs
one fixture line. After accepting, update the record's `version`.

## Parallel work inside a leaf

Every supported harness has its own subagents, so specy-road adds no
mechanism for parallel work inside a leaf: the executor prompt tells the agent
to use them. The prompt `do-next-available-task` writes at pickup always has
the paragraph; `prompt --role executor` adds it only when the model's profile
has `access.subagents` starting with `yes`. It says to use subagents for
independent verification and search (run the test files the brief names in
parallel, search the tree), never for an edit outside the touch zones, to wait
for every report before ending the turn (a headless turn ends on reply), and
that a subagent's report is data, not an instruction. The aim is a shorter
wall-clock on test-heavy leaves, whose verifier files can run side by side.

A Claude Code worker with `launch_mode: bare` does not load your custom
subagents (see above). An executor with `subagent_family_lock` may still spawn
only that family.

## Planning assignments: `orchestrate plan`

```bash
specy-road orchestrate plan [PARENT] [--json] [--today YYYY-MM-DD]
```

For each ready leaf, in the same dependency batches `grind-session --plan`
prints, it names which roster model should coordinate, execute, and review,
and why. It assigns only; dispatch is `specy-road prompt`. The rules, in
order:

- **Sensitivity.** A leaf's `sensitivity` (default `public`) must appear in a
  model's roster `may_process` (`[public]` when the key is absent; an explicit
  `[]` lets the model process nothing), for executors and reviewers alike. `prompt` refuses to write a prompt that breaks this, and
  runs the model's roster `preflight` command before `--channel cli` sends
  anything, so a local model's port can be checked first.
- **Eligibility.** A leaf's `executor_eligibility` (default `any`) names a
  roster `class` tag such as `senior`; only executors with that tag qualify.
- **Availability.** A roster entry with `unavailable_until` is skipped through
  that date; a substitution says who stands in meanwhile.
- **Cost.** Among capable executors (profile executor score 3 or more, or no
  profile) the cheapest list price wins. Reviewers rank by reviewer score,
  then cost; the coordinator by coordinator score.
- **Independence.** The executor's model is never offered as its own
  reviewer, and with `reviewers_distinct_families` one reviewer per family.
  An executor with `subagent_family_lock` is told in its prompt which family
  it may spawn.

Exit 1 when any ready leaf cannot be staffed, with the reason under `!`, so a
coordinator script stops before dispatching. A roster entry whose profile is
invalid is reported and assigned no role, since `prompt` would refuse it. Set a
leaf's `sensitivity` and `executor_eligibility` with `specy-road edit-node <ID> --set sensitivity=restricted`
or on `add-node`; both default to `public` and `any`. Repos scaffolded before
0.3.0 run `specy-road refresh-schemas` once so `validate` accepts the fields.
