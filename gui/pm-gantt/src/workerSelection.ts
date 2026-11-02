/**
 * Which worker the Workers drawer shows (M10.12), kept outside React so the
 * out-of-order case is testable without a DOM.
 *
 * Every `select` supersedes the one before it: the earlier request is
 * aborted, and its response or error is dropped even if it still arrives, so
 * a slow reply for worker A can never replace worker B's details. The previous
 * details are cleared as soon as a new selection starts.
 */

export type WorkerSelectionState<D> = {
  selected: string | null;
  detail: D | null;
  loading: boolean;
  error: string | null;
};

export type WorkerSelection = {
  select: (id: string) => Promise<void>;
  clear: () => void;
};

export function createWorkerSelection<D>(
  fetchDetail: (id: string, signal: AbortSignal) => Promise<D>,
  onChange: (state: WorkerSelectionState<D>) => void,
): WorkerSelection {
  let state: WorkerSelectionState<D> = {
    selected: null,
    detail: null,
    loading: false,
    error: null,
  };
  let token = 0;
  let ctrl: AbortController | null = null;
  const set = (patch: Partial<WorkerSelectionState<D>>) => {
    state = { ...state, ...patch };
    onChange(state);
  };
  const supersede = () => {
    token += 1;
    ctrl?.abort();
    ctrl = new AbortController();
    return { mine: token, signal: ctrl.signal };
  };
  return {
    async select(id) {
      const { mine, signal } = supersede();
      set({ selected: id, detail: null, loading: true, error: null });
      try {
        const detail = await fetchDetail(id, signal);
        if (mine === token) set({ detail, loading: false });
      } catch (e: unknown) {
        if (mine === token) set({ loading: false, error: String(e) });
      }
    },
    clear() {
      supersede();
      set({ selected: null, detail: null, loading: false, error: null });
    },
  };
}
