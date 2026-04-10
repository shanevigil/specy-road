export type ModalRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

/** Inset from each viewport edge (5%). */
const MARGIN = 0.05;

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
