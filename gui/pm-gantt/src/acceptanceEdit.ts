/**
 * Acceptance criteria in the node edit dialog.
 *
 * The dialog saves them through ``PATCH /api/nodes/{id}`` with one pair,
 * ``acceptance=<criteria joined by "\n">``: ``edit-node --set acceptance=``
 * semantics, one criterion per line, surrounding whitespace trimmed, empty
 * lines dropped, and an empty value removes the field. A newline inside one
 * criterion would split it in two on the server, so it is refused here.
 */

export const ACCEPTANCE_NEWLINE_MESSAGE =
  "A criterion is one line: a line break would split it in two. Add another criterion instead.";

export type AcceptanceEdit = { ok: true; value: string } | { ok: false; message: string };

/**
 * The PATCH value for ``draft``; a criterion containing a line break is
 * refused. The edit modal's save queue sends it only when it differs from the
 * saved value, so an unchanged list sends nothing.
 */
export function acceptanceEdit(draft: readonly string[]): AcceptanceEdit {
  if (draft.some((c) => /[\r\n]/.test(c))) {
    return { ok: false, message: ACCEPTANCE_NEWLINE_MESSAGE };
  }
  const value = draft.map((c) => c.trim()).filter(Boolean).join("\n");
  return { ok: true, value };
}
