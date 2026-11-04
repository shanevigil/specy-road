import { describe, expect, it } from "vitest";
import {
  createWorkerSelection,
  type WorkerSelectionState,
} from "./workerSelection";

type Detail = { worker_id: string };

/** A fetch whose replies the test releases one at a time, in any order. */
function controlledFetch() {
  const pending = new Map<
    string,
    { resolve: (d: Detail) => void; reject: (e: Error) => void; signal: AbortSignal }
  >();
  const fetchDetail = (id: string, signal: AbortSignal) =>
    new Promise<Detail>((resolve, reject) => {
      pending.set(id, { resolve, reject, signal });
    });
  return { pending, fetchDetail };
}

function setup() {
  const { pending, fetchDetail } = controlledFetch();
  let shown: WorkerSelectionState<Detail> | null = null;
  const sel = createWorkerSelection(fetchDetail, (s) => {
    shown = s;
  });
  return { pending, sel, shown: () => shown! };
}

describe("createWorkerSelection", () => {
  it("selecting A then B, with B answering before A, keeps B selected and shown", async () => {
    const { pending, sel, shown } = setup();
    const a = sel.select("w-0001");
    const b = sel.select("w-0002");
    // A's details are gone the moment B is selected, and A's request is aborted.
    expect(shown()).toMatchObject({ selected: "w-0002", detail: null, loading: true });
    expect(pending.get("w-0001")!.signal.aborted).toBe(true);
    pending.get("w-0002")!.resolve({ worker_id: "w-0002" });
    await b;
    pending.get("w-0001")!.resolve({ worker_id: "w-0001" });
    await a;
    expect(shown()).toEqual({
      selected: "w-0002",
      detail: { worker_id: "w-0002" },
      loading: false,
      error: null,
    });
  });

  it("a superseded request's error does not replace the newer details", async () => {
    const { pending, sel, shown } = setup();
    const a = sel.select("w-0001");
    const b = sel.select("w-0002");
    pending.get("w-0002")!.resolve({ worker_id: "w-0002" });
    await b;
    pending.get("w-0001")!.reject(new Error("boom"));
    await a;
    expect(shown()).toMatchObject({ selected: "w-0002", detail: { worker_id: "w-0002" }, error: null });
  });

  it("clear drops a request still in flight", async () => {
    const { pending, sel, shown } = setup();
    const a = sel.select("w-0001");
    sel.clear();
    pending.get("w-0001")!.resolve({ worker_id: "w-0001" });
    await a;
    expect(shown()).toEqual({ selected: null, detail: null, loading: false, error: null });
  });
});
