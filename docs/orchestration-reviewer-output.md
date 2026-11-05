# Reviewer output, prevention and the tripwire

How a launched reviewer answers and what specy-road checks before it files the record (M8.3). The rest of the review gate is in [orchestration-review.md](orchestration-review.md).

The reviewer prompt ends with the review output schema: the review-record
schema without the fields `review record` fills (`family`, `independence`,
`notes_sha256`, `signature`, `launch_mode`), plus `notes`, the Markdown notes.
The reviewer's final message is exactly one JSON object matching it. Each default
reviewer command passes the harness's structured-output flag where there is one:

| Harness | Reviewer command | Where the JSON comes from |
|---|---|---|
| Claude Code | bare or explicit (below); both use `--allowedTools Read,Glob,Grep,Bash`, `--disallowedTools` (below), `--json-schema '<schema>'` and `--add-dir` | the `result` event's `structured_output`, else its text |
| Codex | `codex exec --json -c sandbox_mode=read-only -c approval_policy=never --output-schema <file> -o <answer file> -` (the answer file is in a private temporary directory, outside the checkout and the hand-off directory) | at `turn.completed`, the `-o` file; a resume (which documents neither flag) the turn's last `agent_message` |
| Cursor | `agent -p --output-format stream-json --mode ask --trust` (no `--force`) | the last `result` event's text |
| Antigravity (`agy`, a `generic` entry) | its `channels.cli` or `access.cli`, with `--json-schema <schema file>`, `--output-format json`, `--sandbox` and `--print-timeout 30m` added after `agy` where absent; `--dangerously-skip-permissions` is refused | the envelope's `structured_output` |
| anything else (`channels.cli`, `generic`, or a plain-text wrapper on any harness) | as written | the whole output, as one final message (a JSON envelope's `structured_output`) |

Claude Code's mode is decided once for `review delegate` and `prompt --channel cli` (`specy_road/reviewer_auth.py`). **Bare** (`--bare`) only when the reviewer's environment has `ANTHROPIC_API_KEY` or the user settings bare mode reads define `apiKeyHelper`. When the helper is the only credential, bare mode also passes `--settings` with that user-settings path, so the helper command is not on the argv or in the log. **Explicit** otherwise: `--setting-sources user --strict-mcp-config` and no `--mcp-config`, so no repository hooks, project settings or MCP servers load, and the subscription login is read. Explicit argv never contains `--bare`. Both modes keep the `--disallowedTools` list, the `--json-schema` and the hand-off `--add-dir`. A profile `access.launch_mode: bare`, or a roster entry `launch_mode: bare`, forces bare; with no key and no `apiKeyHelper`, both commands refuse before launch (no RUN record, exit 1) and name the fixes: export `ANTHROPIC_API_KEY`, configure `apiKeyHelper`, or let specy-road choose explicit mode. The RUN record and the filed REVIEW carry `launch_mode` `bare` or `explicit`. The key's value is never printed or logged. `orchestrate plan` prints one `reviewer auth:` notice per such entry.

One reader takes every harness's answer, strictly (A3). Each harness has one
row in `TURNS` (`specy_road/review_answer.py`) declaring its turn boundary and
terminal message:

| Harness | Final turn | Must close with | Terminal message |
|---|---|---|---|
| Claude Code | the whole process output, from its first event | — | the `result` event: its `structured_output`, else its `result` text; `null` when `is_error` |
| Codex | from the last `turn.started` (none: the first event) | `turn.completed` | the last completed `agent_message`; the `-o` file instead when Codex wrote one |
| Cursor | the whole process output, from its first event | — | the `result` event's text; `null` when `is_error` |
| Antigravity `agy` and any other `generic` / `channels.cli` command | the whole output | — | the whole output: one JSON object, or an `--output-format json` envelope whose `structured_output` is the answer |

An output with none of a harness's event types is read by the `generic` row.
Only the final turn's **last** terminal message counts, and it must be **one
complete JSON object** that passes the schema: its whole text (whitespace
aside) parses as one object, or the harness's structured output is one. Each
of these is a rerun request, never a verdict, and an earlier answer is never
used instead:

- no terminal message in the final turn, or a Codex turn with no
  `turn.completed` (cut off, `turn.failed`, or a later `turn.started`);
- a final message that is `null` (an error result), empty, not JSON, prose
  around JSON, a code fence, two objects, an array, or schema-invalid;
- **any** non-blank line inside the final turn that is not one JSON object (a
  truncated event, stray text), even after a valid answer.

Nested or partial objects are never salvaged.

The schema file is `work/reviews/<NODE_ID>/review-output.schema.json`, in the
form OpenAI's strict structured output takes, which Codex sends it in: every
object requires all of its properties and allows no others, so a field the
prompt's schema leaves optional is required there and may be `null`, and
`acceptance` names exactly the leaf's acceptance ids (strict mode refuses the
record schema's free-key map and `propertyNames`). The other harnesses read the
same file. specy-road drops those `null` fields before it checks the answer
against the prompt's schema, so `null` and left out mean the same. After the
run (`prompt --channel cli` or `review delegate`, default or custom command)
specy-road decides the outcome:

- **review failure** — the tripwire below saw a write. A `REVIEW-<model>.md`
  the run filed itself is put back as it was. Nothing is filed.
- **rerun request** — the extractor above found no answer, it does not match
  the schema, or `review record` refuses it (another commit, an approve with a
  failing item, or no `--sign-key` under `policy.signed_reviews`). Nothing is
  filed; it is never recorded as a verdict. Only the last attempt's output is
  read, and Codex's answer file is removed before every attempt, so a resumed
  turn (a Codex resume writes no `-o` file) is judged by its own final message,
  never by an earlier attempt's answer. An attempt's output is the span of
  `RUN-<model>.log` specy-road recorded itself around the harness's output
  (`log_start`, `log_end` and `log_sha256` in each attempt of the run record),
  never found by searching the log: the `[review delegate]` / `[review prompt]`
  lines are for people and are not parsed, so a harness that prints one moves
  nothing. A span whose bytes changed during the run reads as no output.
- **recorded** — specy-road writes the notes to `notes-<model>.md` and `review record` files
  `REVIEW-<model>.md` from them, with the launch mode, family and `history/`
  copy an interactive filing gets. Under `policy.signed_reviews`, pass the
  reviewer's key to the launch (`review delegate --sign-key <key>`,
  `prompt --role reviewer --channel cli --sign-key <key>`); specy-road files the
  record with `review record --sign-key`, and the gate verifies the signature.

