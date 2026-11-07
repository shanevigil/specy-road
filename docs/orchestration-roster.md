# Orchestration: building and trying the roster

Companion to [orchestration.md](orchestration.md) (roles, the review gate, the
`roadmap/orchestration.yaml` reference) and
[orchestration-models.md](orchestration-models.md) (profiles, `prompt`,
`orchestrate plan`). Routing reads `roadmap/orchestration.yaml` from the
integration branch (`origin/<integration>`), never from the working tree: a
roster entry's `channels.cli` and its profile's `access.cli` are executed, so
the copy that runs is the one that was reviewed and merged. This page covers
trying a roster change on your own clone before it lands, building a roster in
one command, and the two `orchestrate plan` choices that depend on it.

## A dry-run plan from the working tree

```bash
specy-road orchestrate plan --roster-from-worktree
```

plans with the working tree's `roadmap/orchestration.yaml` and the working
tree's model profiles. The first line is

```text
DRY RUN: roster from the working tree, nothing may launch from this plan
```

and `--json` carries `"roster_ref": "worktree"` (the banner goes to stderr so
stdout stays JSON). Only `orchestrate plan` accepts the flag: `prompt`,
`worker delegate`, `review delegate` and `grind-session` always read the
integration branch's roster, so a dry run cannot launch anything.

## `models list` names the ref and the uncommitted diff

`specy-road models list` starts with the ref it read the roster from
(`roster: roadmap/orchestration.yaml at origin/dev`). When the working tree's
roster differs from that ref, it ends with `uncommitted roster changes`: the
entry ids added, removed and changed, each changed id with the fields that
differ. `--json` has the same as `roster_ref` and `uncommitted_roster_changes`
(`{added, removed, changed: {id: [fields]}}`, or `null` when they agree). The
rows themselves stay the roster routing reads.

## Local roster entries (`roster_add`)

