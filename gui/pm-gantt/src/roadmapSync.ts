import { useCallback, useEffect, useRef, useState } from "react";

/** Lock kicks in when this many mutations are in flight + queued. */
export const QUEUE_DEPTH_LOCK_THRESHOLD = 3;

/** Lock releases only once the queue has drained back to ≤ this depth. */
export const QUEUE_DEPTH_LOCK_RELEASE = 1;

/**
 * Pure state-machine step for the sticky overload lock — exposed so the
 * behavior can be unit-tested without a React renderer.
 *
 * Returns the next overload state given the current state and the
 * latest queue depth.
 */
export function nextOverloaded(currentlyOverloaded: boolean, depth: number): boolean {
  if (!currentlyOverloaded && depth >= QUEUE_DEPTH_LOCK_THRESHOLD) return true;
  if (currentlyOverloaded && depth <= QUEUE_DEPTH_LOCK_RELEASE) return false;
  return currentlyOverloaded;
}

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
 *
 * In addition to the basic ``busy`` / ``busyLabel`` signals, exposes a
 * **sticky overload lock** so the UI can keep accepting new input
 * while the queue is shallow but stop the user from piling on once
 * the queue is deep:
 *
 *   - ``queueDepth``: number of in-flight + queued actions.
 *   - ``queueOverloaded``: true once depth has hit
 *     :data:`QUEUE_DEPTH_LOCK_THRESHOLD`; remains true until depth
 *     drains back to :data:`QUEUE_DEPTH_LOCK_RELEASE`. The release
 *     point is below the trip point on purpose so a user can't
 *     immediately repile the queue back to the threshold and stay
 *     locked forever.
 */
export function useRoadmapActionQueue() {
  const queueRef = useRef<ReturnType<typeof createSerialQueue> | null>(null);
  if (!queueRef.current) queueRef.current = createSerialQueue();

  const [busyDepth, setBusyDepth] = useState(0);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [overloaded, setOverloaded] = useState(false);

  // Sticky lock: tripped at THRESHOLD, released at RELEASE.
  useEffect(() => {
    const next = nextOverloaded(overloaded, busyDepth);
    if (next !== overloaded) setOverloaded(next);
  }, [busyDepth, overloaded]);

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

  return {
    busy,
    busyDepth,
    busyLabel,
    queueOverloaded: overloaded,
    runRoadmapAction,
  };
}
