# Orchestration: building the roster

Companion to [orchestration.md](orchestration.md) (roles, the review gate, the
`roadmap/orchestration.yaml` reference) and
[orchestration-models.md](orchestration-models.md) (profiles, `prompt`,
`orchestrate plan`). This page is the short path from no roster to a working
one, and the two `orchestrate plan` choices that depend on it.

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

## Spreading executors: `orchestrate plan --spread`

By default every leaf goes to the cheapest capable executor (the ranking in
[orchestration.md](orchestration.md), "Executor ranking"), so one model can
receive every leaf of a long grind. `--spread` assigns executors round-robin
instead: the capable, available entries for a leaf are ranked the same way, and
the leaf at position *i* in the plan (batches in order, then leaves within a
batch) takes entry *i* modulo their number. The assignment is deterministic for
a given roadmap and roster. It does not weigh cost or current load.
