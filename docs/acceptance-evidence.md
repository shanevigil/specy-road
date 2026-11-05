# Acceptance evidence: authorizing a test change

A leaf may remove or weaken a test only when its node lists that change in
`planned_test_changes`, each item a finding line exactly as `specy-road integrity`
prints it:

```text
removed-test: tests/test_x.py::test_old
removed-test-file: tests/test_gone.py
new-skip: tests/test_x.py::test_slow
assert-loss: tests/test_x.py::test_ok 2->1
```

(`preserve: <path>::<name>` items are red-green declarations; see
[`orchestration-review.md`](orchestration-review.md).)

## Before pickup

Author the list with the leaf, and approve it with the rest of the node.

## After pickup

An acceptance item sometimes reverses behaviour an existing test pins, and that only
becomes clear once the work has started. The owner authorizes the change with
`edit-node`. Like the other list fields, it takes `--set` (one per item, an empty value
removes the field), `--add` and `--remove`:

```bash
specy-road edit-node M3.4 --add 'planned_test_changes=removed-test: tests/test_x.py::test_old'
```

Make the edit in one of two places:

- **On the integration branch.** This is the only place `policy.integrity_gate` reads
  the list from, so the gate counts the change as declared. An executor's worktree
  can't waive its own finding.
- **On the leaf branch.** The edit is committed with the change and reviewed with the
  diff: `review-packet` lists the roadmap chunk under changed paths, and reviewers see
  who authorized what. The required check below reads this list too. With
  `policy.integrity_gate` on, the gate still needs the line on the integration branch.

## Unplanned removals are a required reviewer check

`review-packet` checks every `removed-test`, `removed-test-file`, `new-skip` and
`assert-loss` finding against `planned_test_changes`, taken from both the integration
branch and the commit under review. Any finding that neither lists goes under
**Required check: unplanned test removal**, whatever `policy.integrity_gate` says. The
reviewer prompt says the same thing.

An approving review record needs one `acceptance` entry per such line, keyed by the line
exactly:

```yaml
acceptance:
  A1: pass
  "removed-test: tests/test_x.py::test_old": pass
```

Give the entry only when an acceptance item and the diff justify the change. If they
don't, block with a `required_changes` entry (the entry accepts only `pass`). `review
record` refuses an approve that omits an entry and names the test. A block needs no
entry.
