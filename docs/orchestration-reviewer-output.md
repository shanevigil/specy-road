# Reviewer output, prevention and the tripwire

How a launched reviewer answers and what specy-road checks before it files the record (M8.3). The rest of the review gate is in [orchestration-review.md](orchestration-review.md).

The reviewer prompt ends with the review output schema: the review-record
schema without the fields specy-road fills (`family`, `independence`,
`notes_sha256`, `signature`, `launch_mode`, `harness_model`, `model_mismatch`), plus `notes`, the Markdown notes.
The reviewer's final message is exactly one JSON object matching it. Before
that object, the prompt tells the reviewer to list every required change
it can find in this one review, re-scan the diff for further instances of each
defect class (other inputs, call sites, files) and any acceptance line not fully
met, and that a later round should find nothing it could have reported now.
Each default reviewer command passes the harness's structured-output flag where there is one:

| Harness | Reviewer command | Where the JSON comes from |
|---|---|---|
| Claude Code | bare or explicit (below); both use `--allowedTools Read,Glob,Grep,Bash`, `--disallowedTools` (below), `--json-schema '<schema>'` (the schema inline, less its top-level `$schema`: Claude Code 2.1.318 rejects the draft 2020-12 reference) and `--add-dir` | the `result` event's `structured_output`, else its text |
| Codex | `codex exec --json -c sandbox_mode=read-only -c approval_policy=never` with memories off (`-c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false`) and `CODEX_HOME` set to the model's isolated home (the session's home on resume), then `--output-schema <file> -o <answer file> -` (the answer file is in a private temporary directory, outside the checkout and the hand-off directory) | at `turn.completed`, the `-o` file; a resume (which documents neither flag) the turn's last `agent_message` |
| Cursor | `agent -p --output-format stream-json --mode ask --trust` (no `--force`) | the last `result` event's text |
| Antigravity (`agy`, a `generic` entry) | its roster `channels.cli` (never the profile's `access.cli`), with `--json-schema <schema file>`, `--output-format json`, `--sandbox` and `--print-timeout 30m` added after `agy` where absent; `--dangerously-skip-permissions` is refused | the envelope's `structured_output` |
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
complete JSON object** that passes the schema: the harness's structured output,
or for a text message (Cursor's or Claude Code's `result` text, Codex's
`agent_message` or `-o` file) its last top-level JSON object. For a text
message, text before the final object is ignored and nothing may follow it
(whitespace aside); the text is read as a run of complete JSON values (a brace
inside a JSON string is text, an object inside another value is never the
answer), and a message cut off inside a token (`{"x": tru`) is an unfinished
object, while a brace no JSON can continue (`Use {1`) is prose; the `generic` row's whole output must still parse as one
object or envelope. Each of these is a rerun request, never a verdict, and an
earlier answer is never used instead:

- no terminal message in the final turn, or a Codex turn with no
  `turn.completed` (cut off, `turn.failed`, or a later `turn.started`);
- a final message that is `null` (an error result), empty, or schema-invalid
  (for a text message, its last object; an earlier valid object is never used),
  or a text message that holds no JSON object, has text after its last object
  (a code fence's closing line included), ends inside an unfinished object, or
  nests JSON too deeply;
- **any** non-blank line inside the final turn that is not one JSON object (a
  truncated event, stray text), even after a valid answer.

An object nested in another value, or a partial object, is never the answer.

The schema file is `work/reviews/<NODE_ID>/review-output.schema.json`, in the
form OpenAI's strict structured output takes, which Codex sends it in: every
object requires all of its properties and allows no others, so a field the
prompt's schema leaves optional is required there and may be `null`, and
`acceptance` names exactly the leaf's acceptance ids (strict mode refuses the
record schema's free-key map and `propertyNames`). The other harnesses read the
same file. specy-road drops those `null` fields before it checks the answer
against the prompt's schema, so `null` and left out mean the same. After the
run (`prompt --channel cli --run` or `review delegate`, default or custom command)
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
  When `review record` refuses the answer of a last attempt that exited 0
  with no capacity error, `review delegate` (not a chore reviewer) gives the reviewer one repair turn: the session's resume, or one
  fresh launch with the full prompt on a harness that cannot resume, with
  `review record`'s whole output and the notes rules, through every capacity
  retry. It is checked like the first turn (write check, model check). The
  run record keeps the first refusal as `refusal` and marks the repair
  attempts `repair: true`; a second refusal leaves the run incomplete, naming
  both. `--resume` of an incomplete run that kept a `refusal` at the commit
  under review sends that repair prompt instead of the continue prompt.
  An answer that does not parse (an empty or missing final message, no JSON
  object, a fenced object or text after it, an unfinished or too deeply nested
  object, a stray or cut-off event line, a null result, or a schema-invalid
  object) gets the same one repair turn under the same condition: the reason is given as specy-road's reading of the final
  message, with a request for the whole object and nothing else, without the
  notes rules. `refusal_kind` records `parse` or `record` (missing is
  `record`), and `--resume` sends the repair prompt of the stored kind. A
  second failure of either kind leaves the run incomplete, naming both; there
  is never a third turn. Neither kind gets a repair turn after a capacity
  failure or a non-zero exit, and an unreadable run log, a write (still a
  review failure) and a chore reviewer get none.
  A refusal's one-line reason (the first one, and a repair turn's) is
  `rerun requested: review record refused the output: <first offending line, whole> (N more; full text in
  work/reviews/<ID>/REJECTED-<model>.md)`. A turn (first or repair) whose last attempt
  ended with a capacity error has no answer to read: the run's reason is the
  capacity reason alone, and the write check still runs.
- **recorded** — specy-road writes the notes to `notes-<model>.md` and `review record` files
  `REVIEW-<model>.md` from them, with the launch mode, family and `history/`
  copy an interactive filing gets. Under `policy.signed_reviews`, pass the
  reviewer's key to the launch (`review delegate --sign-key <key>`,
  `prompt --role reviewer --channel cli --run --sign-key <key>`); specy-road files the
  record with `review record --sign-key`, and the gate verifies the signature.

