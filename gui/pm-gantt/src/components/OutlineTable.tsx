import { useRef, type CSSProperties } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { RoadmapNode } from "../types";
import { reorderOutline } from "../api";

function parentKey(n: RoadmapNode | undefined): string | null {
  const p = n?.parent_id;
  if (p === undefined || p === null || p === "") return null;
  return p;
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
      <td className="outline-id" {...listeners}>
        {node.id}
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
  onSelect,
  onDoubleClick,
  onReordered,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

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

  const onDragEnd = async (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const aid = String(active.id);
    const oid = String(over.id);
    const na = nodesById[aid];
    const nb = nodesById[oid];
    if (!na || !nb) return;
    const pa = parentKey(na);
    const pb = parentKey(nb);
    if (pa !== pb) {
      await onReordered();
      return;
    }
    const siblings = orderedIds.filter((id) => parentKey(nodesById[id]) === pa);
    const oldIndex = siblings.indexOf(aid);
    const newIndex = siblings.indexOf(oid);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(siblings, oldIndex, newIndex);
    try {
      await reorderOutline(pa, next);
      await onReordered();
    } catch (err) {
      console.error(err);
      await onReordered();
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
    >
      <table className="outline-table">
        <thead>
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
              <SortableRow
                key={id}
                id={id}
                node={nodesById[id]}
                outlineDepth={rowDepths[i] ?? 0}
                selected={selectedId === id}
                meta={metaLine(id)}
                onSelectRow={() => onSelect(id)}
                onOpenModal={() => onDoubleClick(id)}
              />
            ))}
          </SortableContext>
        </tbody>
      </table>
    </DndContext>
  );
}
