# PM Gantt: LLM Review (plain-English guide)

This guide is for **product managers and delivery leads** using the **PM Gantt** dashboard (`specy-road gui`). It explains what **LLM Review** does when your team has configured an external model, what information is sent to that model, and how to use the **diff**, **preview**, and **merge** controls afterward.

It is **not** a legal or security sign-off: your organization’s policies on AI vendors, data residency, and customer content still apply. See [supply-chain-security.md](supply-chain-security.md) for how this repository treats dependencies and verification.

---

## What LLM Review is (and is not)

**LLM Review** asks a configured **large language model** to return a **full revised copy** of the **planning Markdown** for the roadmap item you are editing (the **feature-sheet** outline for most node types, and a **gate-specific** outline for `type: gate`). You can compare that proposal to what you had before, optionally merge it in section by section, then save the sheet through the normal editor flow.

- **Advisory only** — The model does **not** write to disk by itself. Nothing in the roadmap JSON or planning files changes until **you** accept edits and the app persists them.
- **Not a substitute for validation** — After you change a sheet, your team should still run **`specy-road validate`** (and your usual review process) before treating the spec as authoritative.
- **Optional** — If you skip LLM Review entirely, the rest of the dashboard works the same.

For **where credentials live** (Settings file, global vs per-repo, environment variables), see [pm-workflow.md](pm-workflow.md) (sidebar **Settings**, **LLM** tab, and **LLM environment variables**).

---

## Before you can use it

1. **A planning sheet must exist** for that node — the button sits in the planning area when `planning/` is set up. If you see “Create planning file,” run **`specy-road scaffold-planning <NODE_ID>`** (or use the on-screen scaffold action) first.
2. **LLM settings must be complete** for the backend you chose in **Settings → LLM** (gear in the sidebar). The UI enables **LLM Review** only when the saved form looks sufficient for that backend (same rules as **Test LLM**). Use **Test LLM** once after changing keys or models so you catch connection errors early.
3. **Anthropic only:** the Anthropic **Messages** API requires a **maximum completion token** budget. Set **Max output tokens** in Settings (saved into the same mechanism as other LLM fields) **or** export **`SPECY_ROAD_ANTHROPIC_MAX_TOKENS`** in the environment before starting the GUI. There is **no hidden default** in the reviewer for that value.
4. **Read-only planning** — If this task’s **registered development branch** matches your **current git checkout**, the dashboard treats the title and planning sheet as **read-only** (so in-flight dev work is not overwritten from the PM UI). **LLM Review** is disabled in that state as well.

Supported backends in the reviewer match the docs: **OpenAI**, **Azure OpenAI**, **Anthropic**, and **OpenAI-compatible** base URLs. Azure uses your **resource endpoint**, **API key**, and **deployment name** (the deployment name is what the API calls the “model” for that request).

---

## What happens when you press **LLM Review**

1. The app takes a **snapshot** of the **current editor text** (what you see in the planning Markdown editor), even if you have not saved to disk yet.
2. It sends your **saved LLM settings** for this repository to the **local FastAPI server**, which temporarily copies the relevant values into **process environment variables** the reviewer reads (same names as the CLI — see [pm-workflow.md](pm-workflow.md)).
3. The server builds a **structured prompt**: fixed **instructions** (system message) plus a **single user message** made of labeled sections (brief, shared index, constraints, cited files, your sheet, expected headings). Details are in the next section.
4. The model returns **Markdown** only — intended as a **replacement planning sheet** with the same canonical `##` sections as `specy-road scaffold-planning` for that node type (**feature sheet**: Intent, Approach, Tasks / checklist, References; **gate**: Why this gate exists, Criteria to clear, Decisions and notes, Resolution, References).
5. The UI shows that result in **review mode**: a **diff** view by default, with extra actions described below.

If the request fails (network, auth, quota, invalid Anthropic max tokens, etc.), you see an **error string** in the planning toolbar area; your sheet is left unchanged.

---

## What the model actually sees (high level)

Think of two layers: **instructions** (what role the model is in and how it must format the answer) and **context** (the facts you are asking it to improve).

### Instructions (system message)

The server sends a fixed block of text that tells the model, in short:

- Output **only** the revised Markdown sheet — **no** preamble, **no** “here is what I changed,” and **no** wrapping the whole answer in a fenced code block.
- Follow the **canonical `##` section order** for that node type (same outline as scaffolding: feature sheet vs gate sheet).
- Stay concise; do **not** repeat node id, title, or roadmap dependency prose in the sheet (those belong in the roadmap graph and brief).
- **Defer to the brief for upstream dependency context.** The brief now carries `## 6. Dependency context (intent of upstream work)` with each effective dependency's `## Intent` block (or the gate equivalent) inlined verbatim. The model is instructed to **scan that section first** and **drop sentences from the revised sheet that paraphrase a dep's intent**. It is allowed to add a **single one-line clarification** under `## Approach` (for feature sheets) or `## Decisions and notes` (for gates) **only when** there is a non-obvious aspect of how this task **uses** an upstream dep that the dep's own intent does not state, citing the dep by display id.
- Treat the **`shared/` index** as **optional pointers**; it does **not** replace the **cited contract** snippets when those exist.

### Context (one long user message, several headings)

The user message is built on the server from your **resolved repository root** (the path shown as **Open repository** in Settings). It includes, in order:

