/**
 * The search back ends offered in Settings → Research.
 *
 * Mirrors `brainstorm_search_providers.PROVIDERS` on the server, but only the
 * parts the form needs: what to call it, what to prefill, and whether to ask
 * for a key at all. The server decides how to actually talk to it.
 */
export type ResearchProvider = {
  key: string;
  label: string;
  /** Blank when the user must supply one — self-hosted back ends have no default. */
  defaultEndpoint: string;
  needsKey: boolean;
  /** What the credential is called in that product's own docs. */
  keyLabel: string;
};

export const RESEARCH_PROVIDERS: ResearchProvider[] = [
  {
    key: "bing",
    label: "Bing / Azure Web Search",
    defaultEndpoint: "https://api.bing.microsoft.com/v7.0/search",
    needsKey: true,
    keyLabel: "Subscription key",
  },
  {
    key: "tavily",
    label: "Tavily",
    defaultEndpoint: "https://api.tavily.com/search",
    needsKey: true,
    keyLabel: "API key",
  },
  {
    key: "brave",
    label: "Brave Search",
    defaultEndpoint: "https://api.search.brave.com/res/v1/web/search",
    needsKey: true,
    keyLabel: "Subscription token",
  },
  {
    key: "serper",
    label: "Serper (Google)",
    defaultEndpoint: "https://google.serper.dev/search",
    needsKey: true,
    keyLabel: "API key",
  },
  {
    key: "exa",
    label: "Exa",
    defaultEndpoint: "https://api.exa.ai/search",
    needsKey: true,
    keyLabel: "API key",
  },
  {
    key: "firecrawl",
    label: "Firecrawl",
    defaultEndpoint: "https://api.firecrawl.dev/v1/search",
    needsKey: true,
    keyLabel: "API key",
  },
  {
    key: "searxng",
    label: "SearXNG (self-hosted)",
    defaultEndpoint: "",
    needsKey: false,
    keyLabel: "API key (usually none)",
  },
];

export const DEFAULT_RESEARCH_PROVIDER = "bing";

export function researchProvider(key: string | undefined): ResearchProvider {
  const found = RESEARCH_PROVIDERS.find((p) => p.key === (key || "").trim());
  return found ?? RESEARCH_PROVIDERS[0];
}

/** True when the form has enough to attempt a search. */
export function researchIsComplete(research: Record<string, string>): boolean {
  const provider = researchProvider(research.provider);
  const endpoint = (research.endpoint || provider.defaultEndpoint).trim();
  if (!endpoint) return false;
  return !provider.needsKey || (research.api_key || "").trim() !== "";
}
