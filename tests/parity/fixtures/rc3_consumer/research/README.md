# Research register

Deep-research topics this project reruns on a schedule — the state of a dependency, a vendor's
API, the models and harnesses the team uses. One **register entry** per topic records why it is
run, which prompt runs it, how often, when it last ran and what it changed.

## Layout

- `research/<topic>.md` — the register entry: YAML front matter, then free notes on past runs.
- `research/prompts/<topic>.md` — the prompt you hand to a deep-research tool.

Prompts are tracked here, **not** under `work/`: `work/` holds session scratch, part of it is
gitignored and `finish-this-task` cleans it, so a prompt left there is lost or never shared.
Every Markdown file directly under `research/` other than this README is read as an entry.

## Entry fields

```yaml
---
purpose: Keep our payment-provider integration current with the provider's API changes
prompt: research/prompts/payment-provider-api.md
cadence_days: 90          # rerun after this many days
last_run: 2026-10-31      # YYYY-MM-DD; leave empty until the first run
fed: [M4.2, M4.3]         # roadmap nodes the findings created or changed
---
```

`prompt` is a path from the project root and must name a file under `research/`. Where the
natural cadence is an event ("each minor release"), choose the days that approximate it and say
so in `purpose`.

`specy-road validate` warns when an entry is past its cadence (or has never run), when its
prompt file does not exist or is outside `research/`, and when `cadence_days` or `last_run` cannot
be read.

## Folding findings back in

Research only matters once it reaches the roadmap: **research → brainstorm → promote**.

1. Run the entry's prompt in your deep-research tool and keep the report.
2. Start a brainstorm on it — `specy-road brainstorm start --topic "<topic> findings" --under <ID>`
   — and add each actionable finding as an idea (`--kind research` where it needs more work),
   and record the report's sources with `add-evidence` (a verbatim `--quote`, not just a URL).
   Triage as usual: `recommend`, `evidence` / `verify`, then `accept`, `reject --reason` or `park`.
3. `specy-road brainstorm promote` writes the accepted ideas as roadmap nodes.
4. Update the entry: set `last_run` to the run date and add the promoted (or edited) node ids to
   `fed`, so the next run starts from what the last one changed.
