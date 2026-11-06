# Implementation summary: M21.30 — review policy pinned at claim

## What changed

- **A1 claim pin.** `do_next_task._finalize_pickup` builds the registration message with
  `review_policy_pin.pinned_message`, which appends (after a blank line, subject unchanged)
  `Review-policy: sha256:<hex> at <HEAD>` via the new `registration_pickup_commit.with_policy_trailer`.
  `policy_digest(root, ref)` hashes `json.dumps({roster, substitutions, policy, require_implementation_review_before_finish},
  sort_keys=True, separators=(",", ":"), default=str)` as committed at the ref (missing key = null, no defaults, no
  local overlay). A present but unparsable policy file exits 1 before `register_claim` (no registry write). Same
  message for `--local`. A repo with no commit at HEAD gets no trailer (nothing committed to pin).
- **A2 gate and finish.** `pin_of` reads the trailer of the newest commit reachable from the commit under review whose
  subject starts with `chore(rm-<codename>): register as in-progress`; no trailer → `None` (judged as today); a
  trailer present but unparsable (or naming an unknown commit) → gate problem. `pin_problem` compares with the digest at
  `policy_source` and honours a valid acceptance. `GateResult.policy_pin` is read by `passed` and listed in
  `problems()`, so handoff status, review list and `mark-implementation-reviewed --yes` refuse with no extra wiring.
  `change_lines` gives one line per roster add/remove (with entry), per changed property of a retained entry (sorted,
  including `public_key`), `substitutions changed`, `policy.<key> a -> b`, and the review switch; a fallback line
  covers order-only / missing-vs-empty differences. `finish_task._impl_review_or_exit` calls `pin_holds_or_exit`
  before `review_required`, so turning the switch off after the claim still refuses before any bookkeeping.
