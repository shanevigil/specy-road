# M22.56 — Neutral identities in tests

## Summary

The two zoned tests named the maintainer. Those literals are now neutral, and every assertion still compares a stored value to the literal that test wrote.

- `tests/test_claim_traps.py`: the registry owner and the git user name are `Test User` (the claim row, the assertion on that row, the `git_config_user_name` stand-in, and the pickup assertion).
- `tests/test_review_record_caller.py`: the human-filer value is `alice` in both parametrized cases and in the signed case (the `--human-filed` argument and the assertion against the same literal). The existing `Alice` attestation case is unchanged.

No test was added or removed, and the parametrized case lists have the same length. No other test file changed. Nothing outside the touch zones was required: a whole-word scan of tracked files under `tests/` and `specy_road/` found these strings only in the two zoned files.

## Touch zones

Final list, unchanged: `tests/test_claim_traps.py`, `tests/test_review_record_caller.py`. No Python module imports either file.

## Acceptance

- **A1.** Both files use `Test User` and `alice` where they named the maintainer. Each edited line is that literal or an assertion against the same literal.
- **A2.** Whole-word, case-insensitive match of the runtime tokens against tracked files under `tests/` and `specy_road/`: the login name (`getpass.getuser()`), and alphabetic words of at least two letters from `git config user.name` and the local-part of `git config user.email`. M22.54's untracked local list and CI secret are both unset, so those sources contribute nothing. A match that sits inside a `github.com/<origin-owner>/` URL is not a hit. Result: 3 tokens, 0 hits.

## Tests

- `pytest -q tests/test_claim_traps.py --tb=short` — 5 passed
- `pytest -q tests/test_review_record_caller.py --tb=short` — 34 passed

## Added

### Helpers

none

### Branches or guards

none

### Mocks

none

### Tests

none
