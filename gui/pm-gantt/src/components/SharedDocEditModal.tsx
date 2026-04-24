import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchSharedFile,
  PmGuiConcurrencyError,
  saveSharedFile,
} from "../api";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";
import { ModalPersistStatusFooter } from "./ModalPersistStatusFooter";

type Props = {
  open: boolean;
  filePath: string | null;
  onClose: () => void;
  /** Keep the window below the app header (viewport Y of header bottom). */
  minTop: number;
};

function fileTitle(path: string): string {
  const i = path.lastIndexOf("/");
  return i >= 0 ? path.slice(i + 1) : path;
}

function storageKeyForPath(path: string): string {
  return `shared-doc-${path.replace(/[^a-zA-Z0-9_.-]/g, "_")}`;
}

export function SharedDocEditModal({
  open,
  filePath,
  onClose,
  minTop,
}: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnapRef = useRef({ content: "" });
  const canAutosaveRef = useRef(false);
  const persistClearTimeoutRef = useRef<number | null>(null);
  const messageClearTimeoutRef = useRef<number | null>(null);
  const loadedPathRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (persistClearTimeoutRef.current != null) {
        window.clearTimeout(persistClearTimeoutRef.current);
      }
      if (messageClearTimeoutRef.current != null) {
        window.clearTimeout(messageClearTimeoutRef.current);
      }
    };
  }, []);

  const loadFile = useCallback(
    async (path: string) => {
      setLoading(true);
      setMsg(null);
      canAutosaveRef.current = false;
      try {
        const r = await fetchSharedFile(path);
        setContent(r.content);
        lastSnapRef.current = { content: r.content };
        loadedPathRef.current = path;
        queueMicrotask(() => {
          canAutosaveRef.current = true;
        });
      } catch (e: unknown) {
        setMsg(String(e));
        setContent("");
        lastSnapRef.current = { content: "" };
        loadedPathRef.current = null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!open || !filePath) {
      canAutosaveRef.current = false;
      loadedPathRef.current = null;
      return;
    }
    void loadFile(filePath);
  }, [open, filePath, loadFile]);

  useEffect(() => {
    if (!open || !filePath || !canAutosaveRef.current || loading) {
      return;
    }
    if (content === lastSnapRef.current.content) return;
    if (filePath !== loadedPathRef.current) return;

    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      saveSharedFile(filePath, content)
        .then(() => {
          lastSnapRef.current = { content };
          setPersistMsg("Saved.");
          if (persistClearTimeoutRef.current != null) {
            window.clearTimeout(persistClearTimeoutRef.current);
          }
          persistClearTimeoutRef.current = window.setTimeout(
            () => setPersistMsg(null),
            2000,
          );
        })
        .catch((e: unknown) => {
          if (e instanceof PmGuiConcurrencyError) {
            void onConcurrencyConflict();
            setMsg(
              "Files changed elsewhere; refreshed. Retry your save if needed.",
            );
            setPersistMsg(null);
            return;
          }
          setMsg(String(e));
          setPersistMsg(null);
        });
    }, 600);
    return () => window.clearTimeout(t);
  }, [open, filePath, content, loading, onConcurrencyConflict]);

  if (!open || !filePath) {
    return null;
  }

  return (
    <ModalFrame
      title={fileTitle(filePath)}
      titleTooltip={filePath}
      titleId="shared-doc-edit-title"
      onClose={onClose}
      storageKey={storageKeyForPath(filePath)}
      minTop={minTop}
      zIndex={60}
      footer={
        <ModalPersistStatusFooter msg={msg} persistMsg={persistMsg} />
      }
      bodyClassName="modal-body--workspace modal-body--shared-doc-edit"
    >
      <p className="outline-meta">
        Editing <code>{filePath}</code> — saved automatically while you type.
      </p>
      <div className="shared-doc-edit-body">
        {loading ? (
          <p className="modal-edit-loading">Loading…</p>
        ) : (
          <label className="workspace-editor-label">
            <MarkdownWorkspace
              className="constitution-md-workspace"
              value={content}
              onChange={setContent}
              spellCheck
              disabled={loading}
              editorLabel={filePath}
            />
          </label>
        )}
      </div>
    </ModalFrame>
  );
}
