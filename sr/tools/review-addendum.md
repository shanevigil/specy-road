
---
Coordinator addendum (specy-road's own grind). specy-road files your review from your FINAL message in one shot; a
record it refuses costs a whole rerun. Before you send the final message, check every line of your notes:
- A line of two words or more that is not a heading, a bare acceptance result ("A1: pass") or a table separator is an
  observation. It must EITHER match a required_changes entry (and then the verdict is block) OR carry, on that same
  line, the words "not a defect because <reason>".
- A line that uses a defect word (fails, broken, bug, corrupt, crash, wrong, missing, regression, ...) needs the same,
  even inside a longer sentence. Each clause split on ". ", "; " or " and " is checked on its own.
- On an approve, every findings entry also needs "not a defect because <reason>".
Write ONE observation per line. A list joined by commas ("no X, Y or Z were added") counts as several observations, each needing its
own reason: split such a list into separate lines, each ending with its own "not a defect because <reason>".
Keep the notes short: fewer lines, fewer refusals. Evidence goes in commands_rerun, not in free prose.
Sandboxed test runs: FastAPI TestClient suites (tests/test_gui_*.py, tests/test_roadmap_gui_*.py,
tests/test_gui_outline_contract.py) stall in some reviewer sandboxes. When the leaf's READY file records those suites run
by `specy-road ready --run` at the reviewed commit with exit 0, that recorded run is the verification: cite it in
commands_rerun. Your own rerun timing out is an environment limit, not a defect; do not block on it. Block only if the
recorded run is missing, not at this commit, or not exit 0, or if you find a product cause.
List every required change that meets the review standard below in one pass, so a real problem does not cost a second round.

Review rules v2 (operator-approved 2026-11-11): structured fields in your notes file. They go in ONE fenced block that
opens with a line ```review-fields and closes with ``` (fenced code is not read as observations). YAML inside:
- `findings:` one entry for EVERY blocking finding (every required change), with `finding` (a few words), `lens`
  (correctness | regression | boundary | test_integrity), `input_class` (the class of input that triggers it),
  `locations` (a list of one or more `path:line`), and `acceptance_id` or `risk` (security | data_loss |
  gate_integrity | test_integrity | none); write `risk: none` when you judge no named risk applies. A finding without
  an acceptance id still blocks. Nothing is downgraded to a suggestion.
- Round 1 (the "Rules v2 context" says so): add `inventory:`, one entry per input boundary you checked, with
  `boundary` and `classes` (each class you saw, marked handled or unhandled). Every unhandled class is also a blocking
  finding under `findings`.
- Round 2 on, when the "Rules v2 context" lists trust paths in the fix diff: add `fix_trust: none | tightens | weakens |
  unclear`, on an approve too. Judge the fix by paths (does it change a trust-path file?) and by behaviour (does it add,
  keep, weaken or remove a check, refusal, guard, permission, secret, network or review-gate behaviour?): none = it
  touches no trust path; tightens = it touches one but only adds or keeps checks; otherwise weakens or unclear.
The "Rules v2 context" is the last section of PACKET.md, and also sr/work/reviews/<NODE_ID>/rules-v2-context.md (read
it there when you review from a delta packet). Example:
```review-fields
findings:
  - finding: empty registry list aborts the loader
    lens: boundary
    input_class: empty list
    locations: [specy_road/example.py:42]
    acceptance_id: A2
inventory:
  - boundary: registry loader
    classes: {missing file: handled, empty list: unhandled}
```
