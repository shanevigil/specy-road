import { describe, expect, it } from "vitest";
import { shouldRefreshSnapshotFromViewFingerprint } from "./api";

describe("shouldRefreshSnapshotFromViewFingerprint", () => {
  it("is false on first poll when previous is null (avoid reload storm)", () => {
    expect(shouldRefreshSnapshotFromViewFingerprint(null, "1")).toBe(false);
  });

  it("is true when the view token changed", () => {
    expect(shouldRefreshSnapshotFromViewFingerprint("1", "2")).toBe(true);
  });

  it("is false when unchanged", () => {
    expect(shouldRefreshSnapshotFromViewFingerprint("1", "1")).toBe(false);
  });
});