## `prompt --channel cli`: launch, command, worktree, model (M15.3)

`specy-road prompt --channel cli` writes the prompt and prints the command it
would run, for every role; it starts no process, the roster's `preflight`
included, unless `--run` is given. A reviewer's command comes from its roster
entry only: a `claude-code`, `codex` or `cursor` entry without `channels.cli`
runs the read-only command above with the entry's model, and any other entry
its `channels.cli`. The model is resolved one way for the shown command and the
launch alike (`review_model_check.resolve_effective_model`, which applies
`orchestration_config.harness_model`): the entry's `harness_model`, else the
profile's `api_id`, else the roster `id`; an empty or `unknown` result from any
step is refused. Refused before launch, with the reason: an entry without
either (the profile's `access.cli` is an example and is never run for a
reviewer), a model that resolves to none (a profile `api_id` of `unknown` and
no `harness_model`: the harness would run its own default under the rostered id;
checked for a `channels.cli` too), and a
`channels.cli` passing `--force`, `--yolo` or `--dangerously-skip-permissions`.
The flag check is one rule: the command is split as `sh` reads its words,
erring towards seeing more. Every backslash-newline (a line continuation) is
removed first, then `shlex` in POSIX mode with `punctuation_chars` and no
comment character splits the rest, so `;`, `&`, `|`, `(`, `)`, `<` and `>` are
separate tokens, quotes are removed and `#` is an ordinary character. A token
whose name (the part before any `=`) is exactly one of the flags refuses it:
`--force;`, `--force&&x`, `(--force)`, `'--force'`, `--for\` + newline + `ce`
and `a#b --force` all do; a quoted argument that only mentions `--force` among
other words does not. It is conservative on purpose: a flag inside a `#`
comment, or a backslash-newline inside single quotes (which `sh` keeps), also
refuses. Flags the shell produces at run time (`$VAR`, `$'...'`, `$(...)`,
brace expansion, aliases, a script the command runs) are out of scope; a
command the tokenizer cannot split (an unbalanced quote) is refused.

