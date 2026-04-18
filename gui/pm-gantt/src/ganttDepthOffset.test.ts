import { describe, expect, it } from "vitest";
import { minDependencyDepth } from "./ganttDepthOffset";

describe("minDependencyDepth", () => {
  it("returns 0 for empty ids", () => {
    expect(minDependencyDepth([], {})).toBe(0);
  });

  it("returns minimum depth among visible ids", () => {
    expect(
      minDependencyDepth(["a", "b"], { a: 15, b: 12, c: 0 }),
    ).toBe(12);
  });

  it("treats missing depth as 0", () => {
    expect(minDependencyDepth(["x"], {})).toBe(0);
  });
});
