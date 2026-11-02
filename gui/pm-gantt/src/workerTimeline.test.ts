import { describe, expect, it } from "vitest";
import {
  formatCost,
  formatSeconds,
  isToolCall,
  phaseSegments,
} from "./workerTimeline";

describe("phaseSegments", () => {
  it("sizes each known phase by its share of the known total, in order", () => {
    const segs = phaseSegments({
      delegated_to_launched: 3,
      launched_to_first_output: 2,
      first_output_to_end: 15,
      end_to_acked: null,
    });
    expect(segs.map((s) => s.name)).toEqual([
      "delegated_to_launched",
      "launched_to_first_output",
      "first_output_to_end",
      "end_to_acked",
    ]);
    expect(segs.map((s) => s.pct)).toEqual([15, 10, 75, 0]);
    expect(segs[0].label).toBe("delegated → launched");
    expect(segs[3].seconds).toBeNull();
  });

  it("gives no width to anything when every phase is unknown or zero", () => {
    const segs = phaseSegments({ a_to_b: null, b_to_c: 0 });
    expect(segs.map((s) => s.pct)).toEqual([0, 0]);
  });
});

describe("formatSeconds / formatCost", () => {
  it.each([
    [null, "unknown"],
    [42.4, "42s"],
    [185, "3m 05s"],
    [3720, "1h 02m"],
  ])("renders %s as %s", (s, expected) => {
    expect(formatSeconds(s)).toBe(expected);
  });

  it("keeps an unreported cost distinct from zero", () => {
    expect(formatCost(null)).toBe("$?");
    expect(formatCost(0)).toBe("$0.0000");
    expect(formatCost(0.75, true)).toBe("$0.7500 est.");
  });
});

describe("isToolCall", () => {
  const out = (summary: string, source = "worker") => ({
    type: "output",
    source,
    summary,
  });
  it("recognises each harness's tool-call line and nothing else", () => {
    expect(isToolCall(out("(tool use)"))).toBe(true);
    expect(isToolCall(out("tool call started"))).toBe(true);
    expect(isToolCall(out("command_execution done"))).toBe(true);
    expect(isToolCall(out("reasoning done"))).toBe(false);
    expect(isToolCall(out("Implemented the route."))).toBe(false);
    expect(isToolCall(out("(tool use)", "system"))).toBe(false);
  });
});
