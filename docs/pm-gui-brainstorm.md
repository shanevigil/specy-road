# Brainstorm panel (PM GUI)

The browser version of [`specy-road brainstorm`](brainstorming.md). Same two
modes, same session file, same promotion path — the difference is that the
model runs against the backend configured in **Settings** instead of the agent
in your IDE, and research goes through an endpoint you configure rather than
the agent's own search tool.

Open it from **Brainstorm** in the toolbar, next to Vision and Shared docs.

## Before you start

**A model is required.** The panel disables its composer until Settings has a
working LLM backend (OpenAI, Azure, Anthropic, or an OpenAI-compatible
endpoint). Use **Test LLM** there first.

**Web search is optional and off by default.** Without it the assistant
answers from the repository and its own training, and is told to say so rather
than invent sources.

## Turning on web search

**Settings → Research**:

| Field | Meaning |
|-------|---------|
| Enabled | Whether the assistant may search at all |
| Endpoint | Bing Web Search v7 URL. Azure-hosted variants and compatible proxies work — anything answering `?q=&count=` with `{"webPages": {"value": […]}}` |
| Subscription key | Sent as `Ocp-Apim-Subscription-Key`. Obfuscated at rest like the LLM and git credentials |
| Results per search | Capped at 20 |

**Test search** verifies the endpoint before you rely on it.

Research is stored **globally**, not per repository — a search subscription is
a user credential, and unlike a git remote it does not differ between projects.

### How the assistant searches

Not through provider function calling. The four supported backends disagree
about tool schemas, and the `compatible` backend is whatever you are
self-hosting, where tool support is often absent. Instead the model is told to
emit `SEARCH: <query>` lines; the server runs them and feeds the results back
as another turn.

The loop is bounded: at most 3 rounds of at most 4 queries per message. A
failed search becomes text the model reads ("search failed: …") rather than an
error that ends the conversation.

## Using the panel

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
4. **Triage** in the Ideas list. Accept, Reject, and Undo per row. Ideas are
   ordered by the model's verdict, strongest first; ideas already promoted sink
   to the bottom and lose their buttons, because they are roadmap nodes now and
   the node is what you edit.
5. **Preview promotion**, then **Promote**. Preview shows the display ids that
   would be created and writes nothing.

Promotion is the same code path as the CLI and as `add-node`: chunk, manifest,
and planning sheet in one transaction, then validation. The outline refreshes
when it lands. Afterwards, regenerate the derived files:

```bash
specy-road export && specy-road digest
```

## Notes

- Mutating calls carry `X-PM-Gui-Fingerprint`, like every other write in the
  dashboard, so a conflicting edit elsewhere is caught rather than clobbered.
- The chat transcript lives in the browser tab. The **ideas** are the durable
  artifact and are written to the session file as they are captured; closing
  the panel loses the conversation, not the work.
- The CLI and the panel can be used against the same session interchangeably.

## Where to read next

- [brainstorming.md](brainstorming.md) — the CLI, the session format, promotion
- [pm-gui.md](pm-gui.md) — what ships for the dashboard
- [pm-llm-review.md](pm-llm-review.md) — the other LLM feature in the GUI
