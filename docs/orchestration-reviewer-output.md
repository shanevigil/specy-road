# Reviewer output and the read-only check

How a launched reviewer answers and what specy-road checks before it files the record (M8.3). The rest of the review gate is in [orchestration-review.md](orchestration-review.md).

The reviewer prompt ends with the review output schema: the review-record
schema without the fields `review record` fills (`family`, `independence`,
`notes_sha256`, `signature`, `launch_mode`), plus `notes`, the Markdown notes.
The reviewer ends its reply with one JSON object matching it. Each default
reviewer command passes the harness's structured-output flag where there is one:

| Harness | Reviewer command | Where the JSON comes from |
|---|---|---|
| Claude Code | `--bare`, `--disallowedTools` as above, `--json-schema '<schema>'` | the last `result` event's `structured_output`, else its text |
| Codex | `codex exec --json -c sandbox_mode=read-only -c approval_policy=never --output-schema <file> -o <answer file> -` (the answer file is in a private temporary directory, outside the checkout and the hand-off directory) | at `turn.completed`, the `-o` file; a resume (which documents neither flag) the turn's last `agent_message` |
| Cursor | `agent -p --output-format stream-json --mode ask --trust` (no `--force`) | the last `result` event's text |
| Antigravity (`agy`, a `generic` entry) | its `channels.cli` or `access.cli`, with `--json-schema <schema file>`, `--output-format json`, `--sandbox` and `--print-timeout 30m` added after `agy` where absent; `--dangerously-skip-permissions` is refused | the envelope's `structured_output` |
| anything else (`channels.cli`, `generic`, or a plain-text wrapper on any harness) | as written | the whole output, as one final message (a JSON envelope's `structured_output`) |

One extractor reads every harness's answer: the adapter maps its stream to
ordered messages, each terminal or not, and only the **last** message counts.
It must be terminal (a stream cut off before its `result` or `turn.completed`
is a rerun request), and its body must be a JSON object: `null` (a `null` text,
an error result, a `turn.failed`), empty text, or text that does not end with
one JSON object is a rerun request, and an earlier answer is never used instead.
A text answer is the JSON object the message ends with: it starts a line (prose
or a ```` ```json ```` fence may come before it), nothing but a closing fence
follows it (a later object or array, a trailer, or prose after it is a rerun
request), and no `{` or `[` before it is left open.

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

- **review failure** — the run wrote anything; there is no exemption list,
  and the reviewer's notes travel in the JSON object, not a file. The files
  specy-road itself writes in the checked tree during the run,
  `RUN-<model>.log` (the harness's output, appended during each turn) and,
  under `review delegate`, `RUN-<model>.json` (rewritten between turns), exist
  before the first snapshot and are written in place, so no directory entry
  moves; each is compared by identity and mode like any file, and by content
  against what specy-road wrote (specy-road hashes what it held when the run
  began and every byte it wrote since, and a rewrite first checks that nothing
  else changed it). Everything else specy-road writes for the run is outside
  the tree or outside the run: Codex's answer file in a private temporary
  directory; the lock, prompt and schema before the first snapshot; the notes,
  the record and the run's last record update after the last. Compared: any file of the checkout it ran in, git-ignored and
  `work/` files included, any file of the leaf's hand-off directory, the Git
  metadata a reviewer of this leaf could change (below), `HEAD` or the reviewed
  branch moving, or the Git index's entries (`git add`,
  `git update-index --assume-unchanged`; compared by `git ls-files --stage -v`,
  so the stat refresh a read-only `git status` writes is not a write). Files, and directories (a file created and deleted again still moves its directory's mtime and ctime), are compared by identity (device, inode, link count), permission mode,
  change time (ctime, which a process cannot put back), content (SHA-256), size and mtime, so a rewrite with its mtime put back counts.
  A `REVIEW-<model>.md` it filed itself is put back as it was. Nothing is filed.
- **rerun request** — the extractor above found no answer, it does not match
  the schema, or `review record` refuses it (another commit, an approve with a
  failing item, or no `--sign-key` under `policy.signed_reviews`). Nothing is
  filed; it is never recorded as a verdict. Only the last attempt's output is
  read, and Codex's answer file is removed before every attempt, so a resumed
  turn (a Codex resume writes no `-o` file) is judged by its own final message,
  never by an earlier attempt's answer.
- **recorded** — specy-road writes the notes to `notes-<model>.md` and `review record` files
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
reviewer-created `.git` file or `git init` anywhere is a write. The reviewer runs with `GIT_OPTIONAL_LOCKS=0`, so a read-only `git status` takes no `index.lock`. The hand-off directory itself is compared like any directory: specy-road creates no entry there during the run, so any file created, renamed or deleted there is a write. Two reviewer runs of one leaf share its
hand-off directory, so they take turns: a second run while one holds
`.review-run.lock` is refused at once, before it writes its prompt, run record,
schema or answer file. The reviewer's process gets
`PYTHONDONTWRITEBYTECODE=1` and `PYTEST_ADDOPTS=-p no:cacheprovider`, so
re-running Python tests writes nothing; a command that still writes (a build,
`.specyrd/cache`) fails the review. A prompt specy-road does not read back
(`paste`, `subagent`) asks for the same object and still has the reviewer file
it with `review record`.

The run record (`RUN-<model>.json`) of a launched reviewer is closed from the
run's filing outcome, by one function for `review delegate`, `prompt --channel
cli` and an interrupted run: only a `recorded` filing (whose record the gate
then validates) is `complete`; a review failure or rerun request is
`incomplete`, with its reason and a reviewer-failure event, whatever older
record of the same commit is on file.
