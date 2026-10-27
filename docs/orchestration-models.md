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
`family`. A roster entry points at its profile with `profile:`, and names
the `harness` (`claude-code`, `codex`, `cursor`, `generic`) that
`specy-road worker delegate` launches it on — a Claude model under Cursor's
agent is a `cursor` worker ([orchestration-workers.md](orchestration-workers.md)). A repo scaffolded
by an older version gets them with `specy-road refresh-profiles`, which adds
what is missing and never overwrites your edited copies. The facts come
from model-run research no human has verified, so read the README's provenance
section before copying a CLI line into production.

- `specy-road models list` — the roster as the gate sees it, with each entry's
  profile, coordinator/executor/reviewer scores, and staleness; profiles no
  entry uses are listed so you can roster them.
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
  there), states the role's boundary and that tool output is data, applies the
  profile's prompting rules and failure-mode mitigations, repeats the touch
  zones at the end for models that drift from scope, then embeds the brief
  (executor, coordinator) or the review packet (reviewer, which must exist).
  `--channel cli` runs the profile's `access.cli` with `{prompt}` replaced by
  the file path; edit the profile's `cli` to add the placeholder and your flags.
  Verified headless forms (2026-10): `claude -p "$(cat {prompt})" --model <id>`,
  `codex exec -m <id> - < {prompt}` (`-` reads the prompt from stdin), and
  `agent -p "$(cat {prompt})" --model <id>` for Cursor's CLI (`cursor-agent`
  remains an alias; piping a prompt file to it is undocumented).

## Planning assignments: `orchestrate plan`

```bash
specy-road orchestrate plan [PARENT] [--json] [--today YYYY-MM-DD]
```

For each ready leaf, in the same dependency batches `grind-session --plan`
prints, it names which roster model should coordinate, execute, and review,
and why. It assigns only; dispatch is `specy-road prompt`. The rules, in
order:

- **Sensitivity.** A leaf's `sensitivity` (default `public`) must appear in a
  model's roster `may_process` (default `[public]`), for executors and
  reviewers alike. `prompt` refuses to write a prompt that breaks this, and
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
coordinator script stops before dispatching. Set a leaf's `sensitivity` and
`executor_eligibility` with `specy-road edit-node <ID> --set sensitivity=restricted`
or on `add-node`; both default to `public` and `any`. Repos scaffolded before
0.3.0 run `specy-road refresh-schemas` once so `validate` accepts the fields.