- **A3 accept-policy.** `specy-road review accept-policy <ID> [--ref]` (parser registered in review_cli.py, logic in
  the pin module): refuses without a TTY ("a human accepts a review policy change in a terminal; nothing was
  written"), prints the change lines, asks for the node id typed back, and writes
  `work/reviews/<ID>/POLICY-ACCEPTED.yaml` (node_id, pinned_sha256, accepted_sha256, user, at) under the leaf's
  review filing lock (as `review record` takes it, M21.27). Read back against the new
  `specy_road/schemas/policy-acceptance.schema.json`; malformed, schema-invalid or other-node files are gate problems
  (noted in the message), and an acceptance counts only for the exact pinned and accepted digests.
- **Beyond the brief (coordinator-approved to keep):** `review_gate.human_approval_completes` returns False while
  `policy_pin` is set, so the interactive human approval does not write a REVIEW-human.md that the gate would then
  refuse.
- **A5 docs.** Review rule in `agents-rules.md` and the managed block (provenance comments extended);
  `docs/orchestration-review.md` section "Review policy pinned at claim" (honour-system like READY; M22.5 the broader
  guard); CHANGELOG [Unreleased] Fixed, **Security** entry.
- **Budgets.** Per coordinator decision, `tests/test_enforced_rules_pointers.py` (added to zones) raises
  `_STUB_BYTES` 2063 → 2205 and `_RULES_BYTES` 9107 → 9289, exactly the new sizes, with a comment citing M21.30 and
  the maintainer approval; line counts unchanged.

## Fix round 1 (review at b7ec601a, gpt-6.1-sol-low)

- **R1 — class: a validation skipped by an early return (an invalid acceptance file ignored whenever the policy
  matches the pin).** Design change, not a patch: `pin_problem` now reads `POLICY-ACCEPTED.yaml` first, and one rule
  applies: an existing but invalid file (malformed, schema-invalid, another node) is a gate problem whatever the pin
  and the policy say. The message tells the human to delete it and re-run `review accept-policy` if the policy
  changed. The old in-message "(invalid…)" note branch is gone, so the function has no extra branch. A valid file
  still counts only for its two digests. Acceptance table gains the three invalid shapes with the policy unchanged.
- **R2 — class: a test asserting a call list instead of effects.** The `calls == []` assertion is removed; the
  unparsable-policy pickup case now asserts exit 1, the registry bytes unchanged, and the real `git log` unchanged
  with no registration subject.

## Probes

- Invalid acceptance + policy unchanged (malformed / schema-invalid / other node): gate problem; without the fix
  these three rows fail (red-green, 3 failed), with it they pass.
- Invalid acceptance + policy changed: gate problem (same rule, message now the invalid-file one).
- Valid acceptance whose digests no longer match (pinned, accepted, second edit): still the "policy changed" problem.
- Other validations behind an early return: `pin_of` parses the trailer before any digest comparison, so an
  unparsable trailer is a problem whether or not the policy changed; `policy_digest` raises on an unparsable policy
  file at the ref before the comparison. Unpinned (legacy) claims skip the digest by design (judged as today).
- `accept-policy` on an invalid file with the policy changed: overwrites it with a valid record (the existing write
  path); with the policy unchanged it writes nothing and the gate message names the file to delete.
- Other call-list assertions added by this leaf: none in tests/test_review_policy_pin.py; the pickup test's
  commit-message checks (`calls[1][2]`) follow the existing test's own pattern for the message pickup builds, the
  behaviour under test, with git faked.

## Fix round 2 (review at e7f7f381, gpt-6.1-sol-low)

- **R1 — class: committed policy of the wrong shape reaching code that assumes structure.** One bounded rule, in
  the one reader every path uses (`policy_parts`, docstring): `roster` is null or a list of mappings and `policy` is
  null or a mapping; anything else raises `PolicyUnreadable`. `substitutions` and the review switch are hashed and
  compared as written (their change lines need no structure). `_pin_state` now also computes the change lines, so
  every read of committed policy sits inside one `PolicyUnreadable` boundary for the gate, finish and accept-policy
  (accept-policy used to call `change_lines` outside its try). The `isinstance(e, dict)` filters in `change_lines`
  are gone, now that the rule guarantees mappings. At claim the same rule refuses pickup (exit 1, no registry write).
  Limit (documented): roster entries are keyed by `id`; duplicate ids collapse in the change lines, but the digest
  still differs and the fallback line names it.
- **R2 — class: a multi-change diagnostic flattened onto one line.** The problem is now a header line, one indented
  line per change, and the accept-policy hint on its own line, in the gate (`problems()`), `mark-implementation-
  reviewed`, handoff/review list and finish. accept-policy already printed one line per change.
- **R3 — class: asserting a position in a mocked git call list.** With a committed policy, the pickup test now runs
  real git and reads the registration commit back (`git log --grep` on the subject): subject, blank line, trailer
  with the digest at the commit claimed from. The no-commit case keeps the pre-existing test's own assertion as it
  was before this leaf.

## Probes (fix round 2)

- `policy: 1` committed after the claim: gate problem "policy is not a mapping" (was AttributeError); red-green 1 failed before.
- `roster: [1]` committed after the claim: gate problem "roster is not a list of mappings"; red-green failed before.
- Same shapes at claim time: `pinned_message` exits 1 before `register_claim` (same `PolicyUnreadable` path as a parse error).
- Same shapes through `review accept-policy`: caught by its `PolicyUnreadable` handler (change lines now inside `_pin_state`), "nothing was written".
- Same shapes through finish: `pin_holds_or_exit` → `pin_problem` → one boundary; exit 1, no traceback.
- `substitutions` and the review switch of any shape: only `_encode`d and compared, no structural access — no crash path.
- Whole file not a mapping or not parsing: already `PolicyUnreadable` in `_yaml_at` (round 0 rows still pass).
- Two changes at once (roles + `policy.reviewers_required`): each on its own line in the gate problem; red-green failed before.
- Other call-position asserts added by this leaf: the pinned pickup case now reads git; tests/test_review_policy_pin.py has none.

## Fix round 3 (review at ce2a4def, gpt-6.1-sol-low)

- **Class (R1, R2): a read or parse boundary that catches only some of the errors its input can raise, so an
  unreadable input crashed — or, at the git boundary, read as absent and skipped the check.** One rule for each
  boundary, used everywhere:
  - `load_yaml` (public, docstring states the rule): UTF-8 decode then `yaml.safe_load`; `yaml.YAMLError`,
    `ValueError` (covers `UnicodeDecodeError` and an impossible unquoted date such as `2026-99-99`) and
    `RecursionError` all raise `PolicyUnreadable`. Committed policy (`_yaml_at`) and `POLICY-ACCEPTED.yaml`
    (`read_acceptance`, now reading bytes) both go through it; the acceptance turns it into the invalid-acceptance
    result.
  - `_git_read`: git output is `None` only when git ran and exited non-zero (path or commit not there); output git
    could not deliver or decode (`GitResult.failure`) raises `PolicyUnreadable`. Used by `_yaml_at` and both git
    reads in `pin_of`. Found by the class audit: a committed policy with non-UTF-8 bytes used to be read as
    *missing* (every key null), and an undecodable registration commit message as *no trailer* (judged as today) —
    both fail-open.
  - Limit (documented in the docstrings): the rule covers decode and YAML construction; it does not try to bound
    resource use on hostile input beyond Python's recursion limit.

## Probes (fix round 3)

- Impossible unquoted date committed in substitutions after the claim: gate problem "cannot be checked"; red-green failed before (traceback).
- Non-UTF-8 bytes in the committed policy after the claim: gate problem; red-green failed before (gate *passed*: read as absent).
- Acceptance file with `at: 2026-99-99`: invalid-acceptance problem; red-green failed before (ValueError).
- Acceptance file with non-UTF-8 bytes: invalid-acceptance problem; red-green failed before (UnicodeDecodeError).
- Claim with an impossible date at HEAD: `pinned_message` exits 1, "nothing was registered" (probe script).
- Claim with non-UTF-8 committed policy at HEAD: exits 1 naming the unreadable `git show` output (probe script).
- `review accept-policy` with either bad policy: `_pin_state` raises `PolicyUnreadable` inside its handler — "nothing was written".
- finish: `pin_holds_or_exit` → `pin_problem` → same boundary; exit 1, no traceback.
- `pin_of` git reads: undecodable log or commit body now raises instead of reading as "no registration commit"/"no trailer".
- Other parse sites in the leaf: none (`_SCHEMA` is the bundled schema; `git_text` remains only for `git config user.*` in `_user`, where a failure falls back to the login name).

## Fix round 4 (coordinator: one rule for unreadable input)

- **Rule (module docstring, `_unreadable_as`, `UNREADABLE`).** Two input boundaries: the committed policy (git read,
  decode, YAML load, shape check, digest, change lines — `_yaml_at`, `policy_digest`, `_pin_state`) and
  `POLICY-ACCEPTED.yaml` (`read_acceptance`: file read, decode, YAML load, schema, node id). Inside either, any of
  `OSError`, `ValueError` (incl. `UnicodeDecodeError` and YAML constructor errors such as `2026-99-99`), `TypeError`,
  `AttributeError`, `RecursionError`, `yaml.YAMLError` becomes `PolicyUnreadable` (acceptance: the
  invalid-acceptance result); a `PolicyUnreadable` raised inside passes through. Replaces round 3's `load_yaml`
  (removed) and the separate except clauses; `_git_read` stays (a git output failure is never read as absent). The
  acceptance check now uses `exists()`, so a directory in its place is unreadable, not absent. Limit: other
  exception types (e.g. `MemoryError`) are not caught; the toolkit's other readers keep their own rules (below).
- **Tests.** One table, `UNREADABLE_KINDS` × {committed policy, acceptance file} (16 cells): impossible unquoted
  date, non-UTF-8 bytes, YAML syntax error, wrong top-level type, wrong shape inside, mixed-type keys, deeply nested
  input, unreadable file (a directory in its place). Each cell: gate not passed with the pin problem;
  `mark-implementation-reviewed --yes` and `finish-this-task` exit 1; for the policy cells `review accept-policy`
  exits 1 writing nothing and a claim (`pinned_message`) exits 1; no traceback; tree unchanged. The per-case rows
  from rounds 2–3 (parse error, impossible date, non-UTF-8, policy/roster shape; malformed/date/non-UTF-8
  acceptance) are removed — covered by the table. Schema-invalid, other-node, digest-mismatch and second-edit rows stay.

### Readers outside the pin module (coordinator-approved zones)

The table's `deeply nested input in committed policy` cell first failed outside the pin boundary: the gate reads the
same committed files earlier through `orchestration_config.parse_orchestration_text` (via `effective_config` in
`evaluate_gate`) and `review_policy_ref.committed_yaml` (via `policy_source` / `review_required`), which let
`RecursionError` escape. With the coordinator's approval both files were added to the zones, and only their except
clauses were widened to the same tuple as `review_policy_pin.UNREADABLE`, written out literally with a comment
naming it: `review_policy_pin` imports `review_policy_ref`, so importing the tuple would be circular. Deep nesting
now takes each reader's existing path (the configuration error; `committed_yaml`'s `{}`), never a traceback.