The reviewer runs in the leaf's own worktree, the one `git worktree list`
shows with the claimed branch checked out, never in a checkout on the
integration branch; `--worktree PATH` names another. Without `--run` the
command is always shown, with a note when no worktree qualifies. Either must be the top
of a git checkout, must not have the integration branch checked out, and must
have `HEAD` at the claimed branch's tip; otherwise `prompt` refuses. With no
worktree at all, it refuses and names `--worktree PATH` and the `git worktree
add` that creates one.

After the run, `specy_road/review_model_check.py` compares the model the
harness reported (its first `system/init` event's `model`, as worker usage
reads it, and each `result` event's `model`, or the one key of its
`modelUsage`) with the entry's one effective model
(`review_model_check.resolve_effective_model`: `harness_model`, else the
profile's `api_id`, else the roster `id`; empty or `unknown` resolves to none),
after normalising case, separators and display names (`Claude Opus 5.5` is
`claude-opus-5-5`), and with nothing else: not the roster label, and not the
profile's other names when `harness_model` selects a different model. Any reported model that differs is a mismatch, so a line
the model printed can add one but never hide one. The filed record carries
`harness_model`; on a real mismatch it also carries `model_mismatch: true`, and the gate does not count
it (`harness ran a different model`), which `handoff status` lists under who
can still approve. A harness that reports no model (Codex, plain-text
commands) is a warning only.

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

Paths are compared as text and no symlink is followed: an entry is left to rule 2 only when the path `git status` prints lies under the hand-off directory, whose place the snapshot before the run fixes (the snapshot after reuses it). A tracked file replaced by a symlink (`T`), a new symlink anywhere in the worktree, or the hand-off directory replaced by a symlink is a review failure; a symlink is hashed by its target text. Before that comparison, and before anything is restored, the tripwire checks `work` and `work/reviews` with lstat from the project directory that holds `work/`. A symlink at either is a review failure and nothing is read, deleted or written through it, including the run log and a later gate read: an outside record reached only through that link does not count, and neither does one reached through a symlink at the node directory. A closed listing reads no directory in the project, so a record at `<project>/.handoff-closed` is not an approval. The log read checks every ancestor from the project root saved before the run, so a symlink at the node directory is not opened. `mark-implementation-reviewed` refuses that node link before it reads the gate, names the path, and does not commit the registry. A relative `work/reviews/<node>` is owned by `.` (the directory that holds that `work`), so the lock and the writers do not create `work/work` or follow a top-level `work` symlink. The review lock and the review writers use the same rule: a symlink at the file, or at any directory from that project root down, refuses the command before it writes. A successful `review record` checks `REJECTED-<model>.md` before it writes the live record or clears that marker. Readers apply the same rule: a hand-off file (`REVIEW-*.md`, a `history/` copy, `READY-*.md`, `RCA-*.md`, `RED-GREEN.md`, `PRE-EXISTING.md`, `POLICY-ACCEPTED.yaml`) that is a symlink, or is reached through one, is reported unreadable and never counts, and a symlinked `history/` is not listed. A failed run's restore puts back only this model's records that were regular files before the run, so a link placed earlier never becomes a real record.

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
`GIT_OPTIONAL_LOCKS=0`, so re-running tests and `git status` write nothing.
Both runners (`review delegate` and `prompt --channel cli --run`) start the
reviewer in a session and process group of its own, and guard it from launch
to end: the prompt goes on stdin from a separate thread, after the watch on
the reviewer's exit has started, so an undelivered prompt (a child holding
stdin unread) never holds the run. When its main process
exits (a background child still holding its output does not delay this), or
the run is interrupted (Ctrl-C reaches specy-road, not the reviewer) or fails
while reading output, specy-road sends that group SIGTERM, then SIGKILL after
5 s, and reads the rest of the output for at most 5 s more. It signals only
while the group has a member and never its own group; a process that left the
group with its own session before the reviewer exited is not reached. A
prompt specy-road does not read back (`paste`, `subagent`) asks for the same
object and still has the reviewer file it with `review record`.

The run record (`RUN-<model>.json`) of a launched reviewer is closed from the
run's filing outcome, by one function for `review delegate`, `prompt --channel
cli` and an interrupted run: only a `recorded` filing (whose record the gate
then validates) is `complete`; a review failure or rerun request is
`incomplete`, with its reason and a reviewer-failure event, whatever older
record of the same commit is on file.
