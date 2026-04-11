import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type RefObject,
} from "react";
import {
  DndContext,
  PointerSensor,
  closestCorners,
  pointerWithin,
  type CollisionDetection,
  type DragEndEvent,
  useSensor,
  useSensors,
  useDroppable,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { DependencyInheritanceEntry, RoadmapNode } from "../types";
import { moveOutline, patchNode, reorderOutline } from "../api";

/** Prefer pointer-actual droppables (gap / into) over sortable row hitboxes. */
const outlineCollisionDetection: CollisionDetection = (args) => {
  const insidePointer = pointerWithin(args);
  if (insidePointer.length > 0) {
    return insidePointer;
  }
  return closestCorners(args);
};

const TABLE_COLS = 5;

function parentKey(n: RoadmapNode | undefined): string | null {
  const p = n?.parent_id;
  if (p === undefined || p === null || p === "") return null;
  return p;
}

function isDescendant(
  nodesById: Record<string, RoadmapNode>,
  ancestorId: string,
  nid: string,
): boolean {
  let cur: string | null | undefined = nodesById[nid]?.parent_id;
  while (cur) {
    if (cur === ancestorId) return true;
    cur = nodesById[cur]?.parent_id ?? null;
  }
  return false;
}

function cannotReparentUnder(
  aid: string,
  newParentId: string | null,
  nodesById: Record<string, RoadmapNode>,
): boolean {
  if (!newParentId) return false;
  if (newParentId === aid) return true;
  return isDescendant(nodesById, aid, newParentId);
}

function siblingOrderInsertBefore(
  parentId: string | null,
  aid: string,
  oid: string,
  orderedIds: string[],
  nodesById: Record<string, RoadmapNode>,
): string[] | null {
  const full = orderedIds.filter(
    (id) => parentKey(nodesById[id]) === parentId,
  );
  if (!full.includes(aid) || !full.includes(oid)) return null;
  const without = full.filter((id) => id !== aid);
  const insertAt = without.indexOf(oid);
  if (insertAt < 0) return null;
  return [...without.slice(0, insertAt), aid, ...without.slice(insertAt)];
}

/** Place ``aid`` immediately after sibling ``oid`` under the same parent. */
function siblingOrderInsertAfter(
  parentId: string | null,
  aid: string,
  oid: string,
  orderedIds: string[],
  nodesById: Record<string, RoadmapNode>,
): string[] | null {
  const full = orderedIds.filter(
    (id) => parentKey(nodesById[id]) === parentId,
  );
  if (!full.includes(aid) || !full.includes(oid)) return null;
  const without = full.filter((id) => id !== aid);
  const pos = without.indexOf(oid);
  if (pos < 0) return null;
  const insertAt = pos + 1;
  return [...without.slice(0, insertAt), aid, ...without.slice(insertAt)];
}

function devLabel(
  nid: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitEnrichment: Record<string, Record<string, unknown>>,
): string {
  const e = registryByNode?.[nid];
  const owner = e?.owner;
  if (typeof owner === "string" && owner.trim()) return owner.trim();
  const g = gitEnrichment[nid];
  if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
    const author = g.author as string | undefined;
    if (author) return `@${author}`;
  }
  return "—";
}

function IntoDropBadge({ nodeId }: { nodeId: string }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `into:${nodeId}`,
  });
  return (
    <span
      ref={setNodeRef}
      className={isOver ? "into-drop into-drop-active" : "into-drop"}
      title="Drop here to make this row the new parent (last child)"
    >
      ⎘
    </span>
  );
}

function RootDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: "into:__root__" });
  return (
    <th
      ref={setNodeRef}
      colSpan={TABLE_COLS}
      className={isOver ? "into-root into-root-active" : "into-root"}
      title="Drop here to move to top level (append as last root)"
    >
      Top level
    </th>
  );
}

function RowGapBefore({
  targetId,
  onInsertClick,
  depEditActive,
}: {
  targetId: string;
  onInsertClick: (targetId: string) => void;
  depEditActive: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `before:${targetId}`,
  });
  return (
    <tr ref={setNodeRef} className="outline-gap-tr">
      <td
        className={
          isOver ? "outline-gap-cell outline-gap-active" : "outline-gap-cell"
        }
        colSpan={TABLE_COLS}
        title="Drop here to insert before this row (same parent as this row)"
      >
        <button
          type="button"
          className="outline-gap-insert-btn"
          aria-label="Add task above"
          disabled={depEditActive}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onInsertClick(targetId);
          }}
        >
          +
        </button>
      </td>
    </tr>
  );
}

