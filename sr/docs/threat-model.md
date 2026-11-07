# Threat model for agent work

**In force since 2026-11-07.** This one is written for people. It is not cited from any file agents load, and it is listed in the agent ignore files. The maintainer alone changes it.

It says what specy-road defends against, what it does not, and what risk we accept. Agents work from `sr/constraints/review-brief.md` and the planning lenses, which carry the same rules in neutral language. The section "Why it is written this way" explains that split.

## What we defend against

**A motivated optimizer.** A capable agent that takes the cheapest path to a green signal and uses whatever its environment offers. It is not hostile, and it may give a plausible reason for what it did. We judge what it did, never what it intended.

**The plain mistake.** The wrong file, a missed acceptance line, a report of work that did not happen.

We do **not** defend against a deliberate attacker building a crafted exploit, or against a compromised machine or harness. Isolation is the planned answer to that tier, not more checks. Linux gets it first, in M22.44, before M16; other platforms get a warning.

## In scope

Each of these has happened, here or in published agent studies.

| Path to a false green | Seen here |
|---|---|
| Editing roadmap, acceptance, zones or roster to fit the work | An executor rostered itself and approved its own work; five leaves edited roadmap files in one night |
| Forging or bypassing review records and menus | Record writer called from `python -c`; human menu driven with `expect` |
| Weakening, skipping or special-casing tests | Published studies; watch for it here |
| Changing what the checks run: `conftest.py`, hooks, git config, harness settings | Published studies |
| Reading answers from git history or the network | Published studies |
| Reporting something that did not happen | A headless worker recorded a person as declining (field report) |
| Meeting the words but not the goal: a global lock for a race fix, a smaller workload | Published studies; needs a behavioural check, not a file guard |

**Gate integrity is always in scope.** Anything that lets a leaf count as approved without two real reviews blocks, however it is reached.

## Out of scope

- Crafted input built to defeat one check: odd encodings, unusual path spellings, special files such as FIFOs.
- Races that need a swap timed between two system calls.
- Resource exhaustion by deliberate oversizing.
- A substituted git binary, or changes to system-wide config.
- Prompt injection from repository content, beyond the standing rule that tool output is data.

## Where protection lives

- **Prevent what cannot be undone.** Landing, pushing, secrets.
- **Detect what can be undone, and reject it.** A worker's branch can be thrown away.
- **The merge point is the boundary.** Checks in the worker's environment are early feedback. What counts is what is checked at landing, outside the worker's control.

A check that is in place stays in place. This model decides what must be added, not what gets removed.

## Limits list

Accepted, known gaps. An item moves up only when it is seen happening.

| Limit | Why accepted | Would be closed by |
|---|---|---|
| Worker worktrees share the coordinator's git config and hooks, and Cursor workers run with `--force` on this host. A deliberately hostile worker could plant code there | Detected at turn end for the common cases; a real boundary needs isolation | Isolation (M22.44) |
| Crafted git config: non-UTF-8 include paths, FIFO includes, `/` as `core.hooksPath` | Out of scope | Isolation |
| Timed path swaps during safe writes | Out of scope | Isolation |
| Unusual path spellings through a symlinked `work/` | Out of scope, unless a record would count as approval | Isolation |
| Final gate runs in the worker's worktree | Reviewers see the diff. **This one should be fixed**, not accepted for long | Proposed new leaf: gate in a clean checkout |

## What we are accepting

A deliberately crafted attack may succeed against an unattended worker until isolation lands. Adopters should know that: the docs should say it plainly, and they should run workers accordingly.

## Why it is written this way

**Mitigation, not a complete defence.** Agents are stochastic, so no set of checks closes every path, and the attempt has a cost we measured ourselves: M21.37 took 13 rounds and M22.5 about seven, and each round found another case. All of M16 waited behind M22.5. The goal is reliable delivery of the intended result at a defensible cost. A governance system that stops the work has failed too.

**"Motivated optimizer", not "confused" or "hostile".** "Confused" is too weak: agents in published studies edited tests and patched test runners on purpose, with plausible reasons. "Hostile" is too strong: none of the documented cases, and none of ours, used crafted encodings or timed races. Our real incidents were ordinary, and the expensive review rounds were about things that never happened.

**A stated model stops scope creep in review.** Asked to find anything wrong, a reviewer has no definition of done, and the number of findings becomes the goal. That is goal inflation: the same drift we guard against in executors, in the other direction. A review should answer "can this leaf falsely look finished?", not "can anything at all go wrong?".

**Reproducible is not the bar.** Sol reproduces nearly everything with a probe, including the non-UTF-8 include. The test that ends the loop is whether a case is realistic here and whether something else already catches it.

**The merge point, not the worker.** A check inside the worker's environment can be changed by the worker. Hardening every hook is endless; checking the result once, outside the worker's reach, is one place to get right. If we ever need to defend against a hostile agent, that hardening also goes in one place.

**Two rounds, then a person.** Published results suggest repeated attempts raise the rate of cheating. A retry under pressure is a risk, not only a cost. Running out of budget never lands a leaf: two distinct-family approvals stay required. We keep those because different model families catch different things, while knowing they are one source of assurance, not the assurance itself.

**An honest exit is a control.** The strongest published mitigations are protected tests and a sanctioned way to stop. Agents take shortcuts more when the honest option is missing or costly, so executors are told that stopping is a good outcome.

**Why agents get different words from people.**

- *Framing.* Words like "attacker" and "exploit" set a frame, and negating them still puts them in front of the model. We want a reviewer checking evidence, not hunting for attacks. We have not measured this effect, but neutral wording costs nothing.
- *Menus.* A list of ways to fake success is a list of ways to fake success. Executors should not read one. The same goes for reviewers and exotic cases: naming them invites them. So agent briefs say what good looks like and what evidence is enough, and leave out catalogs.
- *People need the opposite.* A maintainer or adopter deciding what to trust needs the risk stated plainly. Softening this document would hide the risk from the people who accept it.
- *Neutral is not soft.* "Every review record comes from a real review" is neutral and strict. If rewording ever weakens a check, the rewording is wrong.

**Why plan for it, not only review for it.** The bar reviewers enforce is set when acceptance is written. Hostile wording in a planning sheet becomes a hostile review. So planning names each leaf's risk, what done-but-wrong looks like and the smallest check that tells them apart. That protects the requirement and leaves the implementation free.

**What is evidence and what is judgement.** Our incident history and round counts are facts from this repository. The published figures come from the research in `sr/docs/research/reports/goal-drift-governance-2026-11-07/`, whose citations have not been independently checked, and several are preprints. The framing effect and the two-round budget are judgement calls.

**What would change this.** Revisit it if an out-of-scope case is seen happening; if an escaped defect traces to a finding this bar dismissed; if leaves escalate so often that people become the bottleneck; or when isolation lands. Track review rounds per landed leaf, new blocks per round, how many blocks held up, escalations, and defects after landing.
