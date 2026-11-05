# Orchestration: trying a roster before it lands

Companion to [orchestration.md](orchestration.md) and
[orchestration-models.md](orchestration-models.md). Routing reads
`roadmap/orchestration.yaml` from the integration branch (`origin/<integration>`),
never from the working tree: a roster entry's `channels.cli` and its profile's
`access.cli` are executed, so the copy that runs is the one that was reviewed
and merged. This page covers the ways to see a roster change on your own clone
before it lands.

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
# allow_local_cli: true   # needed for an entry with channels.cli or a profile with access.cli
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
- An added entry that would run a command on this clone, through
  `channels.cli` or through a profile whose `access.cli` is set, is refused
  unless the same file sets `allow_local_cli: true`.
- The review gate reads only the committed roster, so a review by a local
  entry does not count toward it.

Out of scope: sharing local entries between clones. Commit them to the
integration branch to share them.
