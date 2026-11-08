/**
 * Outline row click versus double-click, and the selection a toolbar action reads.
 *
 * A click selects immediately. A second click on the same row inside
 * {@link DOUBLE_CLICK_MS} opens the edit modal and does not select again.
 * The timer only ends that window; it does not delay the selection.
 */

/** Same window the row used to wait before selecting, so a double click still opens. */
export const DOUBLE_CLICK_MS = 220;

export type RowClickDecision = "select" | "open" | "ignore";

export type OutlineRowClick = {
  /** One primary click on `id`. `titleEditing` selects nothing and opens nothing. */
  click(id: string, opts?: { titleEditing?: boolean }): RowClickDecision;
  /** Row selected by the most recent selecting click. */
  selectedId(): string | null;
  /** Selection a toolbar action uses at the moment it runs. */
  toolbarTarget(): string | null;
  /** Drop a pending double-click window (id click, long press, row double-click). */
  disarm(): void;
};

export function createOutlineRowClick(): OutlineRowClick {
  let selected: string | null = null;
  let armed: { id: string; timer: ReturnType<typeof setTimeout> } | null = null;

  const disarm = () => {
    if (armed == null) return;
    clearTimeout(armed.timer);
    armed = null;
  };

  return {
    click(id, opts) {
      if (opts?.titleEditing) return "ignore";
      if (armed?.id === id) {
        disarm();
        return "open";
      }
      disarm();
      selected = id;
      const timer = setTimeout(() => {
        if (armed?.timer === timer) armed = null;
      }, DOUBLE_CLICK_MS);
      armed = { id, timer };
      return "select";
    },
    selectedId() {
      return selected;
    },
    toolbarTarget() {
      return selected;
    },
    disarm,
  };
}

/**
 * Attributes from `useSortable` for one row.
 *
 * Drag being disabled is not a disabled row: dnd-kit's `aria-disabled` is
 * omitted so the row is not marked disabled.
 */
export function rowDragAttributes<T extends { "aria-disabled"?: boolean }>(
  attributes: T,
  dragDisabled: boolean,
): T {
  if (!dragDisabled || !("aria-disabled" in attributes)) return attributes;
  const next: Record<string, unknown> = { ...attributes };
  delete next["aria-disabled"];
  return next as T;
}
