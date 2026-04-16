import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCorners,
  pointerWithin,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
  type DraggableAttributes,
  type DraggableSyntheticListeners,
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
import { pmPlanningTitleReadOnlyFromRow } from "../pmDisplayStatus";
import { phaseRollupDerivedComplete } from "../parentStatusRollup";
import {
  devColumnDetailTitle,
  devColumnLabel,
  rowMatchesRegisteredBranch,
} from "../rowMatchesRegisteredBranch";
import { visibleDragSubtreeIds } from "../outlineSubtree";

const TITLE_PLAN_READONLY_HINT =
  "Title and planning are read-only while this task is in active development (in progress, open or merged merge request, or this checkout matches the registered branch).";

/** Prefer pointer-actual droppables (gap / into) over sortable row hitboxes. */
const outlineCollisionDetection: CollisionDetection = (args) => {
  const insidePointer = pointerWithin(args);
  if (insidePointer.length > 0) {
    return insidePointer;
  }
  return closestCorners(args);
};

const TABLE_COLS = 5;

function statusColumnTooltip(
  node: RoadmapNode | undefined,
  persistedNorm: string,
  baseDisp: string,
  outlineDisp: string,
): string | undefined {
  const rollup = phaseRollupDerivedComplete(node, baseDisp);
  const outlineDiffers = outlineDisp !== persistedNorm;
  const rollupOnlyVisualComplete =
    rollup &&
    outlineDisp.trim().toLowerCase() === "complete" &&
    persistedNorm.trim().toLowerCase() !== "complete";

  const parts: string[] = [];
  if (rollup) {
    parts.push(
      "Display: all descendants complete (roadmap status unchanged).",
    );
  }
  if (outlineDiffers && !rollupOnlyVisualComplete) {
    parts.push(
      "PM view reflects active registration or Git remote state; the roadmap file may still list another status until it is updated.",
    );
  }
  return parts.length > 0 ? parts.join("\n\n") : undefined;
}

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
  hidden: gapHidden,
}: {
  targetId: string;
  onInsertClick: (targetId: string) => void;
  depEditActive: boolean;
  /** Hide gap between rows that move together in a subtree drag. */
  hidden?: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `before:${targetId}`,
  });
  const gapStyle: CSSProperties | undefined = gapHidden
    ? { opacity: 0, pointerEvents: "none" }
    : undefined;
  return (
    <tr ref={setNodeRef} className="outline-gap-tr" style={gapStyle}>
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
  statusCellTitle?: string;
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
  dragDisabled: boolean;
  /** Set only for the row whose dependency cell is being edited; anchors the floating toolbar. */
  depCellRef?: RefObject<HTMLTableCellElement | null>;
  /** Registry branch matches current git checkout (named branch). */
  isGitCheckoutRow?: boolean;
  /** Branch / registry details (hover); not shown under title to keep row height aligned with Gantt. */
  devCellTitle?: string;
  /** Inline title edit disabled (same condition as isGitCheckoutRow). */
  titleEditLocked?: boolean;
};

type OutlineRowTrExtra = {
  variant: "interactive" | "dragPreview";
  rowClass: string;
  gitCheckoutTitle?: string;
  trRef?: (el: HTMLTableRowElement | null) => void;
  trStyle?: CSSProperties;
  dndListeners?: DraggableSyntheticListeners;
  dndAttributes?: DraggableAttributes;
  onRowDoubleClick?: (e: MouseEvent<HTMLTableRowElement>) => void;
  onTitleClick?: () => void;
  onTitlePointerDown?: (e: ReactPointerEvent<HTMLTableCellElement>) => void;
  onTitlePointerMove?: (e: ReactPointerEvent<HTMLTableCellElement>) => void;
  onTitlePointerEnd?: () => void;
  onIdClick?: () => void;
  onStatusDevClick?: () => void;
};