## Prevention and the tripwire (A2)

A reviewer cannot forge a record because specy-road files it from the run's
final JSON; it cannot write the repository or `work/reviews/<ID>/` because
each default reviewer launch is read-only: Codex `sandbox_mode=read-only`;
Cursor `--mode ask` without `--force`; Claude Code, bare and explicit alike, with `--allowedTools
Read,Glob,Grep,Bash` and `--disallowedTools Write Edit NotebookEdit
"Bash(git commit *)" "Bash(git push *)" "Bash(gh *)"`. Tests pin each argv.
Prevention is the boundary.

After the run a small tripwire (`specy_road/review_write_check.py`) reports a
**review failure** when:

1. the leaf worktree's `git status --porcelain -z --untracked-files=all`
   lists a path it did not list before the run, or lists one with another
   status code or other content (SHA-256): a changed tracked file or a new
   untracked file; or
2. `work/reviews/<ID>/` gains, loses or changes (by SHA-256) any file other
   than the reviewer's notes (`notes-<model>.md`) and the run files specy-road
   itself writes (`RUN-<model>.json`, `RUN-<model>.log`, `.review-run.lock`).

Paths are compared as text and no symlink is followed: an entry is left to rule 2 only when the path `git status` prints lies under the hand-off directory, whose place the snapshot before the run fixes (the snapshot after reuses it). A tracked file replaced by a symlink (`T`), a new symlink anywhere in the worktree, or the hand-off directory replaced by a symlink is a review failure; a symlink is hashed by its target text.

It is a tripwire, **not a security boundary**. Out of scope by design:
identical-byte rewrites, writes undone before the run ends, metadata-only
changes (mode, times, links), git-ignored files outside the hand-off
directory, and Git internals (`HEAD`, refs, reflogs, the index, hooks,
config). Other sessions writing the same checkout during the run count as the
run's writes, so run reviewers where nothing else writes. Two reviewer runs of
one leaf share its hand-off directory, so they take turns: a second run while
one holds `.review-run.lock` is refused at once, before it writes its prompt,
run record, schema or answer file. The reviewer's process gets
`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_ADDOPTS=-p no:cacheprovider` and
`GIT_OPTIONAL_LOCKS=0`, so re-running tests and `git status` write nothing. A
prompt specy-road does not read back (`paste`, `subagent`) asks for the same
object and still has the reviewer file it with `review record`.

The run record (`RUN-<model>.json`) of a launched reviewer is closed from the
run's filing outcome, by one function for `review delegate`, `prompt --channel
cli` and an interrupted run: only a `recorded` filing (whose record the gate
then validates) is `complete`; a review failure or rerun request is
`incomplete`, with its reason and a reviewer-failure event, whatever older
record of the same commit is on file.
