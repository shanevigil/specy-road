import { useEffect, useState } from "react";
import type { PublishStatusPayload } from "../types";
import { ModalFrame } from "./ModalFrame";

const DEFAULT_MESSAGE = "roadmap: update plan";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Latest status; refreshed when opening and after publish. */
  status: PublishStatusPayload | null;
  onRefreshStatus: () => Promise<void>;
  onPublish: (message: string) => Promise<void>;
  headerMinTop: number;
  /** Stack above task dialogs (default 200). */
  zIndex?: number;
};

export function PublishRoadmapModal({
  open,
  onClose,
  status,
  onRefreshStatus,
  onPublish,
  headerMinTop,
  zIndex = 200,
}: Props) {
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [publishing, setPublishing] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLocalErr(null);
    setMessage(DEFAULT_MESSAGE);
    void onRefreshStatus();
  }, [open, onRefreshStatus]);

  if (!open) return null;

  const canPublish = Boolean(status?.can_publish) && !publishing;
  const blocked = Boolean(status?.blocked);
  const detail = status?.detail ?? null;

  const onSubmit = async () => {
    const m = message.trim();
    if (!m) {
      setLocalErr("Enter a short description for this update.");
      return;
    }
    setLocalErr(null);
    setPublishing(true);
    try {
      await onPublish(m);
      onClose();
    } catch (e: unknown) {
      setLocalErr(String(e));
    } finally {
      setPublishing(false);
    }
  };

  return (
    <ModalFrame
      title="Publish roadmap changes"
      titleId="publish-roadmap-title"
      onClose={onClose}
      storageKey="publish-roadmap"
      minTop={headerMinTop}
      zIndex={zIndex}
      bodyClassName="modal-body--publish"
      footer={
        <div className="modal-footer-actions">
          <button
            type="button"
            className="publish-modal-btn publish-modal-btn--ghost"
            disabled={publishing}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="publish-modal-btn publish-modal-btn--primary"
            disabled={!canPublish}
            onClick={() => void onSubmit()}
          >
            {publishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      }
    >
      <p className="outline-meta">
        Saves your roadmap, planning, and governance files to git and pushes to
        the remote so the team can see them. Your edits are already saved on
        this computer; publishing shares them.
      </p>
      {status ? (
        <div className="publish-roadmap-meta">
          <div>
            <span className="publish-roadmap-meta-label">Branch</span>{" "}
            <code>{status.current_branch ?? "—"}</code>
          </div>
          {status.upstream ? (
            <div>
              <span className="publish-roadmap-meta-label">Upstream</span>{" "}
              <code>{status.upstream}</code>
            </div>
          ) : null}
        </div>
      ) : null}

      {blocked && detail ? (
        <div className="publish-roadmap-blocked" role="alert">
          <p>{detail}</p>
          {status && status.out_of_scope_paths.length > 0 ? (
            <ul className="publish-roadmap-path-list">
              {status.out_of_scope_paths.slice(0, 12).map((p) => (
                <li key={p}>
                  <code>{p}</code>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="outline-meta">
            Ask a developer if you are unsure how to fix this.
          </p>
        </div>
      ) : null}

      {!blocked && status?.scope_dirty && status.scope_paths.length > 0 ? (
        <div className="publish-roadmap-scope">
          <span className="publish-roadmap-meta-label">Changed files</span>
          <ul className="publish-roadmap-path-list">
            {status.scope_paths.slice(0, 20).map((p) => (
              <li key={p}>
                <code>{p}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <label className="publish-roadmap-label" htmlFor="publish-message">
        Summary for teammates
      </label>
      <input
        id="publish-message"
        type="text"
        className="publish-roadmap-input"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        disabled={publishing}
        autoComplete="off"
        spellCheck
        maxLength={500}
      />

      {localErr ? (
        <p className="modal-review-error" role="alert">
          {localErr}
        </p>
      ) : null}
    </ModalFrame>
  );
}
