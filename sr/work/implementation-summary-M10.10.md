# Implementation summary — M10.10

## Summary

Docs only. **A1:** `docs/philosophy-and-scope.md` gains `## Where specy-road sits` (placed after "What specy-road is opinionated about", before "What specy-road does not prescribe"). It states that driving coding-agent CLIs as workers is no longer rare, names Microsoft Agent Framework, LiteLLM's harness feature and Bernstein, each with a primary URL and "read 2026-10-30", and lists the four commitments that together are specy-road's: the roadmap graph in the repo; separated roles with fresh-session distinct-family reviewers; reviews bound to a commit; tracked files plus shell commands as the only surface. **A2:** `README.md` "Why teams use it" gains one bullet, "Governance, not another agent runner", linking the new section; the "What it is" paragraph is untouched. **A3:** the opening paragraph of `docs/orchestration.md` gains one sentence pointing at the section. **A4:** every statement about a neighbour is quoted or paraphrased from that tool's own documentation as fetched on 2026-10-30 (see Sources below); none of the section 5 secondary claims of `docs/design-notes/agent-performance-research-triage.md` appear (grep of added lines for `32,800`, `43%`, `14%`, `--bare`, `EFFORT_LEVEL`, Systima, Linux: none).

Implementation code landed in commit `6389ccaf3eb0008e2fd5c354833f92391815a70a`.

## Sources used for A4

- Microsoft Agent Framework — <https://github.com/microsoft/agent-framework>; package READMEs `python/packages/claude/README.md` ("enables integration with Claude Agent SDK ... agentic capabilities through the Agent Framework", `pip install agent-framework-claude --pre`) and `python/packages/github_copilot/README.md` ("enables integration with GitHub Copilot"). The Learn overview page and the repo README do not mention these agents, so the section cites the package path.
- LiteLLM harness — <https://docs.litellm.ai/docs/harness>; both B64 quotes ("drive Claude Code, Codex, OpenCode, Deep Agents or Tool Loop from Python with one API"; "litellm.agent() is in beta. The API may change between releases.") re-confirmed on the live page.
- Bernstein — <https://github.com/saketh-bandi/bernstein>. Its README has been rewritten since the B64 quotes were taken: it now calls itself "the open-source governance layer for AI agents" with "a deterministic scheduler - no model in the coordination loop", CLI coding agents "(Claude Code, Codex, Gemini CLI, and 40+ more)", and "each coding task gets its own git worktree behind merge gates". The section paraphrases the current wording. Because Bernstein now describes itself as a governance layer, the section does **not** claim the neighbours lack governance; it states specy-road's four commitments as a combination and tells readers which axis to evaluate on.

## Touch zones (confirmed)

`docs/philosophy-and-scope.md`, `README.md`, `docs/orchestration.md` — accurate; no additions or removals. No CHANGELOG or what's-new entry (M6.1 owns release notes).

## Verification

```bash
specy-road validate            # OK: roadmap and registry validate.
specy-road file-limits         # OK: file limits satisfied. (orchestration.md stays 325 lines, cap 400)
for u in <the four URLs in the diff>; do curl -sIL -o /dev/null -w "%{http_code}\n" "$u"; done   # 200 x4
python -m pytest -q tests/test_review_round6_docs.py tests/test_shared_checkout_guidance.py      # 15 passed
python -m pytest -q tests/test_*doc*.py                                                            # 25 passed
```

## Added

- `## Where specy-road sits` section in `docs/philosophy-and-scope.md` — A1: neighbours with primary URLs and read date, then the four commitments.
- "Governance, not another agent runner" bullet in `README.md` "Why teams use it" — A2: positioning line linking the section.
- One sentence at the end of the `docs/orchestration.md` opening paragraph — A3: pointer to the section.
- Helpers, branches or guards: none.
- Mocks: none.
- Tests: none (docs-only leaf; existing doc tests run as regression check).
