import { describe, expect, it } from "vitest";
import {
  canTriage,
  filterIdeas,
  ideaCounts,
  promotableCount,
  recommendationRank,
  sortIdeasForTriage,
} from "./brainstormIdeas";
import type { BrainstormIdea } from "./types";

function idea(over: Partial<BrainstormIdea> = {}): BrainstormIdea {
  return {
    id: "B1",
    title: "An idea",
    rationale: "",
    kind: "feature",
    effort: "",
    evidence: [],
    status: "proposed",
    recommendation: null,
    promoted_node_key: null,
    ...over,
  };
}

describe("ideaCounts", () => {
  it("counts each triage state", () => {
    const counts = ideaCounts([
      idea({ id: "B1", status: "proposed" }),
      idea({ id: "B2", status: "accepted" }),
      idea({ id: "B3", status: "accepted" }),
      idea({ id: "B4", status: "rejected" }),
      idea({ id: "B5", status: "revised" }),
    ]);

    expect(counts.proposed).toBe(1);
    expect(counts.accepted).toBe(2);
    expect(counts.rejected).toBe(1);
    expect(counts.revised).toBe(1);
  });

  it("counts promoted ideas separately from their status", () => {
    const counts = ideaCounts([
      idea({ status: "accepted", promoted_node_key: "abc" }),
      idea({ id: "B2", status: "accepted" }),
    ]);

    expect(counts.accepted).toBe(2);
    expect(counts.promoted).toBe(1);
  });

  it("handles an empty session", () => {
    expect(ideaCounts([]).proposed).toBe(0);
  });
});

describe("canTriage", () => {
  it("allows triage until the idea becomes a node", () => {
    expect(canTriage(idea())).toBe(true);
    expect(canTriage(idea({ promoted_node_key: "abc" }))).toBe(false);
  });
});

describe("recommendationRank", () => {
  it("orders strong before consider before park", () => {
    expect(recommendationRank("strong")).toBeLessThan(
      recommendationRank("consider"),
    );
    expect(recommendationRank("consider")).toBeLessThan(
      recommendationRank("park"),
    );
  });

  it("puts unassessed ideas last", () => {
    expect(recommendationRank(null)).toBeGreaterThan(
      recommendationRank("park"),
    );
  });

  it("does not crash on an unknown verdict", () => {
    expect(recommendationRank("nonsense")).toBe(3);
  });
});

describe("sortIdeasForTriage", () => {
  it("leads with the strongest recommendation", () => {
    const sorted = sortIdeasForTriage([
      idea({ id: "B1", recommendation: "park" }),
      idea({ id: "B2", recommendation: null }),
      idea({ id: "B3", recommendation: "strong" }),
      idea({ id: "B4", recommendation: "consider" }),
    ]);

    expect(sorted.map((i) => i.id)).toEqual(["B3", "B4", "B1", "B2"]);
  });

  it("sinks promoted ideas regardless of their verdict", () => {
    const sorted = sortIdeasForTriage([
      idea({ id: "B1", recommendation: "strong", promoted_node_key: "abc" }),
      idea({ id: "B2", recommendation: "park" }),
    ]);

    expect(sorted.map((i) => i.id)).toEqual(["B2", "B1"]);
  });

  it("keeps insertion order for ties so ids stay readable", () => {
    const sorted = sortIdeasForTriage([
      idea({ id: "B1", recommendation: "strong" }),
      idea({ id: "B2", recommendation: "strong" }),
      idea({ id: "B3", recommendation: "strong" }),
    ]);

    expect(sorted.map((i) => i.id)).toEqual(["B1", "B2", "B3"]);
  });

  it("does not mutate the input", () => {
    const input = [
      idea({ id: "B1", recommendation: "park" }),
      idea({ id: "B2", recommendation: "strong" }),
    ];

    sortIdeasForTriage(input);

    expect(input.map((i) => i.id)).toEqual(["B1", "B2"]);
  });
});

describe("filterIdeas", () => {
  const ideas = [
    idea({ id: "B1", status: "accepted" }),
    idea({ id: "B2", status: "rejected" }),
  ];

  it("returns everything for 'all' or empty", () => {
    expect(filterIdeas(ideas, "all")).toHaveLength(2);
    expect(filterIdeas(ideas, "")).toHaveLength(2);
  });

  it("filters to one status", () => {
    expect(filterIdeas(ideas, "accepted").map((i) => i.id)).toEqual(["B1"]);
  });
});

describe("promotableCount", () => {
  it("counts accepted ideas that have not landed yet", () => {
    expect(
      promotableCount([
        idea({ id: "B1", status: "accepted" }),
        idea({ id: "B2", status: "accepted", promoted_node_key: "abc" }),
        idea({ id: "B3", status: "proposed" }),
      ]),
    ).toBe(1);
  });

  it("is zero when nothing is accepted", () => {
    expect(promotableCount([idea()])).toBe(0);
  });
});