1. **`## Brief`** — The same **work-packet brief** the CLI would generate for that node (`specy-road brief`): metadata, ancestor chain, **inlined planning sheets** along the ancestor path and for this node, **full text of every top-level `shared/*.md` file**, dependencies, **`## 6. Dependency context (intent of upstream work)`** with each effective dependency's `## Intent` block inlined verbatim, touch-zone guidance, and a short rollup reference. This block can be **large** on big programs.
2. **`## shared/ index (possible references)`** — A **sorted** list of files under **`shared/`** (including subfolders), each with a **short, deterministic one-line description** derived from a small prefix of the file (so the model knows what else exists without rereading the whole tree). Very large trees are **capped** (file count and total characters) with a short footer so the request stays bounded.
3. **`## constraints/README.md`** — The full **`constraints/README.md`** file if it exists, or a placeholder if it does not.
4. **`## Cited documents (from contract_citation)`** — Parsed from the node’s **`agentic_checklist.contract_citation`** field in the roadmap JSON. Only repo-relative paths starting with **`shared/`**, **`docs/`**, **`specs/`**, or **`adr/`** are included; each file is inlined up to a **per-file size cap** (very long files are truncated with a marker).
5. **`## Current planning sheet`** — The **snapshot from the editor** when you clicked the button (not necessarily what is on disk).
6. **`## Expected shape`** — A short bullet list of the canonical `##` headings for that node type so the model stays aligned with your scaffold.

**Caching (performance):** The **`shared/` index** text may be **reused** across repeated reviews in the same server process when the tool detects that nothing relevant under **`shared/`** changed (using **git** state when possible, otherwise file metadata). The **brief** and the rest of the message are still rebuilt each time so they stay current.

### Tokens, cost, and size

- The app does **not** show a token counter. **Total size** depends on your brief, how many files are under **`shared/`**, how large cited contracts are, and how long the current sheet is.
- **Billing and limits** are entirely between **you** and **your model provider** (OpenAI, Azure, Anthropic, or your compatible gateway). Large briefs can approach **context window** limits; if that happens, the provider returns an error like any other API failure.
- **OpenAI / Azure OpenAI** chat completions: by default the reviewer does **not** set `max_tokens` / `max_completion_tokens` (provider defaults). For **Azure** deployments that require `max_completion_tokens`, you can opt in via environment variables documented in [pm-workflow.md](pm-workflow.md) (`SPECY_ROAD_AZURE_CHAT_USE_MAX_COMPLETION_TOKENS` and related).
- **Optional throughput caps** (requests and estimated tokens per **rolling 60 seconds**, **local to the process** running the reviewer): configured for **Azure** in PM Gantt Settings, or via env vars for any OpenAI-shaped backend — see [pm-workflow.md](pm-workflow.md) (**Azure throughput** and **OpenAI or compatible** bullets). If a call would exceed the cap, you get a **clear error** (no silent drop).
- **Anthropic:** you must supply a **completion budget** via **`SPECY_ROAD_ANTHROPIC_MAX_TOKENS`** (Settings **Max output tokens** or environment), because their API **requires** that parameter.

---

## After the model responds: diff, preview, and actions

When a proposal arrives, the planning area switches out of the plain single-editor layout into **review mode**.

### Default: section diff (“Before” vs “Proposed”)

You see a **side-by-side diff** built from **Markdown structure**:

- The left column is **Before (snapshot)** — the sheet as it was when you clicked **LLM Review**.
- The right column is **Proposed** — the model’s returned Markdown.
- Lines are highlighted (**green** for additions, **red** for deletions, neutral for unchanged context), similar to a code diff but rendered for readability.
- The diff is grouped by **`##` sections** (level-2 headings). For each **paired** section (same heading index on both sides), you can **click** the **Before** or **Proposed** column to record which side you want for that section.

**Important:** merging works on **paired** sections only. If the **number of `##` sections** differs between snapshot and proposal, the UI warns you: only the **first N** matching pairs participate in **Accept selections** / **Accept all**; trailing unpaired content may still appear in the diff for your reading but is **not** folded into those merge actions (use **Append** or manual editing if you need that text).

### **Proposed preview** (raw compare)

**Proposed preview** switches to a layout with your **editable** planning editor on one side and a **read-only rendered preview** of the proposed sheet on the other. A collapsible **Markdown source** area exposes the raw proposed Markdown in a **textarea** so you can **select** precise passages.

Use this when you care more about **reading** or **copying** fragments than about the line diff.

### Buttons (what they do)

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

## Privacy and “what leaves my laptop”

Everything described above is sent from the **machine running the PM GUI server** to the **API endpoint** you configured (OpenAI, Azure, Anthropic, or compatible). That includes the **brief** (which inlines planning content and top-level `shared/*.md` bodies), **constraints**, **cited paths**, the **`shared/` file index**, and your **current sheet text**.

If any of that material is sensitive, **do not use LLM Review** until your team’s policy allows it, or use a **private deployment** / gateway your organization approves.

---

## Command-line equivalent

Developers can run the same reviewer without the GUI:

```bash
specy-road review-node <NODE_ID> -o work/review-<NODE_ID>.md
```

Same environment variables as the dashboard. See [pm-workflow.md](pm-workflow.md) under **Optional: LLM review from the terminal**.

---

## Related docs

- [pm-workflow.md](pm-workflow.md) — Settings storage, LLM env vars, **Test LLM**, day-to-day PM commands.
- [pm-gui.md](pm-gui.md) — Starting the dashboard and repository root behavior.
- [optional-ai-tooling-patterns.md](optional-ai-tooling-patterns.md) — Broader, optional patterns for coding agents in product repos (not specific to this button).
