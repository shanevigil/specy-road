import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  FAIL_MS,
  SETTLE_MS,
  createPendingStore,
  nextPendingToken,
} from "./pendingMutationsCore";

describe("createPendingStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("begin → row is pending with the right kind/phase", () => {
    const onChange = vi.fn();
    const store = createPendingStore({ onChange });
    store.begin("t1", ["M0.1", "M0.2"], "reorder");
    expect(store.pendingIds.has("M0.1")).toBe(true);
    expect(store.pendingIds.has("M0.2")).toBe(true);
    expect(store.pendingFor("M0.1")).toEqual({
      kind: "reorder",
      phase: "active",
    });
    expect(store.pendingFor("M9")).toBeNull();
    expect(onChange).toHaveBeenCalled();
  });

  it("end → row enters settling, clears after SETTLE_MS", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("t1", ["M0.1"], "reorder");
    store.end("t1");
    expect(store.pendingFor("M0.1")).toEqual({
      kind: "reorder",
      phase: "settling",
    });
    vi.advanceTimersByTime(SETTLE_MS + 1);
    expect(store.pendingFor("M0.1")).toBeNull();
    expect(store.pendingIds.has("M0.1")).toBe(false);
  });

  it("fail → row enters fail phase, clears after FAIL_MS", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("t1", ["M0.1"], "delete");
    store.fail("t1");
    expect(store.pendingFor("M0.1")).toEqual({
      kind: "delete",
      phase: "fail",
    });
    vi.advanceTimersByTime(FAIL_MS + 1);
    expect(store.pendingFor("M0.1")).toBeNull();
  });

  it("multiple concurrent tokens tracked independently", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("t1", ["M0.1"], "reorder");
    store.begin("t2", ["M0.1", "M0.2"], "dep");
    expect(store.pendingIds.has("M0.1")).toBe(true);
    expect(store.pendingIds.has("M0.2")).toBe(true);

    store.end("t1");
    // M0.1 still pending (active) via t2; t2 outranks t1's settling.
    expect(store.pendingFor("M0.1")?.phase).toBe("active");
    expect(store.pendingFor("M0.1")?.kind).toBe("dep");

    vi.advanceTimersByTime(SETTLE_MS + 1);
    // t1 cleared; t2 still active.
    expect(store.pendingFor("M0.1")?.phase).toBe("active");

    store.end("t2");
    expect(store.pendingFor("M0.1")?.phase).toBe("settling");
    vi.advanceTimersByTime(SETTLE_MS + 1);
    expect(store.pendingFor("M0.1")).toBeNull();
  });

  it("fail outranks active when both tokens reference the same row", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("good", ["M0.1"], "reorder");
    store.begin("bad", ["M0.1"], "delete");
    store.fail("bad");
    expect(store.pendingFor("M0.1")?.phase).toBe("fail");
    expect(store.pendingFor("M0.1")?.kind).toBe("delete");
  });

  it("re-begin on the same token resets phase to active and cancels prior timer", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("t1", ["M0.1"], "reorder");
    store.end("t1");
    expect(store.pendingFor("M0.1")?.phase).toBe("settling");
    store.begin("t1", ["M0.1"], "reorder");
    expect(store.pendingFor("M0.1")?.phase).toBe("active");
    vi.advanceTimersByTime(SETTLE_MS + 1);
    // Re-begin's prior timer was cancelled; row is still active.
    expect(store.pendingFor("M0.1")?.phase).toBe("active");
  });

  it("dispose() clears all timers and entries", () => {
    const store = createPendingStore({ onChange: () => undefined });
    store.begin("t1", ["M0.1"], "reorder");
    store.begin("t2", ["M0.2"], "reorder");
    store.dispose();
    expect(store.pendingIds.size).toBe(0);
  });
});

describe("nextPendingToken", () => {
  it("returns unique strings", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 100; i++) {
      const t = nextPendingToken();
      expect(typeof t).toBe("string");
      expect(t.length).toBeGreaterThan(8);
      expect(seen.has(t)).toBe(false);
      seen.add(t);
    }
  });
});