function OutlineRowTr(props: RowProps & OutlineRowTrExtra) {
  const {
    variant,
    id,
    node,
    outlineDepth,
    meta,
    statusText,
    statusCellTitle,
    devText,
    depCellText,
    depEditId,
    titleEditing,
    titleDraft,
    onTitleDraftChange,
    onTitleBlur,
    onTitleKeyDown,
    titleInputRef,
    onDepCellClick,
    depCellRef,
    devCellTitle,
    titleEditLocked,
    rowClass,
    gitCheckoutTitle,
    trRef,
    trStyle,
    dndListeners,
    dndAttributes,
    onRowDoubleClick,
    onTitleClick,
    onTitlePointerDown,
    onTitlePointerMove,
    onTitlePointerEnd,
    onIdClick,
    onStatusDevClick,
  } = props;

  const depActive = depEditId === id;
  const isPreview = variant === "dragPreview";

  return (
    <tr
      ref={trRef}
      style={trStyle}
      className={rowClass || undefined}
      title={gitCheckoutTitle}
      {...(isPreview ? {} : (dndListeners ?? {}))}
      {...(isPreview ? {} : (dndAttributes ?? {}))}
      onDoubleClick={onRowDoubleClick}
    >
      <td className="outline-id" onClick={isPreview ? undefined : onIdClick}>
        <span className="outline-id-text">{node.id}</span>
        {isPreview ? null : <IntoDropBadge nodeId={node.id} />}
      </td>
      <td
        className="outline-title"
        title={titleEditLocked ? TITLE_PLAN_READONLY_HINT : undefined}
        onClick={isPreview ? undefined : onTitleClick}
        onPointerDown={isPreview ? undefined : onTitlePointerDown}
        onPointerMove={isPreview ? undefined : onTitlePointerMove}
        onPointerUp={isPreview ? undefined : onTitlePointerEnd}
        onPointerCancel={isPreview ? undefined : onTitlePointerEnd}
        onPointerLeave={isPreview ? undefined : onTitlePointerEnd}
        style={{ paddingLeft: `${outlineDepth * 12}px` }}
      >
        {!isPreview && titleEditing ? (
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
          <div className="outline-title-row">
            <div className="outline-title-text-wrap">
              <div>{node.title}</div>
            </div>
            {titleEditLocked ? (
              <span
                className="outline-pm-lock"
                title={TITLE_PLAN_READONLY_HINT}
                aria-label="Read-only"
              >
                <svg
                  className="outline-pm-lock-icon"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                  focusable="false"
                >
                  <rect
                    x="3"
                    y="11"
                    width="18"
                    height="11"
                    rx="2"
                    stroke="currentColor"
                    strokeWidth="2"
                  />
                  <path
                    d="M7 11V7a5 5 0 0 1 10 0v4"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
            ) : null}
          </div>
        )}
        {meta ? <div className="outline-meta">{meta}</div> : null}
      </td>
      <td
        className="outline-col-status"
        title={statusCellTitle}
        onClick={isPreview ? undefined : onStatusDevClick}
      >
        {statusText}
      </td>
      <td
        className="outline-col-dev"
        title={devCellTitle}
        onClick={isPreview ? undefined : onStatusDevClick}
      >
        {devText}
      </td>
      <td
        ref={depCellRef}
        className={
          depActive
            ? "outline-col-dep outline-col-dep-active"
            : "outline-col-dep"
        }
        title="Click to choose which features this item depends on (explicit)"
        onClick={
          isPreview
            ? undefined
            : (e) => {
                e.preventDefault();
                e.stopPropagation();
                onDepCellClick();
              }
        }
      >
        <span className="outline-dep-cell-text">{depCellText}</span>
      </td>
    </tr>
  );
}

