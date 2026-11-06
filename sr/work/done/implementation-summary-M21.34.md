# M21.34 implementation summary

CR2 in `docs/context-regressions.yaml` changed; nothing else.

- **A1:** the prompt now asks for a short "Running the tests" README section with the command that runs the tests. App, setup, harnesses and runs are unchanged.
- **A2:** the first pass item records `git rev-list --all --reflog` and `git worktree list --porcelain` before and after the session, and runs `git show --name-only` on each newly reachable commit object. It expects exactly one new commit, README.md only, on the checkout's branch or on the branch of a worktree path absent from the before list; anything else fails the run. The second item and the AGENTS "Shared checkouts" rule are unchanged.
- **A3:** still ten cases at most; `tests/test_context_regressions.py` passes with its schema unchanged, so that file was not edited.
- **A4 (informational):** net +8 lines against the +4 estimate; the item is wrapped to the file's width and spells out the set difference.

Touch zones confirmed: only `docs/context-regressions.yaml` needed a change. `tests/test_context_regressions.py` stayed as it is. CR3's `setup: As CR2, ...` still reads correctly because the setup did not change.

Checked in a scratch repo (not a verifier): a backdated commit on a new branch in a linked worktree shows in the before/after `rev-list` difference, the worktree appears in the `worktree list` difference, and the commit stays in the difference after a `reset --hard` drops it from the branch.

Not run: a §9 replay of CR2 on the harnesses, which this leaf does not ask for.

## Added

- Helpers: none
- Branches or guards: none
- Mocks: none
- Tests: none (the existing schema test covers the changed case)
