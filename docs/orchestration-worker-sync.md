# Worker sync — waiting, filters and compact output

Every coordinator turn starts with [`specy-road worker sync`](orchestration-workers.md). This page covers **`--wait`**, **`--until`**, and how tool-use lines are shown. The command table and the rest of the worker loop stay in [orchestration-workers.md](orchestration-workers.md).

## Waiting

When there is nothing to do until a worker reports, call `specy-road worker sync --wait` rather than sleeping and re-running `sync`. Every event appended to any worker's log also replaces one file, `work/.workers/FLAG`; `--wait` stats it every 250 ms (no OS watch API) and prints the usual `sync` output as soon as it changes, or at once when an unacknowledged event is already there. After `--timeout` seconds (default 600) with nothing new it prints the empty delta and exits 2. The wait is the command itself, in the foreground: nothing runs on after it returns, and Ctrl-C ends it with exit 130 and no acknowledgement.

### `--until` (with `--wait`)

By default, `--wait` returns on **any** new event, including every harness `output` line (each tool use). That is fine when you want the next line of activity, but not when you are waiting for a **turn to end**.

Use **`--wait --until completion`**, or a comma list such as **`--until completion,error,intervention`**, to block until an unacknowledged event whose `type` is one of those appears. Typical coordinator use:

```bash
specy-road worker sync --wait --until completion --timeout 600
```

`output`, `message`, `usage`, and the rest still show up in the next `sync` once the turn ends; they just do not end the wait early.

## Compact tool-use output

Consecutive `output` events whose only text is `(tool use)` collapse to one line in plain `sync` output, for example `  #5-#10 output: 6 tool uses`. Pass **`--verbose`** on `sync` to print each event line as before.

When a `completion` event reports **`READY file missing`**, the rendered block includes **`specy-road worker resume W --ready-only`**: a one-turn resume with a short prompt to write READY for the current HEAD only (see the `resume` row in [orchestration-workers.md](orchestration-workers.md)).

## Related flags (on `sync`)

| Flag | Role |
|---|---|
| `--ack` | Mark the returned events handled (`work/.workers/sync.yaml`). |
| `--wait` | Block until there is something to report (see above). |
| `--until TYPES` | With `--wait`: only `completion`, `error`, and/or `intervention` end the wait. |
| `--timeout SECONDS` | With `--wait` (default 600). |
| `--verbose` | Do not collapse tool-use runs. |

Orphaned workers, gaps, and `--json` behave as documented under **`sync`** in [orchestration-workers.md](orchestration-workers.md).
