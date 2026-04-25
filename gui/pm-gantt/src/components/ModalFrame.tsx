import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import {
  clampRectToViewport,
  getDefaultModalRect,
  getTaskMaximizedRect,
  loadStoredModalRect,
  saveStoredModalRect,
  type ClampRectOpts,
  type ModalRect,
} from "../modalRect";
import { isMacLike } from "../os";

/** Matches `modalRect` clamp minima for width/height. */
const RESIZE_MIN_W = 320;
const RESIZE_MIN_H = 220;

type ResizeHandle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

function applyModalResize(
  kind: ResizeHandle,
  r: ModalRect,
  dx: number,
  dy: number,
): ModalRect {
  const minW = RESIZE_MIN_W;
  const minH = RESIZE_MIN_H;
  let { left, top, width, height } = r;
  switch (kind) {
    case "e":
      width = Math.max(minW, width + dx);
      break;
    case "s":
      height = Math.max(minH, height + dy);
      break;
    case "w": {
      const newW = Math.max(minW, width - dx);
      left += width - newW;
      width = newW;
      break;
    }
    case "n": {
      const newH = Math.max(minH, height - dy);
      top += height - newH;
      height = newH;
      break;
    }
    case "se":
      width = Math.max(minW, width + dx);
      height = Math.max(minH, height + dy);
      break;
    case "ne": {
      width = Math.max(minW, width + dx);
      const newH = Math.max(minH, height - dy);
      top += height - newH;
      height = newH;
      break;
    }
    case "sw": {
      const newW = Math.max(minW, width - dx);
      left += width - newW;
      width = newW;
      height = Math.max(minH, height + dy);
      break;
    }
    case "nw": {
      const newW = Math.max(minW, width - dx);
      left += width - newW;
      width = newW;
      const newH = Math.max(minH, height - dy);
      top += height - newH;
      height = newH;
      break;
    }
  }
  return { left, top, width, height };
}

type Props = {
  title: ReactNode;
  /** Native tooltip on the title (e.g. full text when the bar is ellipsized). */
  titleTooltip?: string;
  titleId?: string;
  onClose: () => void;
  children: ReactNode;
  /** Optional status / secondary actions (e.g. “Saved”, Test LLM). */
  footer?: ReactNode;
  /** Extra class on the scrollable body (e.g. `modal-body--edit`). */
  bodyClassName?: string;
  /** Persist size/position in localStorage under this key. */
  storageKey?: string;
  /** Initial rect when nothing is stored (default: full-viewport margin preset). */
  getDefaultRect?: () => ModalRect;
  /** One-time first-open position (e.g. stacked offset from another dialog). */
  initialRectOverride?: ModalRect;
  /** Keep window below this viewport Y (e.g. app header bottom). */
  minTop?: number;
  /** Parent-controlled rect (tile layout); disables drag/resize persist while set. */
  forcedRect?: ModalRect | null;
  /** When ``forcedRect`` clears, restore this free-layout rect (e.g. after untile). */
  resumeFreeRect?: ModalRect | null;
  /** Do not write size/position to localStorage (tile mode). */
  suppressPositionPersist?: boolean;
  /** Highlight title bar (e.g. focused task dialog). */
  titleBarActive?: boolean;
  /** After drag/resize (and initial layout). */
  onRectCommit?: (r: ModalRect) => void;
  /** User brought this dialog forward (title bar or window). */
  onActivate?: () => void;
  /** Show edge and corner resize handles (default true). */
  resizable?: boolean;
  /** On window resize, replace rect with ``getDefaultRect()`` (e.g. right-docked panel). */
  reanchorOnResize?: boolean;
  /**
   * Extra control in the title bar: after the drag handle on Mac (where close is on the
   * left), before the drag handle on other platforms (where close is on the right).
   */
  titleBarAction?: ReactNode;
  /** Stacking order when multiple modals are open (e.g. 50, 51, …). */
  zIndex?: number;
  /** Transparent backdrop that does not dim or block the rest of the UI. */
  backdropPassThrough?: boolean;
  /** When false, Escape does not close (only topmost modal should use true in a stack). */
  closeOnEscape?: boolean;
  /** macOS / Windows–style min / max / close (task modals). */
  taskWindowChrome?: boolean;
  /** Hide the window (state alive; e.g. minimized to the task strip). */
  minimized?: boolean;
  onMinimize?: () => void;
  /** When true, maximize is disabled (e.g. tiled layout). */
  maximizeConstrained?: boolean;
};