type RowProps = {
  id: string;
  node: RoadmapNode;
  outlineDepth: number;
  selected: boolean;
  meta?: string;
  statusText: string;
  devText: string;
  depCellText: string;
  depEditId: string | null;
  isDepCandidate: boolean;
  titleEditing: boolean;
  titleDraft: string;
  onTitleDraftChange: (v: string) => void;
  onTitleBlur: () => void;
  onTitleKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  titleInputRef: RefObject<HTMLInputElement | null>;
  onBeginTitleEdit: () => void;
  onSelectRow: () => void;
  onOpenModal: () => void;
  /** Task / status / dev clicked while editing deps (passes row id). */
  onDepRowBodyClick: () => void;
  onDepCellClick: () => void;
  onApplyDepEdit: () => void;
  onCancelDepEdit: () => void;
  onClearDepDraft: () => void;
  depDraftEmpty: boolean;
  dragDisabled: boolean;
};

function SortableRow({
  id,
  node,
  outlineDepth,
  selected,
  meta,
  statusText,
  devText,
  depCellText,
  depEditId,
  isDepCandidate,
  titleEditing,
  titleDraft,
  onTitleDraftChange,
  onTitleBlur,
  onTitleKeyDown,
  titleInputRef,
  onBeginTitleEdit,
  onSelectRow,
  onOpenModal,
  onDepRowBodyClick,
  onDepCellClick,
  onApplyDepEdit,
  onCancelDepEdit,
  onClearDepDraft,
  depDraftEmpty,
  dragDisabled,
}: RowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id, disabled: dragDisabled });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.7 : 1,
  };

  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTitleClick = () => {
    if (depEditId) {
      onDepRowBodyClick();
      return;
    }
    if (selected) {
      if (clickTimer.current) {
        clearTimeout(clickTimer.current);
        clickTimer.current = null;
      }
      onBeginTitleEdit();
      return;
    }
    if (clickTimer.current) clearTimeout(clickTimer.current);
    clickTimer.current = setTimeout(() => {
      clickTimer.current = null;
      onSelectRow();
    }, 220);
  };

  const handleDoubleClick = (e: { preventDefault: () => void }) => {
    e.preventDefault();
    if (depEditId) return;
    if (titleEditing) return;
    if (clickTimer.current) {
      clearTimeout(clickTimer.current);
      clickTimer.current = null;
    }
    onOpenModal();
  };

  const handleIdClick = () => {
    if (clickTimer.current) clearTimeout(clickTimer.current);
    clickTimer.current = null;
    onSelectRow();
  };

  const handleStatusDevClick = () => {
    if (depEditId) {
      onDepRowBodyClick();
    } else {
      onSelectRow();
    }
  };

  const rowClass = [
    selected ? "selected" : "",
    depEditId === id ? "dep-edit-row" : "",
    isDepCandidate ? "dep-candidate-row" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const depActive = depEditId === id;

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className={rowClass || undefined}
      {...listeners}
      {...attributes}
    >
      <td className="outline-id" onClick={handleIdClick}>
        <span className="outline-id-text">{node.id}</span>
        <IntoDropBadge nodeId={node.id} />
      </td>
      <td
        className="outline-title"
        onClick={handleTitleClick}
        onDoubleClick={handleDoubleClick}
        style={{ paddingLeft: `${outlineDepth * 12}px` }}
      >
        {titleEditing ? (
          <input
            ref={titleInputRef}
            className="outline-title-input"
            value={titleDraft}
            onChange={(e) => onTitleDraftChange(e.target.value)}
            onBlur={onTitleBlur}
            onKeyDown={onTitleKeyDown}
            onClick={(e) => e.stopPropagation()}
            onPointerDownCapture={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
          />
        ) : (
          <div>{node.title}</div>
        )}
        {meta ? <div className="outline-meta">{meta}</div> : null}
      </td>
      <td className="outline-col-status" onClick={handleStatusDevClick}>
        {statusText}
      </td>
      <td className="outline-col-dev" onClick={handleStatusDevClick}>
        {devText}
      </td>
      <td
        className={
          depActive
            ? "outline-col-dep outline-col-dep-active"
            : "outline-col-dep"
        }
        title="Click to choose which features this item depends on (explicit)"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDepCellClick();
        }}
      >
        <span className="outline-dep-cell-text">{depCellText}</span>
        {depActive ? (
          <div className="dep-edit-floating">
            <button
              type="button"
              className="dep-edit-floating-btn dep-edit-floating-save"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onApplyDepEdit();
              }}
            >
              Save
            </button>
            <button
              type="button"
              className="dep-edit-floating-btn"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onCancelDepEdit();
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="dep-edit-floating-btn"
              disabled={depDraftEmpty}
              title="Remove all prerequisites from the draft"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onClearDepDraft();
              }}
            >
              Clear
            </button>
          </div>
        ) : null}
      </td>
    </tr>
  );
}

