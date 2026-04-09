import { Fragment, useRef, type CSSProperties } from "react";
import {
  DndContext,
  PointerSensor,
  closestCorners,
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
import { moveOutline, reorderOutline } from "../api";

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

/** True if ``newParentId`` is ``aid`` or a descendant of ``aid`` (invalid reparent target). */
function cannotReparentUnder(
  aid: string,
  newParentId: string | null,
  nodesById: Record<string, RoadmapNode>,
): boolean {
  if (!newParentId) return false;
  if (newParentId === aid) return true;
  return isDescendant(nodesById, aid, newParentId);
}

/** Sibling order after moving ``aid`` to sit immediately before ``oid`` under ``parentId``. */
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
      colSpan={2}
      className={isOver ? "into-root into-root-active" : "into-root"}
      title="Drop here to move to top level (append as last root)"
    >
      Top level
    </th>
  );
}

function RowGapBefore({ targetId }: { targetId: string }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `before:${targetId}`,
  });
  return (
    <tr ref={setNodeRef} className="outline-gap-tr">
      <td
        className={isOver ? "outline-gap-cell outline-gap-active" : "outline-gap-cell"}
        colSpan={2}
        title="Drop here to insert before this row (same parent as this row)"
      />
    </tr>
  );
}

type RowProps = {
  id: string;
  node: RoadmapNode;
  outlineDepth: number;
  selected: boolean;
  meta?: string;
  onSelectRow: () => void;
  onOpenModal: () => void;
};

function SortableRow({
  id,
  node,
  outlineDepth,
  selected,
  meta,
  onSelectRow,
  onOpenModal,
}: RowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.7 : 1,
  };

  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleClick = () => {
    if (clickTimer.current) clearTimeout(clickTimer.current);
    clickTimer.current = setTimeout(() => {
      clickTimer.current = null;
      onSelectRow();
    }, 220);
  };

  const handleDoubleClick = (e: { preventDefault: () => void }) => {
    e.preventDefault();
    if (clickTimer.current) {
      clearTimeout(clickTimer.current);
      clickTimer.current = null;
    }
    onOpenModal();
  };

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className={selected ? "selected" : undefined}
      {...attributes}
    >
      <td className="outline-id">
        <span {...listeners} className="outline-drag-handle">
          {node.id}
        </span>
        <IntoDropBadge nodeId={node.id} />
      </td>
      <td
        className="outline-title"
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        style={{ paddingLeft: `${outlineDepth * 12}px` }}
      >
        <div>{node.title}</div>
        {meta ? <div className="outline-meta">{meta}</div> : null}
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
  onSelect: (id: string) => void;
  onDoubleClick: (id: string) => void;
  onReordered: () => Promise<void>;
};

export function OutlineTable({
  orderedIds,
  nodesById,
  rowDepths,
  selectedId,
  prHints,
  gitEnrichment,
  dependencyInheritance,
  onSelect,
  onDoubleClick,
  onReordered,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const metaLine = (nid: string) => {
    const g = gitEnrichment[nid];
    let base = "";
    if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
      const assignees = g.assignees as string[] | undefined;
      const author = g.author as string | undefined;
      const bits = [
        author ? `@${author}` : "",
        assignees?.length ? `A: ${assignees.join(", ")}` : "",
      ].filter(Boolean);
      base = bits.join(" · ") || (g.hint_line as string) || "";
    } else if (g?.hint_line) {
      base = String(g.hint_line);
    } else if (prHints[nid]) {
      base = prHints[nid].replace(/<br>/g, " · ");
    }
    const di = dependencyInheritance?.[nid];
    if (di && (di.explicit.length > 0 || di.inherited.length > 0)) {
      const depBits: string[] = [];
      if (di.explicit.length)
        depBits.push(`deps: ${di.explicit.join(", ")}`);
      if (di.inherited.length)
        depBits.push(`inherited: ${di.inherited.join(", ")}`);
      const depStr = depBits.join(" · ");
      return base ? `${base} · ${depStr}` : depStr;
    }
    return base;
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

  const onDragEnd = async (e: DragEndEvent) => {
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
      if (
        parentDisplay &&
        isDescendant(nodesById, aid, parentDisplay)
      ) {
        await onReordered();
        return;
      }
      if (cannotReparentUnder(aid, parentDisplay, nodesById)) return;
      const others = orderedIds.filter(
        (id) =>
          parentKey(nodesById[id]) === parentDisplay && id !== aid,
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

    await applyInsertBefore(aid, oid);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragEnd={onDragEnd}
    >
      <table className="outline-table">
        <thead>
          <tr>
            <RootDropZone />
          </tr>
          <tr>
            <th className="outline-id">ID</th>
            <th className="outline-title">Task</th>
          </tr>
        </thead>
        <tbody>
          <SortableContext
            items={orderedIds}
            strategy={verticalListSortingStrategy}
          >
            {orderedIds.map((id, i) => (
              <Fragment key={id}>
                <RowGapBefore targetId={id} />
                <SortableRow
                  id={id}
                  node={nodesById[id]}
                  outlineDepth={rowDepths[i] ?? 0}
                  selected={selectedId === id}
                  meta={metaLine(id)}
                  onSelectRow={() => onSelect(id)}
                  onOpenModal={() => onDoubleClick(id)}
                />
              </Fragment>
            ))}
          </SortableContext>
        </tbody>
      </table>
    </DndContext>
  );
}
