import { useCallback, useRef, useState } from "react";

/**
 * FIFO async mutex: one `fn` runs at a time; failures do not break later jobs.
 */
export function createSerialQueue() {
  let tail = Promise.resolve<void>(undefined);
  return {
    enqueue(fn: () => Promise<void>): Promise<void> {
      const p = tail.then(() => fn());
      tail = p.catch(() => {
        /* keep queue alive */
      });
      return p;
    },
  };
}

/**
 * Serializes roadmap mutations + refreshes so file-backed API calls do not overlap.
 * Each action shows {@link busyLabel} while it runs; queued actions run in FIFO order.
 */
export function useRoadmapActionQueue() {
  const queueRef = useRef<ReturnType<typeof createSerialQueue> | null>(null);
  if (!queueRef.current) queueRef.current = createSerialQueue();

  const [busyDepth, setBusyDepth] = useState(0);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);

  const runRoadmapAction = useCallback((label: string, fn: () => Promise<void>) => {
    return queueRef.current!.enqueue(async () => {
      setBusyLabel(label);
      setBusyDepth((d) => d + 1);
      try {
        await fn();
      } finally {
        setBusyDepth((d) => {
          const next = d - 1;
          if (next === 0) setBusyLabel(null);
          return next;
        });
      }
    });
  }, []);

  const busy = busyDepth > 0;

  return { busy, busyLabel, runRoadmapAction };
}
