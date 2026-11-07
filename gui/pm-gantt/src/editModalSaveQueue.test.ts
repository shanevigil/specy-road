import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FileChangedOnDiskError, PmGuiConcurrencyError } from "./api";
import {
  describeSaveFailure,
  EditModalSaveQueue,
  type SaveQueueDeps,
  type SaveStatus,
} from "./editModalSaveQueue";

type Deferred = { resolve: () => void; reject: (e: unknown) => void };

/** Fake server: every call is logged; each request waits until the test settles it. */
function harness(opts: { renameTo?: string } = {}) {
  const log: string[] = [];
  const pending: Deferred[] = [];
  const statuses: SaveStatus[] = [];
  const adopted: (string | null)[] = [];
  let path = "planning/M1_old.md";
  const wait = (label: string) =>
    new Promise<void>((resolve, reject) => {
      log.push(label);
      pending.push({ resolve, reject });
    });
  const deps: SaveQueueDeps = {
    patchNode: vi.fn((pairs) => wait(`patch ${pairs[0].key}=${pairs[0].value}`)),
    resolveSheetPath: vi.fn(async () => {
      if (opts.renameTo) path = opts.renameTo;
      log.push(`resolve -> ${path}`);
      return path;
    }),
    saveSheet: vi.fn((p, c) => wait(`put ${p} ${c}`)),
    refresh: vi.fn(async () => {
      log.push("refresh");
    }),
    onStatus: (s) => statuses.push(s),
    onSheetPathAdopted: (p) => adopted.push(p),
  };
  const q = new EditModalSaveQueue(deps, {
    title: "Old",
    status: "",
    acceptance: "a\nb",
    path: "planning/M1_old.md",
    content: "body",
  });
  const settle = async (fail?: unknown) => {
    const d = pending.shift();
    if (!d) throw new Error("no request in flight");
    if (fail === undefined) d.resolve();
    else d.reject(fail);
    await vi.advanceTimersByTimeAsync(0);
  };
  return { q, deps, log, pending, statuses, adopted, settle };
}

const last = (s: SaveStatus[]) => s[s.length - 1];

