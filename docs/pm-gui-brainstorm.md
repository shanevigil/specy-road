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
| Provider | Which back end to call — see the table below |
| Endpoint | Leave blank to use the provider's default; SearXNG has none, so fill it in |
| API key | Obfuscated at rest like the LLM and git credentials |
| Self-hosted endpoint | Permits a private or localhost address. Off by default — see below |
| Results per search | Capped at 20 |

**Test search** verifies the endpoint before you rely on it.

Research is stored **globally**, not per repository — a search subscription is
a user credential, and unlike a git remote it does not differ between projects.

### Providers

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

### Self-hosted endpoints

The dashboard refuses a search endpoint that resolves to a private, loopback,
or link-local address, and requires `https`. That is deliberate: the GUI is
reachable from any page open in your browser, so an unchecked endpoint would
turn search into a way to probe your own network.

A SearXNG instance you run yourself is exactly the case that restriction gets
wrong, so **Self-hosted endpoint** lifts it — permitting private addresses and
plain `http`, since a LAN box rarely has a certificate. Leave it off unless the
endpoint is one you operate.

### How the assistant searches

Not through provider function calling. The four supported backends disagree
about tool schemas, and the `compatible` backend is whatever you are
self-hosting, where tool support is often absent. Instead the model is told to
emit `SEARCH: <query>` lines; the server runs them and feeds the results back
as another turn.

The loop is bounded: at most 3 rounds of at most 4 queries per message. A
failed search becomes text the model reads ("search failed: …") rather than an
error that ends the conversation.

## The window

Brainstorm opens as a task window, not a drawer: it has the same traffic-light
controls, tiling, and stacking as the task dialogs, and shares one window stack
with them. So it can sit beside the task it is about — **Tile** lays the open
windows out left to right, with the task dialogs in dependency order and
Brainstorm on the right, since it is not a step in that chain. **Minimize**
sends it to the strip at the bottom of the screen; the conversation and the
captured ideas are still there when you bring it back. Pressing the Brainstorm
button again raises it rather than doing nothing.

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