function resolveInitialRect(
  storageKey: string | undefined,
  getDefaultRect: (() => ModalRect) | undefined,
  initialOverride: ModalRect | undefined,
  clampOpts: ClampRectOpts,
): ModalRect {
  if (initialOverride) {
    return clampRectToViewport(initialOverride, clampOpts);
  }
  if (storageKey) {
    const stored = loadStoredModalRect(storageKey);
    if (stored) {
      return clampRectToViewport(stored, clampOpts);
    }
  }
  const base = getDefaultRect ? getDefaultRect() : getDefaultModalRect();
  return clampRectToViewport(base, clampOpts);
}

export function ModalFrame({
  title,
  titleTooltip,
  titleId,
  onClose,
  children,
  footer,
  bodyClassName,
  storageKey,
  getDefaultRect,
  initialRectOverride,
  minTop = 0,
  forcedRect,
  resumeFreeRect,
  suppressPositionPersist = false,
  titleBarActive = false,
  onRectCommit,
  onActivate,
  resizable = true,
  reanchorOnResize = false,
  titleBarAction,
  zIndex = 50,
  backdropPassThrough = false,
  closeOnEscape = true,
  taskWindowChrome = false,
  minimized = false,
  onMinimize,
  maximizeConstrained = false,
}: Props) {
  const mac = isMacLike();
  const clampOpts: ClampRectOpts = useMemo(() => ({ minTop }), [minTop]);
  const [isMaximized, setIsMaximized] = useState(false);
  const preMaxRectRef = useRef<ModalRect | null>(null);

  const [rect, setRect] = useState<ModalRect>(() =>
    resolveInitialRect(
      storageKey,
      getDefaultRect,
      initialRectOverride,
      clampOpts,
    ),
  );
  const rectRef = useRef(rect);
  useEffect(() => {
    rectRef.current = rect;
  }, [rect]);

  const persistRect = useCallback(() => {
    if (!storageKey || suppressPositionPersist) return;
    saveStoredModalRect(storageKey, rectRef.current);
  }, [storageKey, suppressPositionPersist]);

  const emitCommit = useCallback(() => {
    onRectCommit?.(rectRef.current);
  }, [onRectCommit]);

  useEffect(() => {
    if (forcedRect != null) {
      setIsMaximized(false);
      preMaxRectRef.current = null;
    }
  }, [forcedRect]);

  const toggleMaximize = useCallback(() => {
    if (maximizeConstrained || forcedRect != null) return;
    if (isMaximized) {
      const pre = preMaxRectRef.current;
      if (pre) {
        const next = clampRectToViewport(pre, clampOpts);
        setRect(next);
        rectRef.current = next;
      }
      setIsMaximized(false);
      preMaxRectRef.current = null;
    } else {
      preMaxRectRef.current = { ...rectRef.current };
      const next = getTaskMaximizedRect(clampOpts);
      setRect(next);
      rectRef.current = next;
      setIsMaximized(true);
    }
    requestAnimationFrame(() => {
      persistRect();
      emitCommit();
    });
  }, [
    isMaximized,
    maximizeConstrained,
    forcedRect,
    clampOpts,
    persistRect,
    emitCommit,
  ]);

  useEffect(() => {
    onRectCommit?.(rectRef.current);
    // eslint-disable-next-line @eslint-react/exhaustive-deps -- report initial rect once
  }, []);

  const dragRef = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const resizeSessionRef = useRef<{
    kind: ResizeHandle;
    x: number;
    y: number;
    rect: ModalRect;
  } | null>(null);

  const tileWasActive = useRef(false);

  useEffect(() => {
    if (forcedRect != null) {
      tileWasActive.current = true;
      const next = clampRectToViewport(forcedRect, clampOpts);
      setRect(next);
      rectRef.current = next;
      requestAnimationFrame(emitCommit);
      return;
    }
    if (tileWasActive.current) {
      if (resumeFreeRect != null) {
        const next = clampRectToViewport(resumeFreeRect, clampOpts);
        setRect(next);
        rectRef.current = next;
        if (!suppressPositionPersist) persistRect();
        requestAnimationFrame(emitCommit);
      }
      tileWasActive.current = false;
    }
  }, [
    forcedRect,
    resumeFreeRect,
    clampOpts,
    emitCommit,
    persistRect,
    suppressPositionPersist,
  ]);

  useEffect(() => {
    const onWinResize = () => {
      if (reanchorOnResize && getDefaultRect) {
        setRect(clampRectToViewport(getDefaultRect(), clampOpts));
        return;
      }
      if (isMaximized && !forcedRect) {
        const next = getTaskMaximizedRect(clampOpts);
        setRect(next);
        rectRef.current = next;
        requestAnimationFrame(emitCommit);
        return;
      }
      setRect((r) => clampRectToViewport(r, clampOpts));
    };
    window.addEventListener("resize", onWinResize);
    return () => window.removeEventListener("resize", onWinResize);
  }, [reanchorOnResize, getDefaultRect, clampOpts, isMaximized, forcedRect, emitCommit]);

  useEffect(() => {
    if (!closeOnEscape || minimized) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, closeOnEscape, minimized]);

  const onTitlePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (forcedRect != null) return;
      if (e.button !== 0) return;
      e.preventDefault();
      onActivate?.();
      if (isMaximized) {
        const pre = preMaxRectRef.current;
        if (pre) {
          const next = clampRectToViewport(pre, clampOpts);
          setRect(next);
          rectRef.current = next;
        }
        setIsMaximized(false);
        preMaxRectRef.current = null;
        requestAnimationFrame(() => {
          persistRect();
          emitCommit();
        });
        return;
      }
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
          clampRectToViewport(
            {
              ...prev,
              left: d.left + ev.clientX - d.x,
              top: d.top + ev.clientY - d.y,
            },
            clampOpts,
          ),
        );
      };
      const up = () => {
        dragRef.current = null;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        requestAnimationFrame(() => {
          persistRect();
          emitCommit();
        });
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [forcedRect, isMaximized, persistRect, emitCommit, onActivate, clampOpts],
  );

  const onResizeStart = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>, kind: ResizeHandle) => {
      if (forcedRect != null) return;
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      onActivate?.();
      const r = rectRef.current;
      resizeSessionRef.current = {
        kind,
        x: e.clientX,
        y: e.clientY,
        rect: { ...r },
      };
      const move = (ev: PointerEvent) => {
        if (!resizeSessionRef.current) return;
        const s = resizeSessionRef.current;
        const dx = ev.clientX - s.x;
        const dy = ev.clientY - s.y;
        setRect(
          clampRectToViewport(
            applyModalResize(s.kind, s.rect, dx, dy),
            clampOpts,
          ),
        );
      };
      const up = () => {
        resizeSessionRef.current = null;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        requestAnimationFrame(() => {
          persistRect();
          emitCommit();
        });
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [forcedRect, persistRect, emitCommit, onActivate, clampOpts],
  );

  const onWindowPointerDown = useCallback(() => {
    onActivate?.();
  }, [onActivate]);

  const maxDisabled = maximizeConstrained || forcedRect != null;

  const defaultCloseBtn = (
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

  const macTld =
    taskWindowChrome && mac ? (
      <div className="modal-tld" role="group" aria-label="Window">
        <button
          type="button"
          className="modal-tld-btn modal-tld-btn--close"
          aria-label="Close"
          title="Close"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        />
        <button
          type="button"
          className="modal-tld-btn modal-tld-btn--min"
          aria-label="Minimize"
          title="Minimize"
          onClick={(e) => {
            e.stopPropagation();
            onMinimize?.();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        />
        <button
          type="button"
          className="modal-tld-btn modal-tld-btn--zoom"
          aria-label={isMaximized ? "Restore" : "Enter full screen"}
          title={isMaximized ? "Restore" : "Enter full screen"}
          disabled={maxDisabled}
          onClick={(e) => {
            e.stopPropagation();
            if (!maxDisabled) toggleMaximize();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        />
      </div>
    ) : null;

  const winControls =
    taskWindowChrome && !mac ? (
      <div className="modal-win-ctrls" role="group" aria-label="Window">
        <button
          type="button"
          className="modal-win-btn"
          aria-label="Minimize"
          title="Minimize"
          onClick={(e) => {
            e.stopPropagation();
            onMinimize?.();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <span className="modal-win-glyph" aria-hidden>
            ―
          </span>
        </button>
        <button
          type="button"
          className="modal-win-btn"
          aria-label={isMaximized ? "Restore" : "Maximize"}
          title={isMaximized ? "Restore" : "Maximize"}
          disabled={maxDisabled}
          onClick={(e) => {
            e.stopPropagation();
            if (!maxDisabled) toggleMaximize();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <span className="modal-win-glyph" aria-hidden>
            {isMaximized ? "❐" : "□"}
          </span>
        </button>
        <button
          type="button"
          className="modal-win-btn modal-win-btn--close"
          aria-label="Close"
          title="Close"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <span className="modal-win-glyph" aria-hidden>
            ×
          </span>
        </button>
      </div>
    ) : null;

  const titlebarClass =
    mac
      ? `modal-titlebar modal-titlebar--mac${
          taskWindowChrome ? " modal-titlebar--mac-task" : ""
        }${titleBarActive ? " modal-titlebar--active" : ""}`
      : `modal-titlebar${
          taskWindowChrome ? " modal-titlebar--win-task" : ""
        }${titleBarActive ? " modal-titlebar--active" : ""}`;

  return (
    <div
      className={[
        backdropPassThrough
          ? "modal-backdrop modal-backdrop--pass-through"
          : "modal-backdrop",
        minimized ? "modal-backdrop--minimized" : null,
      ]
        .filter(Boolean)
        .join(" ")}
      role="presentation"
      style={{ zIndex }}
      aria-hidden={minimized}
      onMouseDown={
        minimized || backdropPassThrough ? undefined : onClose
      }
    >
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
        onMouseDown={(e) => {
          e.stopPropagation();
          onWindowPointerDown();
        }}
      >
        <header className={titlebarClass}>
          {taskWindowChrome
            ? mac
              ? macTld
              : titleBarAction != null
                ? (
                    <div className="modal-titlebar-action modal-titlebar-action--leading">
                      {titleBarAction}
                    </div>
                  )
                : null
            : mac
              ? defaultCloseBtn
              : titleBarAction != null
                ? (
                    <div className="modal-titlebar-action modal-titlebar-action--leading">
                      {titleBarAction}
                    </div>
                  )
                : null}
          <div
            className="modal-titlebar-drag"
            onPointerDown={onTitlePointerDown}
          >
            <span
              id={titleId}
              className="modal-title-text"
              title={titleTooltip}
            >
              {title}
            </span>
          </div>
          {taskWindowChrome
            ? mac
              ? titleBarAction != null
                ? (
                    <div className="modal-titlebar-action modal-titlebar-action--trailing">
                      {titleBarAction}
                    </div>
                  )
                : null
              : winControls
            : mac
              ? titleBarAction != null
                ? (
                    <div className="modal-titlebar-action modal-titlebar-action--trailing">
                      {titleBarAction}
                    </div>
                  )
                : null
              : defaultCloseBtn}
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
        {resizable && forcedRect == null && !isMaximized ? (
          <div className="modal-resize-layer" aria-hidden>
            {(
              [
                ["n", "Resize from top"] as const,
                ["s", "Resize from bottom"] as const,
                ["e", "Resize from right"] as const,
                ["w", "Resize from left"] as const,
                ["nw", "Resize from top-left"] as const,
                ["ne", "Resize from top-right"] as const,
                ["sw", "Resize from bottom-left"] as const,
                ["se", "Resize from bottom-right"] as const,
              ] as const
            ).map(([kind, titleT]) => (
              <div
                key={kind}
                className={`modal-resize-grip modal-resize-grip--${kind}`}
                title={titleT}
                onPointerDown={(ev) => onResizeStart(ev, kind)}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
