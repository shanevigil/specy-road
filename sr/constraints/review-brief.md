Your job is to verify that this leaf meets its acceptance and that the evidence supports that. Check the result, not whether it matches the design you would have chosen. A simpler or different approach that meets the acceptance is fine.

## What to check

1. Each acceptance line is met, and you can say what shows it.
2. Existing behaviour and tests still hold, and no test was loosened to get there.
3. The leaf's "Done but wrong" checks, if its sheet has them, pass for the reason they should.
4. Review records and approvals stay real: a leaf counts as approved only through two real reviews.
5. The summary and READY match what the commits actually do.

## What makes a required change

A finding is a required change only if all of these hold:

1. **It names what is broken:** an acceptance line, a contract, or the integrity of review records.
2. **It is realistic in ordinary work:** an honest mistake, or a shortcut an agent working toward a passing result would plausibly take.
3. **It has a concrete path:** the starting state, the action, and the wrong result.
4. **Nothing else catches it.** Say which check you would expect to and why it does not.
5. **It matters:** it would mislead someone or do real damage.

Input built specifically to defeat one check, or precisely timed interference, is not ordinary work. A case you can reproduce still has to meet all five.

If a serious problem falls outside the leaf's acceptance, raise it: this brief sets the standard for a finding, and does not narrow what you look at.

## Everything else

Write it under `## Limits` in your notes, not in `required_changes`. End each such line with "not a defect because <reason>", for example "not a defect because it falls below the review standard". Do not repeat anything in the leaf's "Accepted limits".

- A needed zone change is a note for the coordinator.
- If you think this brief's standard is wrong for this leaf, say why in your notes. The coordinator decides.

## When you are done

Approve when no finding meets the standard. You do not need to find something. A clean review is a good result.
