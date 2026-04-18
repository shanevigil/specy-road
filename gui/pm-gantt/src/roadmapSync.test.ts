import { describe, expect, it, vi } from "vitest";
import { createSerialQueue } from "./roadmapSync";

describe("createSerialQueue", () => {
  it("runs enqueued tasks in order when scheduled back-to-back", async () => {
    const order: string[] = [];
    const q = createSerialQueue();

    const p1 = q.enqueue(async () => {
      order.push("a-start");
      await Promise.resolve();
      order.push("a-end");
    });
    const p2 = q.enqueue(async () => {
      order.push("b-start");
      await Promise.resolve();
      order.push("b-end");
    });

    await Promise.all([p1, p2]);

    expect(order).toEqual(["a-start", "a-end", "b-start", "b-end"]);
  });

  it("continues after a rejected task", async () => {
    const q = createSerialQueue();
    const spy = vi.fn();

    await q
      .enqueue(async () => {
        throw new Error("x");
      })
      .catch(() => {});
    await q.enqueue(async () => {
      spy();
    });

    expect(spy).toHaveBeenCalledTimes(1);
  });
});
