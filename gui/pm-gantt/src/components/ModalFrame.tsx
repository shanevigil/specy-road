import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { getDefaultModalRect, type ModalRect } from "../modalRect";
import { isMacLike } from "../os";

const MIN_W = 320;
const MIN_H = 220;

function clampRectToViewport(r: ModalRect): ModalRect {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let { left, top, width, height } = r;
  width = Math.min(Math.max(width, MIN_W), vw);
  height = Math.min(Math.max(height, MIN_H), vh);
  left = Math.min(Math.max(left, 0), Math.max(0, vw - width));
  top = Math.min(Math.max(top, 0), Math.max(0, vh - height));
  return { left, top, width, height };
}

type Props = {
  title: ReactNode;
  titleId?: string;
  onClose: () => void;
  children: ReactNode;
  /** Optional status / secondary actions (e.g. “Saved”, Test LLM). */
  footer?: ReactNode;
  /** Extra class on the scrollable body (e.g. `modal-body--edit`). */
  bodyClassName?: string;
};

export function ModalFrame({
  title,
  titleId,
  onClose,
  children,
  footer,
  bodyClassName,
}: Props) {
  const mac = isMacLike();
  const [rect, setRect] = useState<ModalRect>(() => getDefaultModalRect());
  const rectRef = useRef(rect);
  useEffect(() => {
    rectRef.current = rect;
  }, [rect]);
  const dragRef = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const resizeRef = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);

  useEffect(() => {
    const onWinResize = () => {
      setRect((r) => clampRectToViewport(r));
    };
    window.addEventListener("resize", onWinResize);
    return () => window.removeEventListener("resize", onWinResize);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onTitlePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const r = rectRef.current;
      dragRef.current = {
        x: e.clientX,
        y: e.clientY,
        left: r.left,
        top: r.top,
      };
      const move = (ev: PointerEvent) => {
        if (!dragRef.current) return;
        const d = dragRef.current;
        setRect((prev) =>
          clampRectToViewport({
            ...prev,
            left: d.left + ev.clientX - d.x,
            top: d.top + ev.clientY - d.y,
          }),
        );
      };
      const up = () => {
        dragRef.current = null;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [],
  );

  const onResizePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const r = rectRef.current;
      resizeRef.current = {
        x: e.clientX,
        y: e.clientY,
        width: r.width,
        height: r.height,
      };
      const move = (ev: PointerEvent) => {
        if (!resizeRef.current) return;
        const d = resizeRef.current;
        setRect((prev) =>
          clampRectToViewport({
            ...prev,
            width: Math.max(MIN_W, d.width + ev.clientX - d.x),
            height: Math.max(MIN_H, d.height + ev.clientY - d.y),
          }),
        );
      };
      const up = () => {
        resizeRef.current = null;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [],
  );

  const closeBtn = (
    <button
      type="button"
      className="modal-close"
      aria-label="Close"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      ×
    </button>
  );

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="modal-window"
        style={{
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
        }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header
          className={
            mac ? "modal-titlebar modal-titlebar--mac" : "modal-titlebar"
          }
        >
          {mac ? closeBtn : null}
          <div
            className="modal-titlebar-drag"
            onPointerDown={onTitlePointerDown}
          >
            <span id={titleId} className="modal-title-text">
              {title}
            </span>
          </div>
          {!mac ? closeBtn : null}
        </header>
        <div
          className={
            bodyClassName
              ? `modal-body ${bodyClassName}`
              : "modal-body modal-body--framed"
          }
        >
          {children}
        </div>
        {footer != null ? <div className="modal-footer">{footer}</div> : null}
        <div
          className="modal-resize-handle"
          onPointerDown={onResizePointerDown}
          aria-hidden
          title="Resize"
        />
      </div>
    </div>
  );
}
