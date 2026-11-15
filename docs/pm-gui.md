# PM Gantt UI — production architecture

The supported **PM dashboard** is a **FastAPI** server plus a **prebuilt React** single-page app. There is no alternate GUI tree in this repository. Two LLM features of the dashboard have their own sections below: the [Brainstorm panel](#brainstorm-panel) and [LLM Review](#llm-review).

## What ships

- **Server:** [`specy_road/gui_app.py`](../specy_road/gui_app.py) — JSON API for roadmap, planning files, and settings; serves the static UI from [`specy_road/pm_gantt_static/`](../specy_road/pm_gantt_static/) (package data in [`pyproject.toml`](../pyproject.toml)).
- **Frontend sources:** [`gui/pm-gantt/`](../gui/pm-gantt/) — Vite + React + TypeScript. Production assets are produced with `npm run build`, which writes into `specy_road/pm_gantt_static/` for inclusion in the wheel.
- **CLI:** `specy-road gui` starts Uvicorn with the FastAPI app. Install optional dependencies with `pip install 'specy-road[gui]'` (`[gui-next]` is a deprecated alias of it, removed in the release after 0.3.1).

- **Archive drawer:** the toolbar's **Archive** button lists archived subtrees, offers eligible ones, and restores them. Routes live in [`specy_road/gui_app_routes_archive.py`](../specy_road/gui_app_routes_archive.py); every write carries the usual `X-PM-Gui-Fingerprint` token because archiving moves roadmap files. Two preferences under **Settings → Completed work** control the default Hide Complete state (a view filter) and auto-archiving (which moves files). See [Archiving](archiving.md).
- **Workers drawer:** the header's **Workers** button shows what each worker did, step by step, without reading the JSONL. It reads the worker records and event logs under the **main** worktree's `work/.workers/` (gitignored; see [Orchestration workers](orchestration-workers.md)) and **never writes** there: no stall sweep, no `sync --ack`. Workers are grouped by leaf; each row shows its attempt, harness/model, state and total cost (`$?` when no `usage` event reported one, never `$0`). Selecting a worker shows:
  - a **phase bar** for the latest turn — delegated → launched → first output → turn end → acked, each segment sized by its share of the known total and listed with its seconds (`unknown` when a boundary event is missing); the same numbers as `specy-road worker timeline`;
  - the worker's **usage** totals (the same sums as `specy-road worker usage`);
  - the **event list**, with tool-call lines (Claude's `(tool use)`, Cursor's `tool call …`, Codex's command/file/MCP/web-search items) labelled `tool`, and **stall markers** on `stalled` events plus a `stalled ×N` badge when any exist.

  Routes, both read-only, in [`specy_road/gui_app.py`](../specy_road/gui_app.py): `GET /api/workers` (one row per worker: id, node, harness, model, state, attempt, flags, last event, total cost) and `GET /api/workers/{id}/events` (that row plus `events`, `phases` in seconds and `usage` totals; 404 for an unknown id). The drawer reloads when opened and on **Refresh**.
- **Orchestration drawer:** the header's **Orchestration** button shows, per leaf, its claim, workers, worktrees, hand-off, reviews, gate and holds, from one read: `GET /api/orchestration`, which serves `specy_road.orchestration`'s `state.snapshot` of the **main** checkout's project unchanged (also when the GUI runs from a linked worktree). It is **read-only**: nothing in it stops, messages or resumes a worker, releases a claim, prunes a worktree or records a review; its buttons only copy a CLI command (`specy-road worker status|open <id>`, `specy-road review status <id>`) to the clipboard. It loads when opened, on **Refresh**, and every 15 s while open, never while closed.
  - **Groups:** one per leaf with state, in outline order (display id and title from the outline the GUI already loaded; a leaf missing from the outline shows its key), then a **No leaf** group for workers with no leaf. Clicking the id opens the node; clicking a worker id opens the Workers drawer on it.
  - **Claim:** codename, branch and how long ago the registry row was written.
  - **Workers:** id, harness / model, account (the Claude profile name; empty when not known), status (`claimed`, `running`, `exited_ok`, `exited_failed`, `abandoned`), last activity, started and ended as ages, and the worker's flags verbatim (for example `stalled`).
  - **Detail** (also a collapsed **Orchestration** section in the node edit dialog, loaded each time it is expanded): **Worktrees** with path, branch, dirty, and commits ahead / behind the integration branch; **READY**, the hand-off's commit (first 12 characters), model, age and any `blocked_on` acceptance lines; **Reviews** per model with verdict, commit and **Fresh for HEAD**, blocks first (freshness is the snapshot's `fresh_for_head`, never a comparison of commits in the browser); **Gate**, the `specy-road review status` label with approval and block counts and freshness; **Holds**, each from the hold list (with its reason) or an open gate (its id).
  - **Unknown and "—":** a field the server could not read (unreadable or malformed file) shows `unknown`, for that field only; a field with nothing to show (no READY, no review, an older server without the field) shows **—**, never `no`, `0` or clean.
  - **Outline badge:** each leaf with state gets one badge in the outline, the first that applies of: `blocked (N)` (gate state blocked or executor_blocked; N from the gate's block count or READY's `blocked_on`), `held (N)`, `exited_failed`, `stalled`, `running`, `READY awaiting review`, `approved`, `claimed`, `abandoned`, `unknown`. Hovering lists the claim, workers, worktree count, READY, reviews and holds; clicking opens the drawer on that leaf. Badges refresh with the roadmap and with each drawer load; they have no timer of their own.
  - A server without the route (`404`) leaves the outline without badges and the drawer says the server does not provide the snapshot.
- **Node edit dialog:** opening a node shows its title, dependencies, **Acceptance** criteria and planning sheet. Acceptance has one field per criterion, with add, remove and move up / down; edits save as `PATCH /api/nodes/{id}` with the one pair `acceptance=<criteria joined by newlines>` (`specy-road edit-node --set acceptance=` semantics: whitespace trimmed, empty criteria dropped, an empty list removes the field). A line break inside a criterion is refused with a message rather than splitting it. GUI edits change the graph only; `roadmap.md` and `roadmap-context.md` are regenerated by **Publish** (or `specy-road export` and `specy-road digest`).
- **Group siblings:** the toolbar's **Group siblings…** button opens a dialog on the selected row: its siblings as checkboxes (the row checked), the new parent's id (one past the parent's highest child number in the loaded outline, editable), a required title, a type (milestone by default) and **Rewrite id references in prose** (off by default, as `--rewrite-refs`). **Group** sends one `POST /api/outline/group` with `{into_new, title, node_ids, type, rewrite_refs}`, the checked ids in outline order (`specy-road group-nodes` semantics). A refusal, such as a taken id, shows the server's `400` detail in the dialog and changes nothing; on success the outline refreshes with the new parent selected.
- **Status modal:** the header's **Status** button opens the grind status, the same object as `specy-road grind-session --status --json` (see [grind-session.md](grind-session.md)), read-only. **Until** and **Under** take node ids (both empty: the milestone session's parent; a refusal shows the server's message); they and the interval (Off, 30 s, 60 s by default, 2 min, 5 min) are browser preferences per repo. The modal shows the goal and scope the report returned, the totals, **Last updated** with the time and age of `generated_at` and the checkout it covers, then held, active, ready, waiting, finished awaiting merge, not pickable, the estimate, decisions, sessions and missing in the CLI's order and wording. It polls only while open, skips a tick while a load runs, and the refresh icon (**Refresh now**) loads at once and restarts the interval. After a failed load the last good report stays, its age growing, with the error beside it. A server without the route shows "the server does not provide the status". Which clone to run the GUI from: [pm-workflow.md](pm-workflow.md#which-checkout-to-run-the-gui-from).
- **PM decisions in the Status window:** the one orchestration write the GUI makes (M17.15). The PM can answer an open `decision` or `human-action` entry the status lists, with one of its option labels or **Other** (the words alone), and approve a claimed leaf over counted reviewer blocks when the status says `can_approve_over_block` (settling them would pass the gate). Nothing else held gets a GUI action. The form needs typed words; **Review decision** shows the entry or leaf, the commit, every line the decision settles, the option and the words, and only **Record decision** sends `POST /api/pm-decisions`. The record is the existing one, with `channel: pm-gui`: an answer closes the entry as `decided_by: operator` with `<label>: <words>` (planning-sheet line left to the coordinator); an approval is `mark-implementation-reviewed`'s operator decision (M22.67), its marker's session `pm-gui <UTC time>`. A shared entry is committed alone on the integration branch from a temporary worktree and pushed fast-forward only (no remote: the local branch moves by compare-and-swap), so the GUI's checkout gets no edit; a `decisions.local.yaml` entry is closed in place. The registry is not stamped: a coordinator processes the decision (`grind-session --status` lists it under **Decided in the GUI, not yet processed**). An answer on a `human-action` entry with a `criterion` (a leaf's `human:` acceptance criterion) is the person's decision `finish-this-task` reads, so it is not listed there. A copied schema from before `channel` refuses with `400`; run `specy-road upgrade --only schemas` (the message still names its deprecated alias, `refresh-schemas`).
  - **The code.** When `specy-road gui` starts (not under `--read-only`) it prints a code once on its terminal: "PM decisions: enter this code in the Status window …". It is kept in the server's memory only, never in a file, an environment variable, a log line or a response, and changes on each start. The Status window asks for it once per page load, keeps it in page memory only (a reload asks again) and sends it as `X-PM-Decision-Code`; a missing or wrong code is `403`. The custom header also forces a CORS preflight, which the loopback-only rule refuses for other origins. Start the GUI yourself, in your own terminal: whoever starts it sees the code.
  - **Refusals** come before anything is written: `400` for empty words, an option that is not a label or Other, an unknown id or another kind, and the approval's own checks (the role rule, git identity, the fetch, a dirty holder of the integration branch, settling that would not pass the gate); `409` when the entry closed meanwhile, when the leaf's commit under review is not the one shown, or when what the decision would settle changed (a new block). A refused push or failed commit is `400` with git's message, nothing recorded and no marker. When the commit landed but the re-read gate still fails, the answer is `200` with `gate_met: false` and "the registry was not stamped"; the decision stays.
  - **Limits.** Best effort against a local agent: a process running as you that can read the GUI's terminal or memory, drive the browser or start its own GUI can still forge a decision, as it can already run `review operator-decision` or `decisions close`. The recorded channel and recorder identity, and the coordinator's chat line for every GUI decision, make a forgery visible, not impossible. An approval is usable only in the clone that ran the GUI and its linked worktrees: the gate needs the gitignored `OPERATOR-<commit>.yaml` marker, which a pull does not carry; another clone lists the approval with "process it from the clone that ran the GUI". Answers work in every clone.
- **Last worked column:** the outline shows when each leaf was last worked on, **derived from git history** (no stored file) via the `activity` map on `GET /api/roadmap`; see [Archiving](archiving.md#last-worked-on).

## Read-only JSON API

Scripts may read the dashboard's state through these `GET` routes (all under `/api/`):

| Route | Returns |
| --- | --- |
| `/health` | `{"status": "ok"}` |
| `/repo` | repo root and settings id |
| `/roadmap`, `/roadmap/fingerprint` | the graph with rollups and activity; the polling fingerprints |
| `/governance-completion`, `/git-workflow-status` | vision/constitution completeness; branch and registry status |
| `/planning/{node_id}/artifacts` | the node's planning sheet path and its ancestors' |
| `/planning/file?path=…`, `/workspace/file?path=…` | `{path, content, content_hash}` for a planning file or a `shared/` file |
| `/workspace/files?prefix=shared\|work` | file listing |
| `/settings`, `/publish/status` | GUI settings (secrets masked); publish status |
| `/archives`, `/archives/{id}`, `/archives/{id}/nodes` | archived subtrees |
| `/brainstorm/sessions`, `/brainstorm/session` | brainstorm sessions |
| `/workers`, `/workers/{id}/events` | worker rows and event logs |
| `/orchestration` | `specy_road.orchestration`'s `state.snapshot` of the main checkout's project, unchanged (`schema`, `leaves` keyed by node key, `leafless_workers`); writes nothing |
| `/grind-status?until=…&under=…` | `grind-session --status --json`'s object unchanged (both parameters optional); `400` with the CLI's message where the CLI exits 2; writes nothing but the history cache |

The one orchestration write, `POST /api/pm-decisions` (the Status window's decisions, above), takes `{"kind": "answer", "id", "option" (a label or null for Other), "words"}` or `{"kind": "approve-over-block", "node_id", "commit", "settles", "words"}` (the commit and settles the status showed) with the `X-PM-Decision-Code` header, and returns `{"id", "integration_commit", "destination"}` (`origin/<branch>` or `local <branch>`; `null` and `local ledger` for a local entry), plus `gate_met` for an approval.

An unknown `/api/…` path returns a JSON `404` (`{"detail": "no API route …"}`), never the HTML shell.

- **Safe saves:** `content_hash` is the sha256 of the file's bytes. Send it back as `X-Base-Content-Hash` on `PUT` to the same route; if the file changed on disk since, the save is refused with `409` and `detail.current_content` / `detail.content_hash`, and nothing is written. The UI sends it automatically and shows the conflict instead of overwriting. A `PUT` without the header writes unconditionally, as before.
- **Publish** (`POST /api/publish`): regenerates `roadmap.md` and `roadmap-context.md` from the graph before committing, so the pushed commit passes `export --check` and `digest --check`. It refuses with `400`, before staging anything, when the graph does not validate or no git remote is configured (`/publish/status` then reports `blocked_reason: "no_remote"`).
- **`specy-road gui --read-only`:** serves every `GET` and refuses every other method under `/api/` with `403`, including POSTs that only test settings. It does not switch off the opt-in background `git fetch` / integration auto-FF that `GET /api/roadmap` schedules (**Settings**; off by default).

## How to use it and install it

- **End-user install + everyday usage** (consumer-side; `specy-road gui`):
  [install-and-usage.md](install-and-usage.md).
- **Day-to-day PM usage** (browser workflow, what you see in the UI):
  [pm-workflow.md](pm-workflow.md).
- **Rebuilding the SPA from source** (toolkit contributors only): see
  [contributor-guide.md](contributor-guide.md) (section *PM Gantt UI build
  & install*).

Contributors editing React code: rebuild from `gui/pm-gantt/` or use the
Vite dev server with a separate Uvicorn process; details are in
[contributor-guide.md](contributor-guide.md).

## Historical note

The older Streamlit-based dashboard was removed. The toolkit standard is the stack above only.

## Brainstorm panel

**Use this section when:** setting up or explaining the **Brainstorm** panel in `specy-road gui`, including its web-search providers.
**Not for:** the CLI passes, the session format and promotion — [`brainstorming.md`](brainstorming.md).

**Must know without reading on:**
- The panel needs a working LLM backend in Settings; use **Test LLM** first. Web search is optional and off by default.
- Research settings are global, not per repository; a private or plain-`http` search endpoint is refused unless **Self-hosted endpoint** is on.
- Ideas are captured only in Brainstorm mode; Roadmap mode judges and may not add ideas. The human accepts, rejects and promotes.
- The Ideas list shows ideas and triage state, verdicts only behind **Show verdicts**; clusters, critics, quotes and verification states are CLI-only (`brainstorm list --by cluster`).
- Roadmap mode is **advisory only**: its verdicts, clusters and overlaps stay in the chat and are not written to the session. Apply the ones you keep with the CLI's `specy-road brainstorm revise`.
- Panel and CLI share `work/brainstorm-<slug>.yaml`; after promoting run `specy-road export && specy-road digest`.

The browser version of [`specy-road brainstorm`](brainstorming.md). Same two
modes, same session file, same promotion path — the difference is that the
model runs against the backend configured in **Settings** instead of the agent
in your IDE, and research goes through an endpoint you configure rather than
the agent's own search tool.

Open it from **Brainstorm** in the toolbar, next to Vision and Shared docs.

### Before you start

**A model is required.** The panel disables its composer until Settings has a
working LLM backend (OpenAI, Azure, Anthropic, or an OpenAI-compatible
endpoint). Use **Test LLM** there first.

**Web search is optional and off by default.** Without it the assistant
answers from the repository and its own training, and is told to say so rather
than invent sources.

### Turning on web search

**Settings → Research**:

| Field | Meaning |
|-------|---------|
| Enabled | Whether the assistant may search at all |
| Provider | Which back end to call — see the table below |
| Endpoint | Leave blank to use the provider's default; SearXNG has none, so fill it in |
| API key | Obfuscated at rest like the LLM and git credentials, and like them never sent back to the page (shown as `********`; leave it to keep the stored key) |
| Self-hosted endpoint | Permits a private or localhost address. Off by default — see below |
| Results per search | Capped at 20 |

**Test search** verifies the endpoint before you rely on it.

Research is stored **globally**, not per repository — a search subscription is
a user credential, and unlike a git remote it does not differ between projects.

#### Providers

| Provider | Default endpoint | Key |
|----------|------------------|-----|
| Bing / Azure Web Search | `api.bing.microsoft.com/v7.0/search` | `Ocp-Apim-Subscription-Key` |
| Tavily | `api.tavily.com/search` | `Authorization: Bearer` |
| Brave Search | `api.search.brave.com/res/v1/web/search` | `X-Subscription-Token` |
| Serper (Google) | `google.serper.dev/search` | `X-API-KEY` |
| Exa | `api.exa.ai/search` | `x-api-key` |
| Firecrawl | `api.firecrawl.dev/v1/search` | `Authorization: Bearer` |
| SearXNG (self-hosted) | none — supply your own | usually none |

Switching provider clears the endpoint, so you get the new provider's default
rather than the previous one's URL.

Settings written before this existed used `bing_endpoint` and `bing_api_key`;
those are still read, so an existing configuration keeps working untouched.

#### Self-hosted endpoints

The dashboard refuses a search endpoint that resolves to a private, loopback,
or link-local address, and requires `https`. That is deliberate: the GUI is
reachable from any page open in your browser, so an unchecked endpoint would
turn search into a way to probe your own network.

A SearXNG instance you run yourself is exactly the case that restriction gets
wrong, so **Self-hosted endpoint** lifts it — permitting private addresses and
plain `http`, since a LAN box rarely has a certificate. Leave it off unless the
endpoint is one you operate.

#### How the assistant searches

Not through provider function calling. The four supported backends disagree
about tool schemas, and the `compatible` backend is whatever you are
self-hosting, where tool support is often absent. Instead the model is told to
emit `SEARCH: <query>` lines; the server runs them and feeds the results back
as another turn.

The loop is bounded: at most 3 rounds of at most 4 queries per message. A
failed search becomes text the model reads ("search failed: …") rather than an
error that ends the conversation.

### The window

Brainstorm opens as a task window, not a drawer: it has the same traffic-light
controls, tiling, and stacking as the task dialogs, and shares one window stack
with them. So it can sit beside the task it is about — **Tile** lays the open
windows out left to right, with the task dialogs in dependency order and
Brainstorm on the right, since it is not a step in that chain. **Minimize**
sends it to the strip at the bottom of the screen; the conversation and the
captured ideas are still there when you bring it back. Pressing the Brainstorm
button again raises it rather than doing nothing.

Inside, height goes to the conversation: it takes roughly three times the share
the idea list does as the window grows, and the idea list scrolls under its own
heading. The composer starts one line tall and grows as you type, up to about
eight lines. **Enter** sends and **Shift+Enter** starts a new line.

### Using the panel

1. **Set the topic and anchor**, then **Start session**. The anchor is the node
   accepted ideas will hang off; leave it blank for the roadmap root. This
   creates the same `work/brainstorm-<slug>.yaml` the CLI uses.
2. **Stay in Brainstorm mode** while generating. The assistant is given the
   divergent prompt: it will question the topic before generating, then produce
   volume without ranking. Ideas it proposes are written to the session as they
   arrive and appear in the Ideas list — the panel reports how many each reply
   added. Capture only happens in this mode, so the converge pass cannot
   quietly add to the board while it is judging it.
3. **Switch to Roadmap mode** when you have enough. The assistant is given the
   convergent prompt instead — clustering, overlap detection, and a `strong` /
   `consider` / `park` verdict per idea. It is told not to add new ideas.
   **This pass is advisory only.** What it says stays in the chat: the panel
   does not parse verdicts, clusters, overlaps or critics out of the reply,
   and nothing is written to the session. To keep a verdict, apply it with
   the CLI against the same session file:

   ```bash
   specy-road brainstorm revise B1 --cluster C1 --overlap M3.1:adjacent \
     --critic "feasibility: …" --recommendation strong --why "…"
   ```

4. **Triage** in the Ideas list. Each row shows the id, title, kind,
   effort, rationale, evidence URLs and status, with Accept, Reject, and
   Undo. Verdicts are hidden by default, as in the CLI's `list`, so they do
   not steer you; **Show verdicts** adds the `strong` / `consider` / `park`
   badge from `revise` and sorts strongest first. Otherwise ideas keep their
   capture order. Ideas already promoted sink to the bottom and lose their
   buttons, because they are roadmap nodes now and the node is what you edit.
   The list does not show clusters, critics, overlaps, quotes or verification
   states; read those with `specy-road brainstorm list --by cluster` and the
   session file.
5. **Preview promotion**, then **Promote**. Preview shows the display ids that
   would be created and writes nothing.

Promotion is the same code path as the CLI and as `add-node`: chunk, manifest,
and planning sheet in one transaction, then validation. The outline refreshes
when it lands. Afterwards, regenerate the derived files:

```bash
specy-road export && specy-road digest
```

### What the panel does not do yet

The CLI's round model (`next-round`), shards, the evidence pass and `verify`
are not panel buttons yet. The panel's Brainstorm mode runs the round-1
prompt, so it plans and generates without the roadmap inventory; Roadmap mode
runs the same converge prompt the CLI writes (clusters, overlap relations,
critics) but records none of its output — verdicts are advisory, and
`specy-road brainstorm revise` is how they reach the session. The panel does
show the round the session is in (`round N of M`, from `start --rounds`).
Use the CLI against the same session for the rest; the session file is
shared.

### Notes

- Mutating calls carry `X-PM-Gui-Fingerprint`, like every other write in the
  dashboard, so a conflicting edit elsewhere is caught rather than clobbered.
- The chat transcript lives in the browser tab. The **ideas** are the durable
  artifact and are written to the session file as they are captured; closing
  the panel loses the conversation, not the work.
- The CLI and the panel can be used against the same session interchangeably.

## LLM Review

**Use this section when:** a PM asks what the PM Gantt **LLM Review** button sends, where it sends it, or how to merge the proposal it returns.
**Not for:** where LLM credentials and environment variables are stored — [`pm-workflow.md`](pm-workflow.md) (Settings, **LLM** tab).

**Must know without reading on:**
- LLM Review is advisory: nothing on disk changes until the user accepts edits and saves; still run `specy-road validate` afterwards.
- The brief, the cited `shared/` contracts, `constraints/README.md`, the `shared/` index and the current sheet text all leave the machine for the configured provider.
- Anthropic requires `SPECY_ROAD_ANTHROPIC_MAX_TOKENS` (or Settings **Max output tokens**); there is no hidden default.
- Terminal equivalent: `specy-road review-node <NODE_ID> -o work/review-<NODE_ID>.md`.

This section is for **product managers and delivery leads** using the **PM Gantt** dashboard (`specy-road gui`). It explains what **LLM Review** does when your team has configured an external model, what information is sent to that model, and how to use the **diff**, **preview**, and **merge** controls afterward.

It is **not** a legal or security sign-off: your organization’s policies on AI vendors, data residency, and customer content still apply. See [supply-chain-security.md](supply-chain-security.md) for how this repository treats dependencies and verification.

---

### What LLM Review is (and is not)

**LLM Review** asks a configured **large language model** to return a **full revised copy** of the **planning Markdown** for the roadmap item you are editing (the **feature-sheet** outline for most node types, and a **gate-specific** outline for `type: gate`). You can compare that proposal to what you had before, optionally merge it in section by section, then save the sheet through the normal editor flow.

- **Advisory only** — The model does **not** write to disk by itself. Nothing in the roadmap JSON or planning files changes until **you** accept edits and the app persists them.
- **Not a substitute for validation** — After you change a sheet, your team should still run **`specy-road validate`** (and your usual review process) before treating the spec as authoritative.
- **Optional** — If you skip LLM Review entirely, the rest of the dashboard works the same.

For **where credentials live** (Settings file, global vs per-repo, environment variables), see [pm-workflow.md](pm-workflow.md) (sidebar **Settings**, **LLM** tab, and **LLM environment variables**).

---

### Before you can use it

1. **A planning sheet must exist** for that node — the button sits in the planning area when `planning/` is set up. If you see “Create planning file,” run **`specy-road planning scaffold <NODE_ID>`** (or use the on-screen scaffold action) first.
2. **LLM settings must be complete** for the backend you chose in **Settings → LLM** (gear in the sidebar). The UI enables **LLM Review** only when the saved form looks sufficient for that backend (same rules as **Test LLM**). Use **Test LLM** once after changing keys or models so you catch connection errors early.
3. **Anthropic only:** the Anthropic **Messages** API requires a **maximum completion token** budget. Set **Max output tokens** in Settings (saved into the same mechanism as other LLM fields) **or** export **`SPECY_ROAD_ANTHROPIC_MAX_TOKENS`** in the environment before starting the GUI. There is **no hidden default** in the reviewer for that value.
4. **Read-only planning** — If this task’s **registered development branch** matches your **current git checkout**, the dashboard treats the title and planning sheet as **read-only** (so in-flight dev work is not overwritten from the PM UI). **LLM Review** is disabled in that state as well.

Supported backends in the reviewer match the docs: **OpenAI**, **Azure OpenAI**, **Anthropic**, and **OpenAI-compatible** base URLs. Azure uses your **resource endpoint**, **API key**, and **deployment name** (the deployment name is what the API calls the “model” for that request).

---

### What happens when you press **LLM Review**

1. The app takes a **snapshot** of the **current editor text** (what you see in the planning Markdown editor), even if you have not saved to disk yet.
2. It sends your **saved LLM settings** for this repository to the **local FastAPI server**, which temporarily copies the relevant values into **process environment variables** the reviewer reads (same names as the CLI — see [pm-workflow.md](pm-workflow.md)).
3. The server builds a **structured prompt**: fixed **instructions** (system message) plus a **single user message** made of labeled sections (brief, shared index, constraints, cited files, your sheet, expected headings). Details are in the next section.
4. The model returns **Markdown** only — intended as a **replacement planning sheet** with the same canonical `##` sections as `specy-road planning scaffold` for that node type (**feature sheet**: Intent, Approach, Tasks / checklist, References; **gate**: Why this gate exists, Criteria to clear, Decisions and notes, Resolution, References).
5. The UI shows that result in **review mode**: a **diff** view by default, with extra actions described below.

If the request fails (network, auth, quota, invalid Anthropic max tokens, etc.), you see an **error string** in the planning toolbar area; your sheet is left unchanged.

---

### What the model actually sees (high level)

Think of two layers: **instructions** (what role the model is in and how it must format the answer) and **context** (the facts you are asking it to improve).

#### Instructions (system message)

The server sends a fixed block of text that tells the model, in short:

- Output **only** the revised Markdown sheet — **no** preamble, **no** “here is what I changed,” and **no** wrapping the whole answer in a fenced code block.
- Follow the **canonical `##` section order** for that node type (same outline as scaffolding: feature sheet vs gate sheet).
- Stay concise; do **not** repeat node id, title, or roadmap dependency prose in the sheet (those belong in the roadmap graph and brief).
- **Defer to the brief for upstream dependency context.** The brief now carries `## 6. Dependency context (intent of upstream work)` with each effective dependency's `## Intent` block (or the gate equivalent) inlined verbatim. The model is instructed to **scan that section first** and **drop sentences from the revised sheet that paraphrase a dep's intent**. It is allowed to add a **single one-line clarification** under `## Approach` (for feature sheets) or `## Decisions and notes` (for gates) **only when** there is a non-obvious aspect of how this task **uses** an upstream dep that the dep's own intent does not state, citing the dep by display id.
- Treat the **`shared/` index** as **optional pointers**; it does **not** replace the **cited contract** snippets when those exist.

#### Context (one long user message, several headings)

The user message is built on the server from your **resolved repository root** (the path shown as **Open repository** in Settings). It includes, in order:

1. **`## Brief`** — The same **work-packet brief** the CLI would generate for that node (`specy-road brief`): metadata, ancestor chain, **inlined planning sheets** along the ancestor path and for this node, the **full text of each `shared/` contract the chain cites in its `## References`** (plus `shared/README.md`; everything else under `shared/` is listed as a path), dependencies, **`## 6. Dependency context (intent of upstream work)`** with each effective dependency's `## Intent` block inlined verbatim, touch-zone guidance, and a short rollup reference. This block can be **large** on big programs.
2. **`## shared/ index (possible references)`** — A **sorted** list of files under **`shared/`** (including subfolders), each with a **short, deterministic one-line description** derived from a small prefix of the file (so the model knows what else exists without rereading the whole tree). Very large trees are **capped** (file count and total characters) with a short footer so the request stays bounded.
3. **`## constraints/README.md`** — The full **`constraints/README.md`** file if it exists, or a placeholder if it does not.
4. **`## Current planning sheet`** — The **snapshot from the editor** when you clicked the button (not necessarily what is on disk).
5. **`## Expected shape`** — A short bullet list of the canonical `##` headings for that node type so the model stays aligned with your scaffold.

**Caching (performance):** The **`shared/` index** text may be **reused** across repeated reviews in the same server process when the tool detects that nothing relevant under **`shared/`** changed (using **git** state when possible, otherwise file metadata). The **brief** and the rest of the message are still rebuilt each time so they stay current.

#### Tokens, cost, and size

- The app does **not** show a token counter. **Total size** depends on your brief, how many files are under **`shared/`**, how large cited contracts are, and how long the current sheet is.
- **Billing and limits** are entirely between **you** and **your model provider** (OpenAI, Azure, Anthropic, or your compatible gateway). Large briefs can approach **context window** limits; if that happens, the provider returns an error like any other API failure.
- **OpenAI / Azure OpenAI** chat completions: by default the reviewer does **not** set `max_tokens` / `max_completion_tokens` (provider defaults). For **Azure** deployments that require `max_completion_tokens`, you can opt in via environment variables documented in [pm-workflow.md](pm-workflow.md) (`SPECY_ROAD_AZURE_CHAT_USE_MAX_COMPLETION_TOKENS` and related).
- **Optional throughput caps** (requests and estimated tokens per **rolling 60 seconds**, **local to the process** running the reviewer): configured for **Azure** in PM Gantt Settings, or via env vars for any OpenAI-shaped backend — see [pm-workflow.md](pm-workflow.md) (**Azure throughput** and **OpenAI or compatible** bullets). If a call would exceed the cap, you get a **clear error** (no silent drop).
- **Anthropic:** you must supply a **completion budget** via **`SPECY_ROAD_ANTHROPIC_MAX_TOKENS`** (Settings **Max output tokens** or environment), because their API **requires** that parameter.

---

### After the model responds: diff, preview, and actions

When a proposal arrives, the planning area switches out of the plain single-editor layout into **review mode**.

#### Default: section diff (“Before” vs “Proposed”)

You see a **side-by-side diff** built from **Markdown structure**:

- The left column is **Before (snapshot)** — the sheet as it was when you clicked **LLM Review**.
- The right column is **Proposed** — the model’s returned Markdown.
- Lines are highlighted (**green** for additions, **red** for deletions, neutral for unchanged context), similar to a code diff but rendered for readability.
- The diff is grouped by **`##` sections** (level-2 headings). For each **paired** section (same heading index on both sides), you can **click** the **Before** or **Proposed** column to record which side you want for that section.

**Important:** merging works on **paired** sections only. If the **number of `##` sections** differs between snapshot and proposal, the UI warns you: only the **first N** matching pairs participate in **Accept selections** / **Accept all**; trailing unpaired content may still appear in the diff for your reading but is **not** folded into those merge actions (use **Append** or manual editing if you need that text).

#### **Proposed preview** (raw compare)

**Proposed preview** switches to a layout with your **editable** planning editor on one side and a **read-only rendered preview** of the proposed sheet on the other. A collapsible **Markdown source** area exposes the raw proposed Markdown in a **textarea** so you can **select** precise passages.

Use this when you care more about **reading** or **copying** fragments than about the line diff.

#### Buttons (what they do)

| Control | Effect |
| -------- | ------ |
| **Close LLM Review** | Discards review state and returns to normal editing. Your planning text reverts to whatever was in the editor before merge (if you had not merged, nothing changes). |
| **Proposed preview** / **Back to diff** | Toggles between the **section diff** view and the **preview + raw source** view. |
| **Append selection** (preview mode) | Copies the **currently selected text** from the proposed Markdown **source** and **appends** it to the end of your planning document (with spacing). Disabled when there is no selection. |
| **Append proposed sheet** | **Appends the entire** proposed Markdown to your planning document. Useful if you want to keep your version and park the model output below for comparison. |
| **Accept selections** | Builds a new sheet from **paired sections**: for each section where you clicked a side, that side wins; any section you never clicked defaults to **Before**. Then review mode closes and the **editor** shows the merged result (autosave rules apply as usual). Disabled when there is nothing to pair. |
| **Accept all (proposed)** | Same as choosing **Proposed** for **every** paired section, then closing review mode. |

Until you **save** (or autosave) through your normal workflow, other collaborators may not see the merged text on disk — behavior matches the rest of the edit dialog.

---

### Privacy and “what leaves my laptop”

Everything described above is sent from the **machine running the PM GUI server** to the **API endpoint** you configured (OpenAI, Azure, Anthropic, or compatible). That includes the **brief** (which inlines planning content and the bodies of the `shared/` contracts the chain cites), **constraints**, **cited paths**, the **`shared/` file index**, and your **current sheet text**.

If any of that material is sensitive, **do not use LLM Review** until your team’s policy allows it, or use a **private deployment** / gateway your organization approves.

---

### Command-line equivalent

Developers can run the same reviewer without the GUI:

```bash
specy-road review-node <NODE_ID> -o work/review-<NODE_ID>.md
```

Same environment variables as the dashboard. See [pm-workflow.md](pm-workflow.md) under **Optional: LLM review from the terminal**.
