/**
 * Status strip for modals with autosave: keeps a fixed footer bar so "Saving…"
 * does not mount/unmount the whole footer and shift the dialog body.
 */
export function ModalPersistStatusFooter({
  msg,
  persistMsg,
}: {
  msg: string | null;
  persistMsg: string | null;
}) {
  return (
    <div className="modal-persist-status-footer">
      <span className="modal-persist-status-footer__msg">{msg ?? ""}</span>
      <span className="modal-persist-status-footer__persist" aria-live="polite">
        {persistMsg ?? ""}
      </span>
    </div>
  );
}
