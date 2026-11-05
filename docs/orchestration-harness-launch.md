# Harness launches: large prompts and the harness binary

**Related:** [`orchestration-workers.md`](orchestration-workers.md), [`orchestration-models.md`](orchestration-models.md), [`orchestration-reviewer-output.md`](orchestration-reviewer-output.md).

Two things stop a harness before it starts: a prompt too long for a command line, and a harness binary that is not
on the `PATH` a non-interactive shell sees. specy-road handles both before it runs anything, for every role
(executor, reviewer, rca) and every launch path (`worker delegate`, `worker message`, `review delegate`,
`prompt --channel cli`).

## The prompt never travels as an argument

Linux caps one command-line argument at 128 KiB (`MAX_ARG_STRLEN`). Review packets run past 130 KB and a root-cause
prompt reached 197 KB, so a prompt passed as an argument fails with `Argument list too long` (Errno 7, which a shell
reports as exit 126 or 127).

| Harness | How the default command gets the prompt |
| --- | --- |
| `claude-code` | On standard input; the argument is a one-line instruction saying so (launch, resume and reviewer). |
| `codex` | On standard input (`-`), launch, resume and reviewer. |
| `cursor` | `agent -p` documents no standard input (`agent --help`, 2026.10.22), so its argument is a one-line instruction naming the prompt file's absolute path; the agent reads the file. Launch, resume and the `--mode ask` reviewer alike. |

A test builds every adapter's launches for every role from a 200 KiB prompt and checks that no argument exceeds
32 KiB (`tests/test_harness_launch.py`).

## A command that would still put it on the command line is refused

A roster `channels.cli` or profile `access.cli` that uses `"<prompt>"` substitutes the prompt **text** into the
command. When an argument would exceed the 128 KiB limit, specy-road refuses the launch before running anything and
names the size and the fix: use `{prompt}` (the prompt file's path), for example `agent -p --model <id> < {prompt}`
or `codex exec -m <id> - < {prompt}`. A worker launch is refused before its record is created; a reviewer run
becomes a rerun request; `prompt --channel cli` exits 1.

## Which harness binary runs

The default commands run `claude`, `codex` or `agent`. Before launching, specy-road resolves the binary:

1. The roster entry's `harness_bin`, when set: a path (`~` is expanded) or a name looked up on `PATH`.
2. Otherwise `PATH`.
3. Otherwise the directories the harness's installer uses: `~/.local/bin` (Cursor's agent CLI, Claude Code's native
   installer, Codex), and `~/.claude/local` for Claude Code's older local install.

```yaml
roster:
  - id: composer-2.5
    family: cursor
    harness: cursor
    harness_bin: ~/.local/bin/agent   # optional: only when agent is on neither PATH nor ~/.local/bin
    roles: [executor, reviewer]
```

The adapter resolves the binary whenever it builds a default command, from the roster entry every caller passes:
launch, `worker message`'s resume, a reviewer's fresh or resumed turn, and the default resume a custom command
without `{session}` falls back to all run the same binary.

When nothing is found the launch is refused, naming the directories searched and `harness_bin`, instead of the harness
failing with exit 127. The absolute path is what runs: Cursor's `agent create-chat` uses it too, a worker's
`launched` event records it (`detail.argv0`), and a reviewer's `RUN-<model>.log` names it on its first line.

A custom `channels.cli` runs as written: put the path in the command itself if the program is off `PATH`.

## Steering files at launch

A Claude Code executor's default launch and resume pass `--disallowedTools` with `Edit(./<rel>)` and
`Write(./<rel>)` for each in-tree steering file present at launch (harness config and hooks, the roadmap policy files,
root shell startup files; [orchestration-workers.md](orchestration-steering-files.md)) plus
`.claude/settings.json`, `.claude/settings.local.json` and the three roadmap policy files, present or not. A path a
touch zone names exactly is skipped. There is one rule per file and no parent glob, so no rule matches an exempt path.
The rules are relative to the worktree, so new files, shell writes, the common git dir and the main checkout stay
detection-only (the post-run check). A custom `channels.cli` command keeps its argv and gets detection only.

Cursor already blocks writes to `.cursor/*.json`, `.vscode/**` and `.git/hooks/**` on its own, and Codex
`workspace-write` refuses writes outside the workspace but allows in-tree steering files; neither argv is changed.
