/**
 * Per-row pending-mutation state machine, decoupled from React.
 *
 * The PM Gantt UI applies mutations optimistically — the dragged row
 * snaps to its new position immediately and pulses blue while the
 * server write completes. This module owns the bookkeeping (which
 * tokens are active, which rows they cover, what phase each is in)
 * and exposes plain methods that any host (React hook, tests, etc.)
 * can drive.
 *
 * Lifecycle of one mutation token:
 *
 *   begin(token, ids, kind)   → rows enter "active" phase
 *   end(token)                → server returned 200 → "settling" phase
 *                                for ``SETTLE_MS`` ms, then cleared
 *   fail(token)               → server returned an error → "fail" phase
 *                                for ``FAIL_MS`` ms, then cleared
 *
 * A row may be referenced by multiple tokens; the strongest phase wins
 * (fail > active > settling) for visual class selection.
 */

export type PendingKind =
  | "reorder"
  | "move"
  | "indent"
  | "outdent"
  | "dep"
  | "add"
  | "delete";

export type PendingPhase = "active" | "settling" | "fail";

export type PendingEntry = {
  ids: string[];
  kind: PendingKind;
  phase: PendingPhase;
  startedAt: number;
};

/** Window during which the pulse continues to fade after a successful save. */
export const SETTLE_MS = 250;
/** Window during which the failure pulse plays. */
export const FAIL_MS = 400;

const PHASE_RANK: Record<PendingPhase, number> = {
  fail: 3,
  active: 2,
  settling: 1,
};

export type PendingMutationsApi = {
  /** Set of display ids currently in any non-cleared phase. */
  readonly pendingIds: ReadonlySet<string>;
  /** Strongest kind/phase observed for ``id`` across active tokens. */
  pendingFor(id: string): { kind: PendingKind; phase: PendingPhase } | null;
};

export type PendingControls = {
  begin(token: string, ids: string[], kind: PendingKind): void;
  end(token: string): void;
  fail(token: string): void;
  /** Free any pending timers (call from cleanup). */
  dispose(): void;
};

export type PendingStore = PendingMutationsApi & PendingControls;

type ScheduleFn = (fn: () => void, ms: number) => unknown;
type CancelFn = (handle: unknown) => void;

export type PendingStoreOptions = {
  /** Listener fired after every state change. */
  onChange: () => void;
  /** Override timers for tests. */
  schedule?: ScheduleFn;
  cancel?: CancelFn;
};

/**
 * Build a host-agnostic pending-mutations store. The host (React hook
 * or test driver) supplies an ``onChange`` callback that triggers a
 * re-read of ``pendingIds`` / ``pendingFor``.
 */
export function createPendingStore(opts: PendingStoreOptions): PendingStore {
  const entries = new Map<string, PendingEntry>();
  const timers = new Map<string, unknown>();
  const schedule: ScheduleFn = opts.schedule ?? ((fn, ms) => setTimeout(fn, ms));
  const cancel: CancelFn = opts.cancel ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));

  const clearTimer = (token: string) => {
    const t = timers.get(token);
    if (t != null) {
      cancel(t);
      timers.delete(token);
    }
  };

  const remove = (token: string) => {
    clearTimer(token);
    if (entries.delete(token)) opts.onChange();
  };

  const transition = (
    token: string,
    phase: PendingPhase,
    holdMs: number,
  ) => {
    const cur = entries.get(token);
    if (!cur) return;
    entries.set(token, { ...cur, phase });
    clearTimer(token);
    timers.set(
      token,
      schedule(() => remove(token), holdMs),
    );
    opts.onChange();
  };

  const buildIndex = () => {
    const ids = new Set<string>();
    const byId = new Map<string, { kind: PendingKind; phase: PendingPhase }>();
    for (const entry of entries.values()) {
      for (const id of entry.ids) {
        ids.add(id);
        const cur = byId.get(id);
        if (!cur || PHASE_RANK[entry.phase] > PHASE_RANK[cur.phase]) {
          byId.set(id, { kind: entry.kind, phase: entry.phase });
        }
      }
    }
    return { ids, byId };
  };

  return {
    get pendingIds() {
      return buildIndex().ids;
    },
    pendingFor(id) {
      return buildIndex().byId.get(id) ?? null;
    },
    begin(token, ids, kind) {
      clearTimer(token);
      entries.set(token, {
        ids: [...ids],
        kind,
        phase: "active",
        startedAt: Date.now(),
      });
      opts.onChange();
    },
    end(token) {
      transition(token, "settling", SETTLE_MS);
    },
    fail(token) {
      transition(token, "fail", FAIL_MS);
    },
    dispose() {
      for (const t of timers.values()) cancel(t);
      timers.clear();
      entries.clear();
    },
  };
}

/** ``crypto.randomUUID()`` if available, otherwise a base-36 fallback. */
export function nextPendingToken(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `pm-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}
