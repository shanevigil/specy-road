import { describe, expect, it } from "vitest";
import { activityKindLabel, formatRelativeAge, lastWorkedTooltip } from "./lastWorked";

const NOW = new Date("2026-06-01T12:00:00Z");

describe("formatRelativeAge", () => {
  it.each([
    ["2026-06-01T11:59:30Z", "now"],
    ["2026-06-01T11:30:00Z", "30m ago"],
    ["2026-06-01T06:00:00Z", "6h ago"],
    ["2026-05-25T12:00:00Z", "7d ago"],
    ["2026-03-01T12:00:00Z", "3mo ago"],
    ["2025-07-15T12:00:00Z", "10mo ago"],
    ["2025-06-01T12:00:00Z", "1y ago"],
    ["2024-06-01T12:00:00Z", "2y ago"],
  ])("renders %s as %s", (iso, expected) => {
    expect(formatRelativeAge(iso, NOW)).toBe(expected);
  });

  it("returns empty string for an unparseable timestamp", () => {
    expect(formatRelativeAge("not-a-date", NOW)).toBe("");
  });

  it("clamps a future timestamp to 'now' rather than showing negative age", () => {
    expect(formatRelativeAge("2026-06-02T12:00:00Z", NOW)).toBe("now");
  });

  it("counts an exact two-year gap as 2y even across a leap day", () => {
    // 730 days: floor-dividing by an average 365.25-day year would say "1y".
    expect(formatRelativeAge("2024-06-01T12:00:00Z", NOW)).toBe("2y ago");
  });

  it("does not skip from days straight past months", () => {
    expect(formatRelativeAge("2026-04-20T12:00:00Z", NOW)).toBe("1mo ago");
  });
});

describe("activityKindLabel", () => {
  it("spells out that a backfill is derived, not observed", () => {
    expect(activityKindLabel("backfilled")).toBe("from git history");
  });

  it("builds a tooltip pairing the reason with the exact timestamp", () => {
    expect(
      lastWorkedTooltip({ at: "2026-05-01T09:12:00+00:00", kind: "finished" }),
    ).toBe("finished — 2026-05-01T09:12:00+00:00");
  });
});
