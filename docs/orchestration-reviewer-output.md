# Reviewer output and the read-only check

How a launched reviewer answers and what specy-road checks before it files the record (M8.3). The rest of the review gate is in [orchestration-review.md](orchestration-review.md).

The reviewer prompt ends with the review output schema: the review-record
schema without the fields `review record` fills (`family`, `independence`,
`notes_sha256`, `signature`, `launch_mode`), plus `notes`, the Markdown notes.
The reviewer ends its reply with one JSON object matching it. Each default
reviewer command passes the harness's structured-output flag where there is one:

| Harness | Reviewer command | Where the JSON comes from |
|---|---|---|
| Claude Code | `--bare`, `--disallowedTools` as above, `--json-schema '<schema>'` | the `result` event's `structured_output`, else its text |
| Codex | `codex exec --json -c sandbox_mode=read-only -c approval_policy=never --output-schema <file> -o <OUTPUT-<model>.json> -` | the `-o` file; a resume (which documents neither flag) its last `agent_message` |
| Cursor | `agent -p --output-format stream-json --mode ask --trust` (no `--force`) | the `result` event's text |
| Antigravity (`agy`, a `generic` entry) | its `channels.cli` or `access.cli`, with `--json-schema <schema file>`, `--output-format json`, `--sandbox` and `--print-timeout 30m` added after `agy` where absent; `--dangerously-skip-permissions` is refused | the envelope's `structured_output` |
| anything else (`channels.cli`, `generic`) | as written | the output's last complete JSON object, which must start a line with no later `{`, and no later line opening a JSON array (`[1,`, or a `[` never closed), after it (a JSON envelope's `structured_output`) |

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

- **review failure** — the run wrote something besides its notes
  (`notes-<model>.md`) and the files the run itself keeps (`RUN-<model>.json`,
  its `.tmp`, `RUN-<model>.log` and `OUTPUT-<model>.json`; the schema file and
  `.review-run.lock` exist before the run and specy-road never writes them
  during it, so they are not among them), or changed `RUN-<model>.log` other than by specy-road's own
  appends of the harness's output (specy-road hashes what the log held when the
  run began and every byte it appended since): any file of the checkout it ran in, git-ignored and
  `work/` files included, any file of the leaf's hand-off directory, the Git
  metadata a reviewer of this leaf could change (below), `HEAD` or the reviewed
  branch moving, or the Git index's entries (`git add`,
  `git update-index --assume-unchanged`; compared by `git ls-files --stage -v`,
  so the stat refresh a read-only `git status` writes is not a write). Files, and directories (a file created and deleted again still moves its directory's mtime and ctime), are compared by identity (device, inode, link count), permission mode,
  change time (ctime, which a process cannot put back), content (SHA-256), size and mtime, so a rewrite with its mtime put back counts.
  A `REVIEW-<model>.md` it filed itself is put back as it was. Nothing is filed.
- **rerun request** — the output has no JSON object, its last object does not
  start a line or sits inside an outer object left unterminated or inside an array (closed or not), a later object was begun and left malformed or truncated (an
  earlier complete object never stands in for it), it does not match the schema,
  or `review record` refuses it (another commit, an approve with a failing
  item, or no `--sign-key` under `policy.signed_reviews`). Nothing is filed; it
  is never recorded as a verdict. `OUTPUT-<model>.json` is emptied before every
  attempt, so a resumed turn (a Codex resume writes no `-o` file) is judged by
  its own final message, never by an earlier attempt's answer.
- **recorded** — the notes go to `notes-<model>.md` and `review record` files
  `REVIEW-<model>.md` from them, with the launch mode, family and `history/`
  copy an interactive filing gets. Under `policy.signed_reviews`, pass the
  reviewer's key to the launch (`review delegate --sign-key <key>`,
  `prompt --role reviewer --channel cli --sign-key <key>`); specy-road files the
  record with `review record --sign-key`, and the gate verifies the signature.

The check walks every file, so run reviewers where nothing else writes: a
coordinator or executor editing the same checkout during the run, or another
leaf's reviewer filing there, counts as this run's write.

Git metadata is shared by every checkout of the repository, so the check reads
only what a reviewer of this leaf could change:

- the checkout's own Git directory (`git rev-parse --git-dir`): `HEAD` and
  `logs/HEAD`, and the index by its entries (above);
- the reviewed branch (the branch checked out where the reviewer runs, and the
  local branch `review delegate` reviews when that checkout is detached): its
  loose ref `refs/heads/<branch>`, its reflog `logs/refs/heads/<branch>` and its
  line in `packed-refs`;
- the shared `hooks/` directory, files and directories, since every checkout runs
  that code;
- a linked worktree's `.git` pointer file.

Everything else in the Git directories is left out: the common directory's own
metadata (an `index.lock` another session takes there), `config`, `objects`,
`FETCH_HEAD`, `ORIG_HEAD`, other branches' refs and reflogs, and other
worktrees' directories. An IDE polling the repository or another worktree
committing on its own branch during the run does not fail the review; a reviewer
commit on the reviewed branch does (its ref and reflog move).

The contents of a nested checkout (a
linked worktree under `work/.worktrees`, a nested repository) are another
checkout's and are skipped, but its `.git` marker is recorded, so a
reviewer-created `.git` file or `git init` anywhere is a write. The reviewer runs with `GIT_OPTIONAL_LOCKS=0`, so a read-only `git status` takes no `index.lock`; the hand-off root, whose entries specy-road changes between harness turns, is fenced during each turn instead: `OUTPUT-<model>.json` and `notes-<model>.md` are created before the run and written in place, so any file created, renamed or deleted there while the harness runs is a write, whatever else the turn wrote. The fence also holds `RUN-<model>.json`, which specy-road writes only between turns: a change to it during a turn is a write, reported as the hand-off directory. Two reviewer runs of one leaf share its
hand-off directory, so they take turns: a second run while one holds
`.review-run.lock` is refused at once, before it writes its prompt, run record,
schema or answer file. The reviewer's process gets
`PYTHONDONTWRITEBYTECODE=1` and `PYTEST_ADDOPTS=-p no:cacheprovider`, so
re-running Python tests writes nothing; a command that still writes (a build,
`.specyrd/cache`) fails the review. A prompt specy-road does not read back
(`paste`, `subagent`) asks for the same object and still has the reviewer file
it with `review record`.
