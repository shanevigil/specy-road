# Implementation summary: M22.61 (headless-question-tool-flagged)

## What changed

A headless executor turn can call Cursor's question tool. Nobody sees the question, and the post-run check used to call that turn clean. Two changes: every executor prompt says a headless turn has nobody to ask, and a Cursor `tool_call` whose tool key is the question tool is one post-run finding per turn.

The coordinator-supplied capture `tests/fixtures/cursor_question_tool.jsonl` was present. It has no agent-build or date comment line; the first line is a `system`/`init` object (model `Grok 4.7 256K High`). The question tool is the `tool_call` key `askQuestionToolCall` (`started` and `completed`). The same capture also has `interaction_query` lines (`askQuestionInteractionQuery`). Those are not `tool_call` lines, so they are not this finding. Detection stays on that one tool key.

- **Prompt.** `executor_preamble` has one standing line: in a headless turn (`worker delegate`, `worker message`, a grind) no person can answer a question tool; open questions go in the implementation summary under a heading marking them unanswered; the summary never says a person was asked.
- **Event.** The Cursor adapter emits `interactive_tool` for a `tool_call` line whose tool key is `askQuestionToolCall`, beside the line's existing `output` event. `worker-event.schema.json` accepts that type, so `worker_runner` persists it before `TurnWatch.observe` collects it. Shell, read, edit, and assistant text do not emit it.
- **Finding.** `stream_findings` returns one finding of kind `interactive_tool` per turn, naming the tool and that no person saw it, however many such lines the stream holds. The `post_run_check` event is not clean and the worker is flagged `post_run_findings`.
- **Claude.** Unchanged. A result whose `permission_denials` names only that tool is still one `permission_denied` finding and no `interactive_tool` finding.

## Touch zones

Final list, unchanged after scanning call sites: `specy_road/bundled_scripts/role_prompt_rca.py`, `specy_road/worker_turn_check.py`, `specy_road/worker_adapter_cursor.py`, `tests/test_worker_turn_check.py`, `tests/test_models_and_prompt.py`, `tests/fixtures/cursor_question_tool.jsonl`, `docs/orchestration-workers.md`, `CHANGELOG.md`, `specy_road/schemas/worker-event.schema.json`.

`role_prompt.py` renders `executor_preamble` and needed no edit. `worker_runner._consume` already persists every parsed event; the schema was the refusal. The schema file is the only copy. Claude's denial path needed no new code. The fixture was already on the branch and was not edited.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worker_turn_check.py tests/test_models_and_prompt.py`: 51 passed.
- `ruff check` on the touched Python files: clean.
- `specy-road file-limits`: OK. The warnings are existing files outside this leaf.

## Added

- `QUESTION_TOOL`: the captured key `askQuestionToolCall`, so the adapter does not guess the tool name.
- `_interactive_tool`: one `interactive_tool` event when a `tool_call` line's tool key is `QUESTION_TOOL`.
- Guard in `_interactive_tool` (`type` is not `tool_call`): assistant text, `interaction_query`, and other line types are not the finding.
- Guard in `_interactive_tool` (tool key absent): shell, read, edit, and any other tool stay quiet.
- `Cursor.parse_events`: appends that event after the line's other events, including a sandbox `permission_denied`.
- `TurnWatch.interactive` and the `observe` branch: collect each `interactive_tool` tool name for the turn.
- `stream_findings` branch: one `interactive_tool` finding per turn naming the tool and that no person saw it.
- `_question_capture`: load the capture's JSON events, skipping a leading `#` comment if one is added later.
- `_captured_question_tool`: the tool key read from the capture, which the assertions name.
- `_question_calls`: how many `tool_call` lines in a replay carry that key.
- `_keep_question_calls`: the same capture with only one such line, for the one-line row.
- `_run_stream`: replay through public `worker_runner.run` and `close_turn` with the existing fake harness.
- Assertion in `test_executor_prompt_has_precondition_boundary_rules_and_brief`: the no-person line is in the executor prompt once.
- `test_a_cursor_question_tool_is_one_interactive_finding_per_turn`: the capture, and the capture kept to one question `tool_call`, each persist the event, one finding, a post-run check that is not clean, and `post_run_findings`.
- `test_cursor_shell_read_and_edit_calls_are_not_an_interactive_tool`: shell, read, and edit calls yield no `interactive_tool` finding.
- `test_a_claude_denial_of_the_question_tool_is_not_an_interactive_tool`: one `permission_denied` finding naming the tool, and no `interactive_tool` finding.
- Mocks: none.