describe("EditModalSaveQueue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends one title PATCH however often the same value is re-requested", async () => {
    const h = harness();
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    // Roadmap refreshes re-render the dialog while the PATCH is in flight.
    for (let i = 0; i < 5; i++) {
      h.q.setTitle("New");
      await vi.advanceTimersByTimeAsync(600);
    }
    expect(h.deps.patchNode).toHaveBeenCalledTimes(1);
    await h.settle();
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(1000);
    expect(h.deps.patchNode).toHaveBeenCalledTimes(1);
  });

  it("holds sheet text typed during a rename, then saves it to the new path", async () => {
    const h = harness({ renameTo: "planning/M1_new.md" });
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    h.q.setContent("typed after the title");
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.log).toEqual(["patch title=New"]);
    await h.settle();
    expect(h.log).toEqual([
      "patch title=New",
      "resolve -> planning/M1_new.md",
      "refresh",
      "put planning/M1_new.md typed after the title",
    ]);
    expect(h.adopted).toEqual(["planning/M1_new.md"]);
    expect(h.q.sheetPath).toBe("planning/M1_new.md");
    await h.settle();
    expect(h.pending).toHaveLength(0);
    expect(h.q.hasUnsavedSheet()).toBe(false);
    expect(last(h.statuses)).toEqual({ state: "saved" });
  });

  it("saves the latest text once the earlier save finishes", async () => {
    const h = harness();
    h.q.setContent("one");
    await vi.advanceTimersByTimeAsync(600);
    h.q.setContent("two");
    h.q.setContent("three");
    await vi.advanceTimersByTimeAsync(600);
    expect(h.pending).toHaveLength(1);
    await h.settle();
    expect(h.log).toEqual([
      "put planning/M1_old.md one",
      "refresh",
      "put planning/M1_old.md three",
    ]);
    await h.settle();
    expect(h.q.hasUnsavedSheet()).toBe(false);
  });

  it("reports a failed sheet save and keeps it until the user edits again", async () => {
    const h = harness();
    h.q.setContent("lost?");
    await vi.advanceTimersByTimeAsync(600);
    await h.settle(new Error("planning file missing: planning/M1_old.md"));
    const s = last(h.statuses);
    expect(s.state).toBe("error");
    expect(s.state === "error" && s.message).toContain(
      "Planning sheet not saved: planning file missing: planning/M1_old.md.",
    );
    expect(s.state === "error" && s.message).toContain("still in the editor");
    expect(h.q.hasUnsavedSheet()).toBe(true);
    // No silent retry loop; a re-render with the same text does not resend.
    h.q.setContent("lost?");
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.deps.saveSheet).toHaveBeenCalledTimes(1);
    // A new edit retries, and success clears the error.
    h.q.setContent("lost? no");
    await vi.advanceTimersByTimeAsync(600);
    await h.settle();
    expect(last(h.statuses)).toEqual({ state: "saved" });
  });

  it("retries once after a 412, then reports the conflict", async () => {
    const h = harness();
    const stale = () => new PmGuiConcurrencyError("PM GUI data changed", 412, "9", true);
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    await h.settle(stale());
    expect(h.log).toEqual(["patch title=New", "refresh", "patch title=New"]);
    await h.settle(stale());
    const s = last(h.statuses);
    expect(s.state === "error" && s.message).toContain("Title not saved: PM GUI data changed.");
    expect(h.deps.patchNode).toHaveBeenCalledTimes(2);
  });

  it("still saves the sheet at its old path when the title PATCH fails", async () => {
    const h = harness({ renameTo: "planning/M1_new.md" });
    h.q.setTitle("New");
    h.q.setContent("text");
    await vi.advanceTimersByTimeAsync(600);
    await h.settle(new Error("validation failed"));
    expect(h.log).toEqual(["patch title=New", "put planning/M1_old.md text"]);
    await h.settle();
    const s = last(h.statuses);
    expect(s.state === "error" && s.message).toContain("Title not saved: validation failed.");
  });

  it("holds the sheet when the renamed path cannot be read back", async () => {
    const h = harness();
    h.deps.resolveSheetPath = vi.fn(async () => {
      throw new Error("artifacts: 500");
    });
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    h.q.setContent("text");
    await h.settle();
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.deps.saveSheet).not.toHaveBeenCalled();
    const s = last(h.statuses);
    expect(s.state === "error" && s.message).toContain("Planning sheet not saved: artifacts: 500.");
  });

  it("drops a pending title save when the title becomes invalid", async () => {
    const h = harness();
    h.q.setTitle("Taken");
    h.q.setTitle("Taken", true);
    h.q.setTitle("   ");
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.deps.patchNode).not.toHaveBeenCalled();
    expect(last(h.statuses)).toEqual({ state: "saved" });
  });

  it("flush sends debounced edits at once (dialog closing)", async () => {
    const h = harness();
    h.q.setContent("last words");
    void h.q.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.log).toEqual(["put planning/M1_old.md last words"]);
  });

  it("never sends two node PATCHes at once (gate status and title)", async () => {
    const h = harness();
    h.q.setStatus("Complete");
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    expect(h.log).toEqual(["patch status=Complete"]);
    await h.settle();
    expect(h.log).toEqual(["patch status=Complete", "refresh", "patch title=New"]);
    await h.settle();
    expect(last(h.statuses)).toEqual({ state: "saved" });
  });

  it("saves acceptance as one pair next to an unrelated title edit", async () => {
    const h = harness();
    h.q.setAcceptance("b\na");
    h.q.setTitle("New");
    await vi.advanceTimersByTimeAsync(500);
    expect(h.log).toEqual(["patch acceptance=b\na"]);
    expect(h.deps.patchNode).toHaveBeenCalledWith([{ key: "acceptance", value: "b\na" }]);
    await h.settle();
    expect(h.log).toEqual(["patch acceptance=b\na", "refresh", "patch title=New"]);
    await h.settle();
    expect(last(h.statuses)).toEqual({ state: "saved" });
  });

  it("sends no acceptance PATCH for an unchanged or reverted list", async () => {
    const h = harness();
    h.q.setAcceptance("a\nb");
    await vi.advanceTimersByTimeAsync(5000);
    h.q.setAcceptance("");
    h.q.setAcceptance("a\nb");
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.deps.patchNode).not.toHaveBeenCalled();
  });

  it("ignores values loaded from disk", async () => {
    const h = harness();
    h.q.resetSheet("planning/M1_old.md", "from disk");
    h.q.setContent("from disk");
    h.q.setTitle("Old");
    await vi.advanceTimersByTimeAsync(5000);
    expect(h.log).toEqual([]);
    expect(h.statuses).toEqual([]);
  });
});

describe("describeSaveFailure", () => {
  it("passes the stale-file message through", () => {
    const e = new FileChangedOnDiskError("planning/M1.md", "x");
    expect(describeSaveFailure("sheet", e)).toBe(
      `Planning sheet not saved: ${e.message.replace(/\.$/, "")}.`,
    );
  });
});
