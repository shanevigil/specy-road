import { describe, expect, it } from "vitest";

import {
  RESEARCH_PROVIDERS,
  researchIsComplete,
  researchProvider,
} from "./researchProviders";

describe("researchProvider", () => {
  it("falls back to the first provider for anything it does not know", () => {
    expect(researchProvider(undefined).key).toBe("bing");
    expect(researchProvider("").key).toBe("bing");
    expect(researchProvider("not-a-provider").key).toBe("bing");
  });

  it("finds each provider it does know", () => {
    for (const p of RESEARCH_PROVIDERS) {
      expect(researchProvider(p.key).label).toBe(p.label);
    }
  });
});

describe("researchIsComplete", () => {
  it("accepts a key provider once it has a key, using the default endpoint", () => {
    expect(researchIsComplete({ provider: "tavily" })).toBe(false);
    expect(researchIsComplete({ provider: "tavily", api_key: "k" })).toBe(true);
  });

  it("accepts a keyless provider once it has an endpoint", () => {
    expect(researchIsComplete({ provider: "searxng" })).toBe(false);
    expect(
      researchIsComplete({
        provider: "searxng",
        endpoint: "https://searx.example/search",
      }),
    ).toBe(true);
  });

  it("treats whitespace as missing", () => {
    expect(researchIsComplete({ provider: "tavily", api_key: "   " })).toBe(false);
    expect(researchIsComplete({ provider: "searxng", endpoint: "  " })).toBe(false);
  });
});

describe("the provider table", () => {
  it("gives every provider a distinct key", () => {
    const keys = RESEARCH_PROVIDERS.map((p) => p.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("gives every hosted provider an https default endpoint", () => {
    for (const p of RESEARCH_PROVIDERS.filter((x) => x.defaultEndpoint)) {
      expect(p.defaultEndpoint.startsWith("https://")).toBe(true);
    }
  });

  it("leaves the self-hosted provider without a default", () => {
    // There is no such thing as the public SearXNG instance.
    expect(researchProvider("searxng").defaultEndpoint).toBe("");
    expect(researchProvider("searxng").needsKey).toBe(false);
  });
});