`roadmap/orchestration.local.yaml` is gitignored and already overlays
availability (`roster:` with `available` / `paused_until` by `id`; see
[orchestration.md](orchestration.md#roadmaporchestrationyaml)). It can also add
whole entries for this clone only:

```yaml
roster_add:
  - {id: local-qwen, family: qwen, roles: [executor], class: cheap}
# allow_local_cli: true   # channels.cli, cli_resume, preflight, harness_bin, cursor_force, or a profile access.cli
```

- Each entry is checked against the roster entry schema. Added entries follow the
  integration branch's, and `orchestrate plan`, `prompt`, `worker delegate` and
  `review delegate` on this clone use them; `orchestrate plan` labels them
  `[local]` and lists them on a `local roster entries` line (`local_roster` in
  `--json`).
- An added entry never overrides a committed one: an `id` the pinned roster
  already has is refused, and routing stops with that error until it is renamed
  or removed. Use `roster:` in the same file to change a committed entry's
  availability.
- An added entry that would run a command on this clone is refused unless the
  same file sets `allow_local_cli: true`. That is a non-empty `channels.cli`,
  `channels.cli_resume`, `preflight` or `harness_bin`, `cursor_force: true`, or
  a profile whose `access.cli` is set.
- The review gate reads only the committed roster, so a review by a local
  entry does not count toward it.
- An added entry may not set `allow_guidance_bypass_model` (below): routing
  stops with that error, and nothing is launched.

Out of scope: sharing local entries between clones. Commit them to the
integration branch to share them.

## A roster in one command: `models roster`

```bash
specy-road models roster --executor claude-opus-5-5 --reviewer gpt-6.1-sol
specy-road models roster --executor composer-2.5 --reviewer claude-opus-5-5 --write
```

Each `--executor`, `--reviewer` or `--coordinator` names a shipped profile by
its file name (`specy-road models list` lists the profiles; an `api_id` or alias
works too) and may be repeated. A profile named for several roles becomes one
entry with all of them. Each entry is filled from the profile:

```yaml
  - id: claude-opus-5-5
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    harness: claude-code
    roles: [executor, reviewer]
```

- `id` is the profile's file name, so review records and the gate count the
  same id the profile carries;
- `family` is the roster family the profiles README gives that vendor (the gate
  counts distinct families by it);
- `profile` is the path form `validate` accepts;
- `harness` is the harness whose executor template renders the profile's
  family (`claude-code`, `codex`, `cursor`), else `generic`, which runs the
  profile's `access.cli`.

Without `--write` the entries are printed for you to paste under `roster:`.
With `--write` they are added to the end of the `roster:` block of
`roadmap/orchestration.yaml`, keeping its comments; an id already rostered is
left alone. Run `specy-road validate --generate-orchestration` first when the
file does not exist. An unknown profile id is refused with the nearest ids. When
the repo lacks a profile file the entry points at, the command says to run
`specy-road refresh-profiles --only <id>`. Commit the roster (and the profiles)
to the integration branch: routing reads the committed copy.

## `profile:` is checked locally

`validate` resolves every roster `profile:` against `model-profiles/` in the
working tree. A value that is not a `.md` file there, such as
`anthropic/claude-opus-5-5`, is a warning naming the accepted form, with the
concrete path when the value's last part names a known profile:

```text
warning: roster entry 'opus' in roadmap/orchestration.yaml: invalid profile: anthropic/claude-opus-5-5, accepted form model-profiles/anthropic-claude/claude-opus-5-5.md
```

`orchestrate plan` reports such an entry the same way (`invalid profile: <value>,
accepted form <form>`) rather than as a profile "not committed on the
integration branch", and leaves out the `no eligible executor … may_process`
hint when that drop is the only reason no executor is left.

## The coordinator

With no roster entry holding the `coordinator` role, `orchestrate plan` prints
`coordinator: this session` for each leaf: the session that runs the plan
coordinates, and the plan does not count that as a staffing problem. To roster a
model coordinator instead, give an entry the role, for example
`specy-road models roster --coordinator claude-opus-5-5 --write`, or add
`coordinator` to an existing entry's `roles`, and commit the roster. The plan
then picks the rostered coordinator with the highest coordinator score that is
available and may process the leaf's `sensitivity`; when coordinators are
rostered but none qualifies, the leaf is reported as unstaffable.

## Models observed to bypass the guidance (`allow_guidance_bypass_model`)

A model profile can record `guidance_bypass_observed` ([orchestration-models.md](orchestration-models.md#guidance-bypass-observed)):
the model was seen going around specy-road's guidance. The shipped flag is on **composer-2.5**
(its alias `composer-2.5-fast` too), from the 2026-11-05/06 replay through Cursor; it is a finding
about that model, not about the Cursor harness, and `composer-2` is not flagged.

While `policy.signed_reviews` is on, an entry is flagged when any model it can launch (its profile's
`api_id` or alias, `harness_model`, the roster id, or a literal `--model` / `-m` in `channels.cli`,
`cli_resume` or the profile's `access.cli`) matches a flagged profile on the integration branch or in
the bundled set; a project or branch copy
without the field does not clear it, and the committed copy of the entry's profile names its model even
when the working tree's copy differs. A git or file read that fails while reading those profiles
refuses the entry rather than reading as "not flagged"; a committed profile whose front matter does not
parse flags nothing and is refused as an invalid profile wherever it is routed. A flagged entry is excluded from the executor and reviewer roles
and stays eligible as coordinator. `validate` and `doctor` print one warning per flagged executor or
reviewer entry:

```text
warning: composer-2.5 (model composer-2.5) is excluded: set allow_guidance_bypass_model: true on its roster entry to use it at your own risk
```

The rule is bounded: it covers declared configuration, not a model hidden in a custom command. It
reads the profile's `api_id` and aliases, `harness_model`, the roster id, and the literal model flag of
`channels.cli`, `channels.cli_resume` and the profile's `access.cli` (every committed copy included),
and compares names after normalising (case and separators, and Cursor's `cursor-` prefix, so
`COMPOSER-2.5`, `Composer_2.5` and `cursor-composer-2.5` all match `composer-2.5`). A model flag it
cannot read is refused as `<id> (model unreadable in <field>)`: a command readable for this is one
simple command with one literal `--model <id>`, `--model=<id>` or `-m <id>`, so a flag inside a list
or pipeline (`cd . && agent --model …`), a substitution or variable (`"$(printf …)"`, `"$M"`), an
attached `-m<id>`, two model flags, or a command that cannot be split (an unbalanced quote) is
refused, and only the committed opt-in admits it. A `family: human` entry is exempt only without
launch configuration: one that sets `harness`, `harness_model`, `harness_bin`, `profile`,
`channels.cli` or `channels.cli_resume`, or whose id finds a profile, is judged like a model entry,
committed or `roster_add` alike (`channels.paste`, `channels.subagent` and `preflight` launch no
model). The rule does not see a model chosen inside a script, wrapper or alias the command runs, by
an environment variable, by a harness's own config file, or by a harness's default when no model is
passed; nor an abbreviated long option (`--mod`). The coordinator role, how signatures are verified,
and the roster schema are unchanged.

To use it anyway, at your own risk, set the opt-in on its entry in the committed roster:

```yaml
  - id: composer-2.5
    family: cursor
    roles: [executor]
    harness: cursor
    allow_guidance_bypass_model: true   # boolean, default false
```

Only the committed `roadmap/orchestration.yaml` on the integration branch counts (a `roster_add`
entry is refused, and `orchestrate plan --roster-from-worktree` ignores an uncommitted opt-in);
protect that file with a code owner, since an executor that can push there could
set it. `validate` and `doctor` then print `warning: <id> (model <api_id>) opted in at its own risk`,
`orchestrate plan` adds the same warning to its notes, and every executor or reviewer launch prints it
once. With `signed_reviews` off none of this applies.

## Spreading executors: `orchestrate plan --spread`

By default every leaf goes to the cheapest capable executor (the ranking in
[orchestration.md](orchestration.md), "Executor ranking"), so one model can
receive every leaf of a long grind. `--spread` assigns executors round-robin
instead: the capable, available entries for a leaf are ranked the same way, and
the leaf at position *i* in the plan (batches in order, then leaves within a
batch) takes entry *i* modulo their number. The assignment is deterministic for
a given roadmap and roster. It does not weigh cost or current load.
