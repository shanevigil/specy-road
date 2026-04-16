import { describe, expect, it } from "vitest";
import { contiguousSubtreeIds } from "./outlineSubtree";

describe("contiguousSubtreeIds", () => {
  it("returns single id for a leaf", () => {
    expect(
      contiguousSubtreeIds(["a", "b"], [0, 0], "b"),
    ).toEqual(["b"]);
  });

  it("includes direct children and stops at next sibling depth", () => {
    const ids = ["root", "c1", "c2", "sib"];
    const depths = [0, 1, 1, 0];
    expect(contiguousSubtreeIds(ids, depths, "root")).toEqual([
      "root",
      "c1",
      "c2",
    ]);
  });

  it("includes nested descendants", () => {
    const ids = ["a", "b", "c", "d"];
    const depths = [0, 1, 2, 0];
    expect(contiguousSubtreeIds(ids, depths, "a")).toEqual(["a", "b", "c"]);
  });

  it("returns empty when root id is missing", () => {
    expect(contiguousSubtreeIds(["x"], [0], "missing")).toEqual([]);
  });
});
