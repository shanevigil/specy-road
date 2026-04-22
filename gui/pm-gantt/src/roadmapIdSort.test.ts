import { describe, expect, it, vi } from "vitest";

import { compareRoadmapIds, naturalIdSortKey } from "./roadmapIdSort";

describe("compareRoadmapIds", () => {
  it("orders M1.2 before M1.10 when sibling_order ties (not lexical)", () => {
    const ids = ["M1.10", "M1.2", "M1.1"];
    expect([...ids].sort(compareRoadmapIds)).toEqual(["M1.1", "M1.2", "M1.10"]);
  });

  it("orders nested segments naturally (M2.1.10 after M2.1.2)", () => {
    const ids = ["M2.1.10", "M2.1.2", "M2.1.1"];
    expect([...ids].sort(compareRoadmapIds)).toEqual(["M2.1.1", "M2.1.2", "M2.1.10"]);
  });

  it("falls back to lexical when parseInt rejects a digit run", () => {
    const orig = Number.parseInt;
    const spy = vi.spyOn(Number, "parseInt").mockImplementation((s: string, radix?: number) => {
      if (s === "10" && (radix === 10 || radix === undefined)) return Number.NaN;
      return orig(s, radix as number);
    });
    expect(naturalIdSortKey("M1.10")).toEqual([[1, "M1.10"]]);
    spy.mockRestore();
  });
});