## Probes (fix round 4)

- All 8 kinds × acceptance file: gate problem, finish/mark exit 1, no traceback (table, pass).
- 7 of 8 kinds × committed policy: gate problem, finish/mark/accept-policy/claim exit 1, no traceback (table, pass).
- Deep nesting × committed policy, pin boundary alone: `PolicyUnreadable` (probe script).
- Deep nesting × committed policy, `effective_config`: uncaught `RecursionError` before the widening; now the existing configuration error (table cell passes).
- Deep nesting × committed `git-workflow.yaml`, `committed_yaml`: uncaught `RecursionError` before the widening; now `{}` as for any unparsable copy.
- Full table after widening: 16/16 cells pass.
- Mixed-type keys (`policy: {1: a, b: c}`): `json.dumps(sort_keys=True)` `TypeError` inside the digest → `PolicyUnreadable` (table, pass).
- Other parse sites in the leaf: `_SCHEMA` (bundled, read inside the acceptance boundary); `git_text` only in `_user`.

## Final touch zones

As listed in the brief plus `tests/test_enforced_rules_pointers.py` (budgets), and `specy_road/orchestration_config.py` and `specy_road/review_policy_ref.py` (one except clause each, fix round 4). No other path changed.

## Verification

- Fix round 4: targeted (plus tests/test_orchestration_config.py) 189 passed; unreadable-input table 16/16; full suite 5731 passed; `ruff check specy_road tests scripts` clean; file-limits OK.
- Fix round 3: targeted 163 passed; `ruff check specy_road tests scripts` clean; file-limits OK.
- Fix round 2: targeted 159 passed; `ruff check specy_road tests scripts` clean; file-limits OK.
- Fix round 1: targeted 156 passed; `ruff check specy_road tests scripts` clean; file-limits OK.
- `pytest -n 4` targeted (pin, pickup, rules budgets, AGENTS block, file limits, gate, mark-reviewed, delegate,
  ready-author, gate agreement): 153 passed. Full suite `pytest -n 4`: 5714 passed.
