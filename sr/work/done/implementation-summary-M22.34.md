# Implementation summary: M22.34 — One accept-policy prompt covers every open claim

Branch `feature/rm-accept-policy-for-all-open-claims`, base `6749dbcb22a20a497105c020cc4e6a3a9626a5c7`.

## What changed

- **A1.** `specy-road review accept-policy --all-open` reads the registry, keeps every open claim whose pinned review policy differs from the integration branch, and prints each distinct set of change lines once with the leaves it affects (and each leaf's pinned and accepted digests). One typed confirmation — the sorted node ids — writes each of those leaves its own `work/reviews/<NODE_ID>/POLICY-ACCEPTED.yaml` naming that leaf's pinned digest and the accepted digest.
- **A2.** It still needs a terminal. An acceptance is still one node and two digests, so a later policy change needs a new one (the existing digest tests still pass). `review accept-policy <NODE_ID>` still asks for that node id and writes the same file. `--ref` stays on the single-node form; with `--all-open` it is refused, because each claim is read on its registered branch.
- **A3.** `tests/test_review_policy_pin.py` covers two leaves pinned to different digests (M1.1 against M1.2 and M1.4, which share a pin and so one printed change set), a leaf with no change (M1.3, not listed and no file), a refusal without a terminal, and a wrong confirmation. `docs/orchestration-review.md` describes `--all-open`. `CHANGELOG.md` `[Unreleased]` / `### Added` records it.
- **A4.** The accept-policy prompt and the gate refusal (`pin_problem`) both say, in plain language, what changed, that the review rules changed after this work started, and what approving covers. The raw change lines stay below that paragraph. Both name `specy_road.review_policy_pin`, which ships in the wheel (`docs/` does not).
- **A5.** `docs/orchestration-review.md` gains "What the review-policy fingerprint covers": what is fingerprinted, why a match passes with no human, when a person is asked, what an acceptance covers, and how to decline by re-claiming the leaf.

## Touch zones

Declared: `specy_road/review_policy_pin.py`, `specy_road/bundled_scripts/review_cli.py`, `docs/orchestration-review.md`, `tests/test_review_policy_pin.py`, `CHANGELOG.md`.

Those are the final zones. `review_cli.py` only gains a sentence in its module docstring: the parser is registered by `review_policy_pin.add_parser`, which already runs from `review_cli`. Callers outside the zones (`do_next_task.py`, `finish_task.py`, `review_gate.py`) already print `pin_problem` and did not need an edit. No path outside the zones needed a change. The roadmap zone list was not edited.

## Verification

- `pytest -n 4 tests/test_review_policy_pin.py`: 36 passed.
- `ruff check` on the two Python files: passed (complexity included).
- `specy-road file-limits`: OK. Existing hard-alert warnings only, on files this leaf does not touch.

## Added

### Helpers

- `_asked_because` — the plain-language paragraph (what changed, why a person is asked, what approving covers, and `specy_road.review_policy_pin`) shared by the prompt and the gate refusal.
- `_policy_refusal` — the gate refusal: that paragraph, then each raw change line, then the existing accept hint.
- `_open_policy_changes` — open registry claims whose pinned digest differs from the integration branch.
- `_change_groups` — group those claims by their change lines so each distinct set is printed once.
- `_print_groups` — print the groups, each leaf's two digests, and the change lines once per set.
- `_write_acceptances` — write one `POLICY-ACCEPTED.yaml` per leaf after taking every leaf's review lock, so a held lock writes nothing.
- `_accept_one` — the single-node flow: same confirmation token and file shape, with the plain-language paragraph above the raw lines.
- `_accept_all` — `--all-open`: print the groups, require the sorted node ids typed back once, then write one file per listed leaf.
- `_usage_error` — refuse neither a node id nor `--all-open`, both of them, or `--ref` together with `--all-open`.
- `INSTALLED_REFERENCE` — the module name the prompt and the refusal cite, because that module is in the installed package.

### Branches or guards

- No terminal: the existing refusal, before any resolve or write.
- A node id and `--all-open` both passed, or neither: error, nothing written.
- `--all-open` with `--ref`: error, nothing written. `--ref` names one commit; `--all-open` uses each claim's registered branch.
- A registry row that is not a mapping or has no node id: skipped. It is not an open claim.
- A claim whose pin matches, or that was never pinned: omitted from `--all-open`. The single-node form still says there is nothing to accept.
- No open claim differs: `--all-open` exits 0 and writes nothing.
- The typed confirmation does not match: nothing written, same sentence as one node.
- A leaf's review lock is held: nothing written. Every lock is taken before the first write.
- `ReviewTargetError` or `PolicyUnreadable`: one handler on `cmd_accept_policy`, nothing written. The existing unreadable-policy test reaches it through the single-node form.

### Mocks

- none. The new test patches `sys.stdin.isatty` and `builtins.input`, as the existing accept-policy test does.

### Tests

- `test_accept_policy_all_open_groups_each_change_once` — two pinned digests, one shared change set printed once for the two leaves on that pin, a leaf whose pin matches and is omitted, no terminal, a node id together with `--all-open`, neither, `--ref` with `--all-open`, a wrong confirmation, then one confirmation writing each changed leaf its own file with that leaf's two digests.
- `test_cr1_change_refuses_mark_reviewed_and_finish_writing_nothing` — also asserts the gate refusal names the review-rules sentence and `specy_road.review_policy_pin` above the raw change line.
- `test_accept_policy_needs_a_terminal_then_the_gate_passes` — also asserts the single-node prompt does the same.
