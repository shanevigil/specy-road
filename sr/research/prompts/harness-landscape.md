# Deep research: the harness and orchestration landscape around specy-road

## Who is asking and why

specy-road is an open-source toolkit that coordinates coding agents through a git-tracked roadmap. It
builds its own harness layer: it launches and resumes the vendor coding CLIs (Claude Code, Codex CLI,
Cursor `agent`) on the user's own subscription logins, parses their streams, normalises usage, leases
worker slots, guards tool calls and checks each run afterwards. It keeps watching how other systems do
the same job, for two reasons: keep its shapes close to proven ones (parity), and know when a
maintained package should replace part of the layer (buy vs build).

Treat the present date as the run date. Cite a primary source (vendor docs, repository, release notes)
for every fact, with the version or date it applies to; label anything you cannot source `unverified`.

## Read first

`docs/research/harness-landscape.md` in this repository: its watchlist (one row per system with what to
watch for), its triggers that reopen buy vs build, its risks, and the log of earlier runs. Start from
the last log entry; report only what changed since then.

## What to establish

1. **Watchlist.** For each entry, what changed since the last run that matches its "watch for" column:
   releases, licence or maintenance status, new modes, deprecations. Say "no relevant change" where
   that is the finding.
2. **Triggers.** For each buy-vs-build trigger, whether it fired, with the evidence.
3. **Risks.** Whether each listed risk moved (for example, a CLI changing its headless default, or a
   vendor's policy on subscription logins for headless or SDK use).
4. **New entrants.** At most three systems not on the watchlist that do the same job (drive several
   coding-agent CLIs, or orchestrate agent runs locally without a daemon), with one line each on why
   they matter and whether to add them.

## Output

A dated report with one section per item above, then a short list of proposed changes: watchlist rows
to add or drop, and findings that need roadmap work (each as one sentence a planner can turn into a
leaf). Do not propose code.