- `ruff check` on changed Python: clean. `specy-road file-limits`: OK (review_gate.py 404, orchestration-review.md
  430, under the 1,000 cap).

## Added

- `specy_road/review_policy_pin.py`: `policy_parts`/`policy_digest` — the A1 digest, one helper for any ref.
- Widened except clauses in `orchestration_config.parse_orchestration_text` and `review_policy_ref.committed_yaml` (fix round 4) — same tuple, so no reader of the committed policy tracebacks.
- `_unreadable_as` + `UNREADABLE` (fix round 4) — the module's one rule for unreadable input at both boundaries.
- `_git_read` (fix round 3; round 3's `load_yaml` removed in round 4) — one parse rule and one git-read rule, so no unreadable input crashes or reads as absent.
- `_yaml_at` + `PolicyUnreadable` — strict read (committed_yaml returns `{}` on a parse error, which must never hash as empty).
- `pinned_message` — the pickup call site's trailer; exits 1 on an unparsable policy before any registry write.
- `pinned_message` no-HEAD guard — a repo with no commit has nothing to pin (keeps existing pickup tests exact).
- `policy_parts` shape rule (fix round 2, R1) — roster a list of mappings, policy a mapping, else `PolicyUnreadable`.
- `pin_of` — trailer lookup on the newest registration commit (startswith, so the CI-skip suffix matches).
- `change_lines` (+ fallback line) — A2's per-change lines; fallback so a digest change is never reported with no line.
- `read_acceptance`/`acceptance_path` — A3 file read with schema check; invalid is a problem, never an acceptance.
- `pin_problem` invalid-acceptance rule (fix round 1, R1) — checked first, so no pin state skips it.
- `_pin_state`, `pin_problem` — shared by the gate, finish and accept-policy.
- `pin_holds_or_exit` — finish's one call (exit 1, message on stderr).
- `cmd_accept_policy`, `add_parser`, `_user` — the A3 command; `_user` names the git user (fallback: login name).
- `registration_pickup_commit.with_policy_trailer` — trailer after a blank line, subject unchanged.
- `specy_road/schemas/policy-acceptance.schema.json` — A3 schema.
- `GateResult.policy_pin` field, `passed`/`problems()` reading it, and the `human_approval_completes` guard.
- `tests/test_review_policy_pin.py`: claim-pins test; gate table (unchanged, CR1 roles, public_key, quoted dates,
  unparsable policy); CR1 mark-reviewed/finish write-nothing; switch-off finish; accept-policy TTY/no-TTY/wrong id;
  acceptance table (malformed, schema-invalid, other node, both digest mismatches, second edit); trailer table
  (unpinned, unparsable); review delegate on a pinned claim. Mocks: `sys.stdin.isatty` and `builtins.input` only.
- `tests/test_do_next_task_pickup.py`: existing CI-skip-free pickup test parametrized over no commit / pinned /
  unparsable policy (exact trailer through `_finalize_pickup`; exit 1 with the registry and `git log` unchanged —
  fix round 1, R2; helper `_git_log` reads the real log).
- `UNREADABLE_KINDS` table test (fix round 4) replaces the round 2–3 per-case unreadable rows; `_write` puts bytes, text or a directory at a path, used by `_on_dev` and the acceptance cells.
- Gate table rows (fix round 2): policy not a mapping, roster not a list of mappings, one line per change.
- Pickup test pinned case runs real git and reads the claim commit back (fix round 2, R3).
- Acceptance table rows (fix round 1, R1): malformed, schema-invalid and other-node files with the policy unchanged.
- `tests/test_enforced_rules_pointers.py`: two budget constants raised with comments (maintainer-approved).
