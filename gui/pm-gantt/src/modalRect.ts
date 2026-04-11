export type ModalRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

/** Inset from each viewport edge (5%). */
const MARGIN = 0.05;

const MIN_W = 320;
const MIN_H = 220;

const STORAGE_PREFIX = "pm-modal-rect:";

export type ClampRectOpts = {
  /** Keep the window top at or below this viewport Y (e.g. below app header). */
  minTop?: number;
};

/** Clamp size and position to the viewport (optionally below a minimum top). */
export function clampRectToViewport(
  r: ModalRect,
  opts?: ClampRectOpts,
): ModalRect {
  const vw = typeof window !== "undefined" ? window.innerWidth : 800;
  const vh = typeof window !== "undefined" ? window.innerHeight : 600;
  const minTop = opts?.minTop ?? 0;
  let { left, top, width, height } = r;
  width = Math.min(Math.max(width, MIN_W), vw);
  height = Math.min(Math.max(height, MIN_H), vh);
  left = Math.min(Math.max(left, 0), Math.max(0, vw - width));
  top = Math.min(Math.max(top, minTop), Math.max(minTop, vh - height));
  return { left, top, width, height };
}

export function getDefaultModalRect(): ModalRect {
  const vw = typeof window !== "undefined" ? window.innerWidth : 800;
  const vh = typeof window !== "undefined" ? window.innerHeight : 600;
  return {
    left: vw * MARGIN,
    top: vh * MARGIN,
    width: vw * (1 - 2 * MARGIN),
    height: vh * (1 - 2 * MARGIN),
  };
}

/**
 * Smaller, left-anchored preset so the Gantt chart on the right stays visible.
 * ``minTop`` keeps the dialog below the app header (or other chrome).
 */
export function getDefaultEditModalRect(opts?: { minTop?: number }): ModalRect {
  const vw = typeof window !== "undefined" ? window.innerWidth : 800;
  const vh = typeof window !== "undefined" ? window.innerHeight : 600;
  const minTop = opts?.minTop ?? 0;
  const marginX = vw * 0.03;
  const suggestedTop = vh * 0.06;
  const top = Math.max(suggestedTop, minTop + 6);
  const bottomMargin = Math.max(16, vh * 0.05);
  return clampRectToViewport(
    {
      left: marginX,
      top,
      width: vw * 0.58,
      height: Math.max(MIN_H, vh - top - bottomMargin),
    },
    { minTop },
  );
}

/** Right-docked settings panel: fixed width, full height minus margins (not resizable). */
export function getDefaultSettingsModalRect(): ModalRect {
  const vw = typeof window !== "undefined" ? window.innerWidth : 800;
  const vh = typeof window !== "undefined" ? window.innerHeight : 600;
  const margin = Math.min(16, Math.max(8, vw * 0.015));
  const width = Math.min(520, Math.max(320, Math.floor(vw * 0.36)));
  return {
    left: vw - width - margin,
    top: margin,
    width,
    height: vh - 2 * margin,
  };
}

function isModalRect(x: unknown): x is ModalRect {
  if (typeof x !== "object" || x === null) return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.left === "number" &&
    typeof o.top === "number" &&
    typeof o.width === "number" &&
    typeof o.height === "number" &&
    Number.isFinite(o.left) &&
    Number.isFinite(o.top) &&
    Number.isFinite(o.width) &&
    Number.isFinite(o.height)
  );
}

export function loadStoredModalRect(storageKey: string): ModalRect | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + storageKey);
    if (!raw) return null;
    const j = JSON.parse(raw) as unknown;
    if (!isModalRect(j)) return null;
    return j;
  } catch {
    return null;
  }
}

export function saveStoredModalRect(storageKey: string, r: ModalRect): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + storageKey, JSON.stringify(r));
  } catch {
    /* ignore quota / private mode */
  }
}