function SortableRow({
  id,
  node,
  outlineDepth,
  selected,
  meta,
  statusText,
  statusCellTitle,
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
  dragDisabled,
  depCellRef,
  isGitCheckoutRow,
  devCellTitle,
  titleEditLocked,
  rowSourceHidden,
}: RowProps & { rowSourceHidden: boolean }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id, disabled: dragDisabled });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: rowSourceHidden ? 0 : 1,
    pointerEvents: rowSourceHidden ? "none" : undefined,
  };

  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressOrigin = useRef<{ x: number; y: number } | null>(null);
  const skipNextTitleClick = useRef(false);

  const TITLE_LONG_PRESS_MS = 500;
  const LONG_PRESS_MOVE_PX = 10;

  const clearLongPressTimer = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    longPressOrigin.current = null;
  };

  const handleTitlePointerDown = (e: ReactPointerEvent<HTMLTableCellElement>) => {
    if (depEditId || titleEditing || titleEditLocked) return;
    if (e.button !== 0) return;
    clearLongPressTimer();
    longPressOrigin.current = { x: e.clientX, y: e.clientY };
    longPressTimer.current = setTimeout(() => {
      longPressTimer.current = null;
      longPressOrigin.current = null;
      skipNextTitleClick.current = true;
      if (clickTimer.current) {
        clearTimeout(clickTimer.current);
        clickTimer.current = null;
      }
      if (!selected) onSelectRow();
      onBeginTitleEdit();
    }, TITLE_LONG_PRESS_MS);
  };

  const handleTitlePointerMove = (e: ReactPointerEvent<HTMLTableCellElement>) => {
    if (!longPressTimer.current || !longPressOrigin.current) return;
    const dx = e.clientX - longPressOrigin.current.x;
    const dy = e.clientY - longPressOrigin.current.y;
    if (dx * dx + dy * dy > LONG_PRESS_MOVE_PX * LONG_PRESS_MOVE_PX) {
      clearLongPressTimer();
    }
  };

  const handleTitlePointerEnd = () => {
    clearLongPressTimer();
  };

  const handleTitleClick = () => {
    if (skipNextTitleClick.current) {
      skipNextTitleClick.current = false;
      return;
    }
    if (depEditId) {
      onDepRowBodyClick();
      return;
    }
    if (clickTimer.current) clearTimeout(clickTimer.current);
    clickTimer.current = setTimeout(() => {
      clickTimer.current = null;
      onSelectRow();
    }, 220);
  };

  const handleRowDoubleClick = (e: MouseEvent<HTMLTableRowElement>) => {
    e.preventDefault();
    if (depEditId) return;
    if (titleEditing) return;
    clearLongPressTimer();
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
    isGitCheckoutRow ? "outline-row-git-current" : "",
    node.type === "gate" ? "outline-row-gate" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const gitCheckoutTitle = isGitCheckoutRow
    ? "Named branch matches the branch field in roadmap/registry.yaml for this row in this checkout."
    : undefined;

  return (
    <OutlineRowTr
      id={id}
      node={node}
      outlineDepth={outlineDepth}
      selected={selected}
      meta={meta}
      statusText={statusText}
      statusCellTitle={statusCellTitle}
      devText={devText}
      depCellText={depCellText}
      depEditId={depEditId}
      isDepCandidate={isDepCandidate}
      titleEditing={titleEditing}
      titleDraft={titleDraft}
      onTitleDraftChange={onTitleDraftChange}
      onTitleBlur={onTitleBlur}
      onTitleKeyDown={onTitleKeyDown}
      titleInputRef={titleInputRef}
      onBeginTitleEdit={onBeginTitleEdit}
      onSelectRow={onSelectRow}
      onOpenModal={onOpenModal}
      onDepRowBodyClick={onDepRowBodyClick}
      onDepCellClick={onDepCellClick}
      dragDisabled={dragDisabled}
      depCellRef={depCellRef}
      isGitCheckoutRow={isGitCheckoutRow}
      devCellTitle={devCellTitle}
      titleEditLocked={titleEditLocked}
      variant="interactive"
      rowClass={rowClass}
      gitCheckoutTitle={gitCheckoutTitle}
      trRef={setNodeRef}
      trStyle={style}
      dndListeners={listeners}
      dndAttributes={attributes}
      onRowDoubleClick={handleRowDoubleClick}
      onTitleClick={handleTitleClick}
      onTitlePointerDown={handleTitlePointerDown}
      onTitlePointerMove={handleTitlePointerMove}
      onTitlePointerEnd={handleTitlePointerEnd}
      onIdClick={handleIdClick}
      onStatusDevClick={handleStatusDevClick}
    />
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
  /** Current named git branch (for row highlight vs registry branch). */
  gitBranchCurrent?: string | null;
  /** Local ``git config user.name`` when Dev column matches checkout (developer convenience). */
  gitUserName?: string | null;
  depEditId: string | null;
  depDraftKeys: Set<string>;
  onToggleDepCandidate: (candidateNodeId: string) => void;
  onDepCellActivate: (nodeId: string) => void;
  onApplyDepEdit: () => void;
  onCancelDepEdit: () => void;
  onClearDepDraft: () => void;
  onSelect: (id: string) => void;
  onDoubleClick: (id: string) => void;
  /** Serial mutation + roadmap refresh (see App performRoadmapMutation). */
  performRoadmapMutation: (
    label: string,
    mutation: () => Promise<void>,
  ) => Promise<void>;
  onMutationError: (message: string) => void;
  onGapInsert: (referenceNodeId: string) => void;
  displayStatusById?: Record<string, string>;
  /** Status column: MR lifecycle labels on top of {@link displayStatusById}. */
  outlineStatusById?: Record<string, string>;
  /** When true, row drag-and-drop reorder is disabled (e.g. outline filtered). */
  reorderLocked?: boolean;
  /** When true, outline is non-interactive while the app saves/refreshes the roadmap. */
  interactionLocked?: boolean;
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
  gitBranchCurrent,
  gitUserName,
  depEditId,
  depDraftKeys,
  onToggleDepCandidate,
  onDepCellActivate,
  onApplyDepEdit,
  onCancelDepEdit,
  onClearDepDraft,
  onSelect,
  onDoubleClick,
  performRoadmapMutation,
  onMutationError,
  onGapInsert,
  displayStatusById,
  outlineStatusById,
  reorderLocked = false,
  interactionLocked = false,
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
    if (g?.kind === "registry" || g?.kind === "remote_tip") {
      return "";
    }
    if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
      const assignees = g.assignees as string[] | undefined;
      // PR/MR author is omitted; Dev column shows the same via devColumnLabel().
      const bits = [
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
    if (
      rowMatchesRegisteredBranch(
        editingTitleId,
        registryByNode,
        gitBranchCurrent,
      )
    ) {
      setEditingTitleId(null);
      return;
    }
    const n = nodesById[editingTitleId];
    if (!n) {
      setEditingTitleId(null);
      return;
    }
    const t = titleDraft.trim();
    if (t && t !== n.title) {
      try {
        await performRoadmapMutation("Saving title…", () =>
          patchNode(editingTitleId, [{ key: "title", value: t }]),
        );
      } catch (e: unknown) {
        console.error(e);
        onMutationError(String(e));
      }
    }
    setEditingTitleId(null);
  }, [
    editingTitleId,
    titleDraft,
    nodesById,
    performRoadmapMutation,
    onMutationError,
    registryByNode,
    gitBranchCurrent,
  ]);

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
      if (rowMatchesRegisteredBranch(id, registryByNode, gitBranchCurrent)) {
        setEditingTitleId(null);
        return;
      }
      const n = nodesById[id];
      if (!n) return;
      const trimmed = titleDraft.trim();
      if (trimmed && trimmed !== n.title) {
        void performRoadmapMutation("Saving title…", () =>
          patchNode(id, [{ key: "title", value: trimmed }]),
        ).catch((e: unknown) => onMutationError(String(e)));
      }
    }, 2500);
    return () => window.clearInterval(tid);
  }, [
    editingTitleId,
    titleDraft,
    nodesById,
    performRoadmapMutation,
    onMutationError,
    registryByNode,
    gitBranchCurrent,
  ]);

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
    if (interactionLocked) return;
    if (rowMatchesRegisteredBranch(nid, registryByNode, gitBranchCurrent)) {
      return;
    }
    const n = nodesById[nid];
    if (!n) return;
    setEditingTitleId(nid);
    setTitleDraft(n.title);
  };

  const refreshRoadmapOnly = useCallback(
    () => performRoadmapMutation("Refreshing roadmap…", async () => {}),
    [performRoadmapMutation],
  );

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
        await performRoadmapMutation("Updating outline…", () =>
          reorderOutline(P, next),
        );
      } catch (err: unknown) {
        console.error(err);
        onMutationError(String(err));
        await refreshRoadmapOnly();
      }
      return;
    }

    try {
      await performRoadmapMutation("Updating outline…", () =>
        moveOutline(na.node_key, P, newIndex),
      );
    } catch (err: unknown) {
      console.error(err);
      onMutationError(String(err));
      await refreshRoadmapOnly();
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
        await performRoadmapMutation("Updating outline…", () =>
          reorderOutline(P, next),
        );
      } catch (err: unknown) {
        console.error(err);
        onMutationError(String(err));
        await refreshRoadmapOnly();
      }
      return;
    }

    try {
      await performRoadmapMutation("Updating outline…", () =>
        moveOutline(na.node_key, P, newIndex),
      );
    } catch (err: unknown) {
      console.error(err);
      onMutationError(String(err));
      await refreshRoadmapOnly();
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
    setActiveDragId(null);
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
        await refreshRoadmapOnly();
        return;
      }
      if (cannotReparentUnder(aid, parentDisplay, nodesById)) return;
      const others = orderedIds.filter(
        (id) => parentKey(nodesById[id]) === parentDisplay && id !== aid,
      );
      const newIndex = others.length;
      try {
        await performRoadmapMutation("Updating outline…", () =>
          moveOutline(na.node_key, parentDisplay, newIndex),
        );
      } catch (err: unknown) {
        console.error(err);
        onMutationError(String(err));
        await refreshRoadmapOnly();
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

  const dragDisabled =
    Boolean(depEditId) || reorderLocked || interactionLocked;

  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const activeSubtreeIds = useMemo(
    () =>
      activeDragId
        ? visibleDragSubtreeIds(orderedIds, nodesById, activeDragId)
        : [],
    [activeDragId, orderedIds, nodesById],
  );

  const subtreeFirstId = activeSubtreeIds[0] ?? null;

  const activeSubtreeSet = useMemo(
    () => new Set(activeSubtreeIds),
    [activeSubtreeIds],
  );

  const onDragStart = (e: DragStartEvent) => {
    setActiveDragId(String(e.active.id));
  };

  const onDragCancel = () => {
    setActiveDragId(null);
  };

  const depCellAnchorRef = useRef<HTMLTableCellElement | null>(null);
  const depToolbarRef = useRef<HTMLDivElement | null>(null);
  const [depToolbarStyle, setDepToolbarStyle] = useState<CSSProperties | null>(
    null,
  );

  /* Floating toolbar position must update in a layout effect (same frame as dep edit). */
  /* eslint-disable react-hooks/set-state-in-effect */
  useLayoutEffect(() => {
    if (!depEditId) {
      setDepToolbarStyle(null);
      return;
    }
    const cell = depCellAnchorRef.current;
    if (!cell) {
      setDepToolbarStyle(null);
      return;
    }

    const update = () => {
      const r = cell.getBoundingClientRect();
      const tw = depToolbarRef.current?.offsetWidth ?? 0;
      const gap = 8;
      const margin = 8;
      let left = r.right + gap;
      if (tw > 0 && left + tw > window.innerWidth - margin) {
        left = r.left - gap - tw;
      }
      if (left < margin) left = margin;
      if (tw > 0 && left + tw > window.innerWidth - margin) {
        left = Math.max(margin, window.innerWidth - margin - tw);
      }
      setDepToolbarStyle({
        position: "fixed",
        top: r.top + r.height / 2,
        left,
        transform: "translateY(-50%)",
        zIndex: 42,
        visibility: "visible",
        pointerEvents: "auto",
      });
    };

    update();
    const raf = requestAnimationFrame(() => update());

    const wrap = cell.closest(".outline-wrap");
    window.addEventListener("resize", update);
    wrap?.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(cell);
    if (wrap) ro.observe(wrap);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", update);
      wrap?.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, [depEditId, orderedIds, depDraftKeys]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const makeRowProps = (rowId: string, i: number): RowProps | null => {
    const node = nodesById[rowId];
    if (!node) return null;
    const nk = node?.node_key;
    const isCandidate =
      Boolean(depEditId) &&
      Boolean(nk) &&
      depDraftKeys.has(nk) &&
      depEditId !== rowId;
    const isGitCheckoutRow = rowMatchesRegisteredBranch(
      rowId,
      registryByNode,
      gitBranchCurrent,
    );
    const persistedNorm =
      (node?.status as string)?.trim() || "Not Started";
    const baseDisp =
      displayStatusById != null
        ? displayStatusById[rowId] ?? persistedNorm
        : persistedNorm;
    const outlineDisp =
      outlineStatusById != null
        ? outlineStatusById[rowId] ?? baseDisp
        : baseDisp;
    const statusText =
      outlineStatusById != null
        ? outlineDisp
        : displayStatusById != null
          ? baseDisp
          : (node?.status as string) || "—";
    const statusCellTitle = statusColumnTooltip(
      node,
      persistedNorm,
      baseDisp,
      outlineDisp,
    );
    const titlePlanLocked = pmPlanningTitleReadOnlyFromRow(
      isGitCheckoutRow,
      baseDisp,
      outlineDisp,
    );
    return {
      id: rowId,
      node,
      outlineDepth: rowDepths[i] ?? 0,
      selected: selectedId === rowId,
      meta: metaLine(rowId),
      statusText,
      statusCellTitle,
      devText: devColumnLabel(
        rowId,
        registryByNode,
        gitEnrichment,
        gitBranchCurrent,
        gitUserName,
      ),
      depCellText: depCellLabel(rowId),
      depEditId,
      isGitCheckoutRow,
      devCellTitle: devColumnDetailTitle(
        rowId,
        registryByNode,
        gitEnrichment,
        prHints,
      ),
      titleEditLocked: titlePlanLocked,
      isDepCandidate: isCandidate,
      titleEditing: editingTitleId === rowId,
      titleDraft,
      onTitleDraftChange: setTitleDraft,
      onTitleBlur: () => void flushTitleIfDirty(),
      onTitleKeyDown,
      titleInputRef,
      onBeginTitleEdit: () => beginTitleEdit(rowId),
      dragDisabled,
      onSelectRow: () => onSelect(rowId),
      onOpenModal: () => onDoubleClick(rowId),
      onDepRowBodyClick: () => {
        if (!depEditId) return;
        if (rowId === depEditId) {
          onSelect(rowId);
          return;
        }
        onToggleDepCandidate(rowId);
      },
      onDepCellClick: () => depCellActivate(rowId),
      depCellRef: depEditId === rowId ? depCellAnchorRef : undefined,
    };
  };

  const depToolbarFallbackStyle: CSSProperties = {
    position: "fixed",
    left: -9999,
    top: 0,
    visibility: "hidden",
    pointerEvents: "none",
    zIndex: 42,
  };

  const depEditToolbar =
    depEditId != null
      ? createPortal(
          <div
            ref={depToolbarRef}
            className="dep-edit-toolbar-portal"
            role="toolbar"
            aria-label="Dependency edit actions"
            style={depToolbarStyle ?? depToolbarFallbackStyle}
          >
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
              disabled={depDraftKeys.size === 0}
              title="Remove all prerequisites from the draft"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onClearDepDraft();
              }}
            >
              Clear
            </button>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      {depEditToolbar}
    <DndContext
      sensors={sensors}
      collisionDetection={outlineCollisionDetection}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
    >
      <>
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
              const rp = makeRowProps(id, i);
              if (!rp) return null;
              return (
                <Fragment key={id}>
                  <RowGapBefore
                    targetId={id}
                    depEditActive={Boolean(depEditId)}
                    onInsertClick={onGapInsert}
                    hidden={Boolean(
                      activeDragId &&
                        subtreeFirstId &&
                        activeSubtreeSet.has(id) &&
                        id !== subtreeFirstId,
                    )}
                  />
                  <SortableRow
                    {...rp}
                    rowSourceHidden={Boolean(
                      activeDragId && activeSubtreeSet.has(id),
                    )}
                  />
                </Fragment>
              );
            })}
          </SortableContext>
        </tbody>
      </table>
      <DragOverlay dropAnimation={null}>
        {activeDragId && activeSubtreeIds.length > 0 ? (
          <table className="outline-table outline-drag-overlay-table">
            <tbody>
              {activeSubtreeIds.map((did) => {
                const idx = orderedIds.indexOf(did);
                if (idx < 0) return null;
                const rp = makeRowProps(did, idx);
                if (!rp) return null;
                const rowClass = [
                  rp.selected ? "selected" : "",
                  rp.depEditId === did ? "dep-edit-row" : "",
                  rp.isDepCandidate ? "dep-candidate-row" : "",
                  rp.isGitCheckoutRow ? "outline-row-git-current" : "",
                  rp.node.type === "gate" ? "outline-row-gate" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <OutlineRowTr
                    key={did}
                    {...rp}
                    variant="dragPreview"
                    rowClass={rowClass}
                    gitCheckoutTitle={
                      rp.isGitCheckoutRow
                        ? "Named branch matches the branch field in roadmap/registry.yaml for this row in this checkout."
                        : undefined
                    }
                    trStyle={{ cursor: "grabbing" }}
                  />
                );
              })}
            </tbody>
          </table>
        ) : null}
      </DragOverlay>
      </>
    </DndContext>
    </>
  );
}
