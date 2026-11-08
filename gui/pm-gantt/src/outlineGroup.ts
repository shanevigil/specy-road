/**
 * The outline's "Group siblings…" dialog.
 *
 * Confirm sends one ``POST /api/outline/group`` (``specy-road group-nodes``)
 * with ``GroupOutlineBody``'s fields. The server owns every other rule (a
 * taken or malformed id, a locked milestone, a gate parent) and answers a
 * refusal with a 400 detail that the dialog shows verbatim.
 */

/** Parent types the dialog offers; the server refuses a gate parent. */
export const GROUP_TYPES = ["milestone", "phase", "task"] as const;

export const GROUP_TITLE_MESSAGE = "Enter a title for the new parent.";
export const GROUP_NONE_CHECKED_MESSAGE = "Check at least one row to group.";

/** ``GroupOutlineBody`` in ``specy_road/gui_app_models.py``. */
export type GroupOutlineBody = {
  into_new: string;
  title: string;
  node_ids: string[];
  type: string;
  rewrite_refs: boolean;
};

export type GroupDialogState = {
  /** The row and its siblings, in outline order. */
  siblingIds: readonly string[];
  checked: ReadonlySet<string>;
  intoNew: string;
  title: string;
  type: string;
  rewriteRefs: boolean;
};

export type GroupBodyResult =
  | { ok: true; body: GroupOutlineBody }
  | { ok: false; message: string };

type OutlineRow = { parent_id?: string | null };

function parentOf(row: OutlineRow | undefined): string | null {
  return row?.parent_id || null;
}

/**
 * One past the highest child number among ``siblingIds`` (``parentId.k``,
 * ``Mk`` at the root); gaps are kept, as ``add-node`` keeps them. A sibling
 * whose id is not ``parentId`` plus one number (an edge-only re-parent keeps
 * its old id) does not count.
 */
function nextChildId(parentId: string | null, siblingIds: readonly string[]): string {
  const prefix = parentId == null ? "M" : `${parentId}.`;
  const numbers = siblingIds
    .map((id) => (id.startsWith(prefix) ? id.slice(prefix.length) : ""))
    .filter((rest) => /^\d+$/.test(rest))
    .map(Number);
  return `${prefix}${Math.max(0, ...numbers) + 1}`;
}

/**
 * The dialog's opening state for ``rowId``: its siblings from the loaded
 * outline (``orderedIds``), only ``rowId`` checked, the parent's next child
 * id, no title, a milestone, and prose references left alone.
 */
export function groupDialogState(
  orderedIds: readonly string[],
  byId: Readonly<Record<string, OutlineRow>>,
  rowId: string,
): GroupDialogState {
  const parentId = parentOf(byId[rowId]);
  const siblingIds = orderedIds.filter((id) => parentOf(byId[id]) === parentId);
  return {
    siblingIds,
    checked: new Set([rowId]),
    intoNew: nextChildId(parentId, siblingIds),
    title: "",
    type: "milestone",
    rewriteRefs: false,
  };
}

/** The request body for ``state``, with the checked rows in outline order. */
export function groupBody(state: GroupDialogState): GroupBodyResult {
  const title = state.title.trim();
  if (!title) return { ok: false, message: GROUP_TITLE_MESSAGE };
  const nodeIds = state.siblingIds.filter((id) => state.checked.has(id));
  if (nodeIds.length === 0) return { ok: false, message: GROUP_NONE_CHECKED_MESSAGE };
  return {
    ok: true,
    body: {
      into_new: state.intoNew,
      title,
      node_ids: nodeIds,
      type: state.type,
      rewrite_refs: state.rewriteRefs,
    },
  };
}
