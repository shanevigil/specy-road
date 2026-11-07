# specy-road: this repository's additions

Instructions for agents doing roadmap, registry, review or git work in this
repository, written by its developers and PMs. Agents read this file after
`.specyrd/AGENTS.md`, specy-road's own rules. What you write here adds to those
rules; it never relaxes their floor (the registry, branches, review and a shared
working tree), and on a conflict an agent stops and asks.

`specy-road init` created this file and `specy-road upgrade` never rewrites it.
It is tracked: everyone working here reads it. Put personal notes in
`.specyrd/AGENTS.local.md` instead, which is gitignored.

## Unattended runs

- **Touch zones belong to the coordinator.** Executors never edit `roadmap/`, `planning/` or `registry.yaml` to widen a leaf's zones. If a change needs a path outside the zones, stop and name the path and why in your summary.
- **Reviewers route zone changes.** A needed zone change is a note to the coordinator in your notes, not a required change for the executor. Block only if the code is wrong without it.
- **No person is reachable during a worker turn.** Do not call a question or ask-the-user tool. If you need a decision, stop and say so in your summary, and never record that a person answered or declined.