type Props = {
  orderedIds: string[];
  nodesById: Record<string, RoadmapNode>;
  rowDepths: number[];
  selectedId: string | null;
  prHints: Record<string, string>;
  gitEnrichment: Record<string, Record<string, unknown>>;
  dependencyInheritance?: Record<string, DependencyInheritanceEntry>;
  registryByNode?: Record<string, Record<string, unknown>>;
  depEditId: string | null;
  depDraftKeys: Set<string>;
  onToggleDepCandidate: (candidateNodeId: string) => void;
  onDepCellActivate: (nodeId: string) => void;
  onApplyDepEdit: () => void;
  onCancelDepEdit: () => void;
  onClearDepDraft: () => void;
  onSelect: (id: string) => void;
  onDoubleClick: (id: string) => void;
  onReordered: () => Promise<void>;
  onGapInsert: (referenceNodeId: string) => void;
};

export function OutlineTable({
  orderedIds,
  nodesById,
  rowDepths,
  selectedId,
  prHints,
  gitEnrichment,
  dependencyInheritance,
  registryByNode,
  depEditId,
  depDraftKeys,
  onToggleDepCandidate,
  onDepCellActivate,
  onApplyDepEdit,
  onCancelDepEdit,
  onClearDepDraft,
  onSelect,
  onDoubleClick,
  onReordered,
  onGapInsert,
}: Props) {
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const keyToId = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of Object.values(nodesById)) {
      if (n?.node_key) m.set(n.node_key, n.id);
    }
    return m;
  }, [nodesById]);

  const metaLine = (nid: string) => {
    const g = gitEnrichment[nid];
    if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
      const assignees = g.assignees as string[] | undefined;
      const author = g.author as string | undefined;
      const bits = [
        author ? `@${author}` : "",
        assignees?.length ? `A: ${assignees.join(", ")}` : "",
      ].filter(Boolean);
      return bits.join(" · ") || (g.hint_line as string) || "";
    }
    if (g?.hint_line) return String(g.hint_line);
    if (prHints[nid]) return prHints[nid].replace(/<br>/g, " · ");
    return "";
  };

  const idForNodeKey = (k: string): string | undefined => {
    const fromMap = keyToId.get(k);
    if (fromMap) return fromMap;
    for (const n of Object.values(nodesById)) {
      if (n?.node_key === k) return n.id;
    }
    return undefined;
  };

  const depCellLabel = (nid: string) => {
    const node = nodesById[nid];
    if (!node) return "—";
    if (depEditId === nid) {
      const parts = [...depDraftKeys]
        .map((k) => idForNodeKey(k))
        .filter(Boolean) as string[];
      return parts.length ? [...new Set(parts)].sort().join(", ") : "—";
    }
    const ex = dependencyInheritance?.[nid]?.explicit ?? [];
    return ex.length ? ex.join(", ") : "—";
  };

  const flushTitleIfDirty = useCallback(async () => {
    if (!editingTitleId) return;
    const n = nodesById[editingTitleId];
    if (!n) {
      setEditingTitleId(null);
      return;
    }
    const t = titleDraft.trim();
    if (t && t !== n.title) {
      try {
        await patchNode(editingTitleId, [{ key: "title", value: t }]);
        await onReordered();
      } catch (e) {
        console.error(e);
      }
    }
    setEditingTitleId(null);
  }, [editingTitleId, titleDraft, nodesById, onReordered]);

  const cancelTitleEdit = useCallback(() => {
    setEditingTitleId(null);
  }, []);

  useEffect(() => {
    if (!editingTitleId) return;
    const el = titleInputRef.current;
    if (el) {
      el.focus();
      el.select();
    }
  }, [editingTitleId]);

  useEffect(() => {
    if (!editingTitleId) return;
    const id = editingTitleId;
    const tid = window.setInterval(() => {
      const n = nodesById[id];
      if (!n) return;
      const trimmed = titleDraft.trim();
      if (trimmed && trimmed !== n.title) {
        void patchNode(id, [{ key: "title", value: trimmed }]).then(() =>
          onReordered(),
        );
      }
    }, 2500);
    return () => window.clearInterval(tid);
  }, [editingTitleId, titleDraft, nodesById, onReordered]);

  const depCellActivate = useCallback(
    (nodeId: string) => {
      if (editingTitleId) {
        void (async () => {
          await flushTitleIfDirty();
          onDepCellActivate(nodeId);
        })();
        return;
      }
      onDepCellActivate(nodeId);
    },
    [editingTitleId, flushTitleIfDirty, onDepCellActivate],
  );

  const onTitleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cancelTitleEdit();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      void flushTitleIfDirty();
    }
  };

  const beginTitleEdit = (nid: string) => {
    if (depEditId) return;
    const n = nodesById[nid];
    if (!n) return;
    setEditingTitleId(nid);
    setTitleDraft(n.title);
  };

  const applyInsertBefore = async (aid: string, oid: string) => {
    if (aid === oid) return;
    const na = nodesById[aid];
    const nb = nodesById[oid];
    if (!na || !nb) return;

    const P = parentKey(nb);
    if (P !== null && cannotReparentUnder(aid, P, nodesById)) return;

    const sibsEx = orderedIds.filter(
      (id) => parentKey(nodesById[id]) === P && id !== aid,
    );
    const newIndex = sibsEx.indexOf(oid);
    if (newIndex < 0) return;

    const pa = parentKey(na);
    if (pa === P) {
      const next = siblingOrderInsertBefore(P, aid, oid, orderedIds, nodesById);
      if (!next?.length) return;
      try {
        await reorderOutline(P, next);
        await onReordered();
      } catch (err) {
        console.error(err);
        await onReordered();
      }
      return;
    }

    try {
      await moveOutline(na.node_key, P, newIndex);
      await onReordered();
    } catch (err) {
      console.error(err);
      await onReordered();
    }
  };

  const applyInsertAfter = async (aid: string, oid: string) => {
    if (aid === oid) return;
    const na = nodesById[aid];
    const nb = nodesById[oid];
    if (!na || !nb) return;

    const P = parentKey(nb);
    if (P !== null && cannotReparentUnder(aid, P, nodesById)) return;

    const sibsEx = orderedIds.filter(
      (id) => parentKey(nodesById[id]) === P && id !== aid,
    );
    const pos = sibsEx.indexOf(oid);
    if (pos < 0) return;
    const newIndex = pos + 1;

    const pa = parentKey(na);
    if (pa === P) {
      const next = siblingOrderInsertAfter(P, aid, oid, orderedIds, nodesById);
      if (!next?.length) return;
      try {
        await reorderOutline(P, next);
        await onReordered();
      } catch (err) {
        console.error(err);
        await onReordered();
      }
      return;
    }

    try {
      await moveOutline(na.node_key, P, newIndex);
      await onReordered();
    } catch (err) {
      console.error(err);
      await onReordered();
    }
  };

  const lastPointerY = useRef(0);
  useEffect(() => {
    const fn = (ev: PointerEvent) => {
      lastPointerY.current = ev.clientY;
    };
    window.addEventListener("pointermove", fn, { passive: true });
    return () => window.removeEventListener("pointermove", fn);
  }, []);

  const onDragEnd = async (e: DragEndEvent) => {
    if (depEditId) return;
    const { active, over } = e;
    if (!over) return;
    const aid = String(active.id);
    const overStr = String(over.id);
    const na = nodesById[aid];
    if (!na) return;

    if (overStr.startsWith("into:")) {
      const raw = overStr.slice("into:".length);
      const parentDisplay = raw === "__root__" ? null : raw;
      if (parentDisplay === aid) return;
      if (parentDisplay && isDescendant(nodesById, aid, parentDisplay)) {
        await onReordered();
        return;
      }
      if (cannotReparentUnder(aid, parentDisplay, nodesById)) return;
      const others = orderedIds.filter(
        (id) => parentKey(nodesById[id]) === parentDisplay && id !== aid,
      );
      const newIndex = others.length;
      try {
        await moveOutline(na.node_key, parentDisplay, newIndex);
        await onReordered();
      } catch (err) {
        console.error(err);
        await onReordered();
      }
      return;
    }

    let oid: string;
    if (overStr.startsWith("before:")) {
      oid = overStr.slice("before:".length);
    } else {
      oid = overStr;
    }

    if (aid === oid) return;
    const nb = nodesById[oid];
    if (!nb) return;

    /** When collision is the sortable row (not `before:` gap), use Y vs row midline: lower half = insert after. */
    let useInsertAfter = false;
    if (!overStr.startsWith("before:") && over?.rect) {
      const r = over.rect as { top: number; height: number };
      const mid = r.top + r.height / 2;
      useInsertAfter = lastPointerY.current > mid;
    }

    if (useInsertAfter) {
      await applyInsertAfter(aid, oid);
    } else {
      await applyInsertBefore(aid, oid);
    }
  };

  const dragDisabled = Boolean(depEditId);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={outlineCollisionDetection}
      onDragEnd={onDragEnd}
    >
      <table
        className={`outline-table${depEditId ? " dep-edit-mode" : ""}`}
      >
        <thead>
          <tr>
            <RootDropZone />
          </tr>
          <tr>
            <th className="outline-id">ID</th>
            <th className="outline-title">Task</th>
            <th className="outline-col-status">Status</th>
            <th className="outline-col-dev">Dev</th>
            <th className="outline-col-dep">Dependency</th>
          </tr>
        </thead>
        <tbody>
          <SortableContext
            items={orderedIds}
            strategy={verticalListSortingStrategy}
          >
            {orderedIds.map((id, i) => {
              const node = nodesById[id];
              const nk = node?.node_key;
              const isCandidate =
                Boolean(depEditId) &&
                Boolean(nk) &&
                depDraftKeys.has(nk) &&
                depEditId !== id;
              return (
                <Fragment key={id}>
                  <RowGapBefore
                    targetId={id}
                    depEditActive={Boolean(depEditId)}
                    onInsertClick={onGapInsert}
                  />
                  <SortableRow
                    id={id}
                    node={node}
                    outlineDepth={rowDepths[i] ?? 0}
                    selected={selectedId === id}
                    meta={metaLine(id)}
                    statusText={(node?.status as string) || "—"}
                    devText={devLabel(id, registryByNode, gitEnrichment)}
                    depCellText={depCellLabel(id)}
                    depEditId={depEditId}
                    isDepCandidate={isCandidate}
                    titleEditing={editingTitleId === id}
                    titleDraft={titleDraft}
                    onTitleDraftChange={setTitleDraft}
                    onTitleBlur={() => void flushTitleIfDirty()}
                    onTitleKeyDown={onTitleKeyDown}
                    titleInputRef={titleInputRef}
                    onBeginTitleEdit={() => beginTitleEdit(id)}
                    dragDisabled={dragDisabled}
                    depDraftEmpty={depDraftKeys.size === 0}
                    onApplyDepEdit={onApplyDepEdit}
                    onCancelDepEdit={onCancelDepEdit}
                    onClearDepDraft={onClearDepDraft}
                    onSelectRow={() => onSelect(id)}
                    onOpenModal={() => onDoubleClick(id)}
                    onDepRowBodyClick={() => {
                      if (!depEditId) return;
                      if (id === depEditId) {
                        onSelect(id);
                        return;
                      }
                      onToggleDepCandidate(id);
                    }}
                    onDepCellClick={() => depCellActivate(id)}
                  />
                </Fragment>
              );
            })}
          </SortableContext>
        </tbody>
      </table>
    </DndContext>
  );
}
