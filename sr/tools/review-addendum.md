
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
