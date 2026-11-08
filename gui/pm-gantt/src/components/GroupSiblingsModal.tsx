import { useState } from "react";
import {
  GROUP_TYPES,
  groupBody,
  type GroupDialogState,
  type GroupOutlineBody,
} from "../outlineGroup";
import type { RoadmapNode } from "../types";
import { ModalFrame } from "./ModalFrame";

type Props = {
  /** Opening state from ``groupDialogState``; read once, on mount. */
  initial: GroupDialogState;
  nodesById: Record<string, RoadmapNode>;
  /** Resolves once the request is settled; throws the server's refusal. */
  onSubmit: (body: GroupOutlineBody) => Promise<void>;
  onClose: () => void;
};

export function GroupSiblingsModal({ initial, nodesById, onSubmit, onClose }: Props) {
  const [state, setState] = useState(initial);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) =>
    setState((s) => {
      const checked = new Set(s.checked);
      if (checked.has(id)) checked.delete(id);
      else checked.add(id);
      return { ...s, checked };
    });

  const onConfirm = async () => {
    const r = groupBody(state);
    if (!r.ok) {
      setError(r.message);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(r.body);
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  };

  return (
    <ModalFrame
      title="Group siblings"
      titleId="group-siblings-title"
      onClose={onClose}
      storageKey="group-siblings"
      minTop={0}
      zIndex={200}
      bodyClassName="modal-body--publish"
      footer={
        <div className="modal-footer-actions">
          <button
            type="button"
            className="publish-modal-btn publish-modal-btn--ghost"
            disabled={submitting}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="publish-modal-btn publish-modal-btn--primary"
            disabled={submitting}
            onClick={() => void onConfirm()}
          >
            {submitting ? "Grouping…" : "Group"}
          </button>
        </div>
      }
    >
      <p className="outline-meta">
        Moves the checked rows, in outline order, under a new parent placed
        where the first of them is (<code>specy-road group-nodes</code>).
      </p>
      <fieldset className="publish-roadmap-label" disabled={submitting}>
        <legend className="publish-roadmap-meta-label">Rows to group</legend>
        {state.siblingIds.map((id) => (
          <label key={id}>
            <input
              type="checkbox"
              checked={state.checked.has(id)}
              onChange={() => toggle(id)}
            />{" "}
            <code>{id}</code> {nodesById[id]?.title ?? ""}
          </label>
        ))}
      </fieldset>
      <label className="publish-roadmap-label">
        New parent id
        <input
          type="text"
          className="publish-roadmap-input"
          value={state.intoNew}
          onChange={(e) => setState((s) => ({ ...s, intoNew: e.target.value }))}
          disabled={submitting}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label className="publish-roadmap-label">
        Title
        <input
          type="text"
          className="publish-roadmap-input"
          value={state.title}
          onChange={(e) => setState((s) => ({ ...s, title: e.target.value }))}
          disabled={submitting}
          autoComplete="off"
          required
        />
      </label>
      <label className="publish-roadmap-label">
        Type
        <select
          className="publish-roadmap-input"
          value={state.type}
          onChange={(e) => setState((s) => ({ ...s, type: e.target.value }))}
          disabled={submitting}
        >
          {GROUP_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={state.rewriteRefs}
          onChange={(e) => setState((s) => ({ ...s, rewriteRefs: e.target.checked }))}
          disabled={submitting}
        />{" "}
        Rewrite id references in prose
      </label>
      {error ? (
        <p className="modal-review-error" role="alert">
          {error}
        </p>
      ) : null}
    </ModalFrame>
  );
}
