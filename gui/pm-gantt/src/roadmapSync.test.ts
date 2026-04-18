import { describe, expect, it } from "vitest";

import {
  QUEUE_DEPTH_LOCK_RELEASE,
  QUEUE_DEPTH_LOCK_THRESHOLD,
  createSerialQueue,
  nextOverloaded,
} from "./roadmapSync";

describe("nextOverloaded — sticky-lock state machine", () => {
  it("starts unlocked at depth 0", () => {
    expect(nextOverloaded(false, 0)).toBe(false);
  });

  it("stays unlocked below the threshold", () => {
    expect(nextOverloaded(false, 1)).toBe(false);
    expect(nextOverloaded(false, QUEUE_DEPTH_LOCK_THRESHOLD - 1)).toBe(false);
  });

  it("trips at the threshold", () => {
    expect(nextOverloaded(false, QUEUE_DEPTH_LOCK_THRESHOLD)).toBe(true);
  });

  it("trips above the threshold", () => {
    expect(nextOverloaded(false, QUEUE_DEPTH_LOCK_THRESHOLD + 5)).toBe(true);
  });

  it("does NOT release the moment depth drops below threshold", () => {
    // Once tripped, stay locked at depth 2 even though 2 < THRESHOLD.
    expect(nextOverloaded(true, QUEUE_DEPTH_LOCK_THRESHOLD - 1)).toBe(true);
  });

  it("releases only once depth falls to RELEASE or below", () => {
    expect(nextOverloaded(true, QUEUE_DEPTH_LOCK_RELEASE)).toBe(false);
    expect(nextOverloaded(true, 0)).toBe(false);
  });

  it("a roundtrip 1 → 2 → 3 → 2 → 1 → 2 → 3 stays locked once tripped", () => {
    let s = false;
    for (const d of [1, 2, 3]) s = nextOverloaded(s, d);
    expect(s).toBe(true);
    // Depth dips to 2 (still > RELEASE=1) → still locked.
    s = nextOverloaded(s, 2);
    expect(s).toBe(true);
    // Depth dips to 1 → release.
    s = nextOverloaded(s, 1);
    expect(s).toBe(false);
    // Now depth climbs back to 2 — fresh climb, still under threshold.
    s = nextOverloaded(s, 2);
    expect(s).toBe(false);
    // … and only locks again when it crosses the threshold afresh.
    s = nextOverloaded(s, 3);
    expect(s).toBe(true);
  });

  it("RELEASE is below THRESHOLD by design (would loop otherwise)", () => {
    expect(QUEUE_DEPTH_LOCK_RELEASE).toBeLessThan(QUEUE_DEPTH_LOCK_THRESHOLD);
  });
});

describe("createSerialQueue", () => {
  it("runs jobs in FIFO order", async () => {
    const q = createSerialQueue();
    const log: number[] = [];
    const ps: Promise<void>[] = [];
    for (let i = 0; i < 5; i++) {
      ps.push(
        q.enqueue(async () => {
          await new Promise((r) => setTimeout(r, 5));
          log.push(i);
        }),
      );
    }
    await Promise.all(ps);
    expect(log).toEqual([0, 1, 2, 3, 4]);
  });

  it("a failing job does not break the queue", async () => {
    const q = createSerialQueue();
    const log: string[] = [];
    const p1 = q.enqueue(async () => {
      throw new Error("first");
    });
    const p2 = q.enqueue(async () => {
      log.push("second-ran");
    });
    await expect(p1).rejects.toThrow("first");
    await p2;
    expect(log).toEqual(["second-ran"]);
  });
});
