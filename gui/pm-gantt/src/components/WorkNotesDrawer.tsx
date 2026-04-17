import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchPlanningFile,
  fetchWorkspaceFiles,
  PmGuiConcurrencyError,
  savePlanningFile,
  type WorkspaceFileEntry,
} from "../api";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";
import { ModalPersistStatusFooter } from "./ModalPersistStatusFooter";

const NEW_NOTE_TEMPLATE = `# Session

_Add session notes, decisions, and follow-ups._

`;

function newWorkNotePath(): string {
  return `work/session-${Date.now()}.md`;
}

type Props = {
  open: boolean;
  onClose: () => void;
};

export function WorkNotesDrawer({ open, onClose }: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [mdFiles, setMdFiles] = useState<WorkspaceFileEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnapRef = useRef({ content: "" });
  const canAutosaveRef = useRef(false);
  const persistClearTimeoutRef = useRef<number | null>(null);
  const messageClearTimeoutRef = useRef<number | null>(null);

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

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    try {
      const r = await fetchWorkspaceFiles("work");
      const mds = r.files.filter(
        (f) => f.name.toLowerCase().endsWith(".md"),
      );
      setMdFiles(mds);
      return mds;
    } catch (e: unknown) {
      setMsg(String(e));
      return [];
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setMsg(null);
    setPersistMsg(null);
    setSelectedPath(null);
    setContent("");
    lastSnapRef.current = { content: "" };
    canAutosaveRef.current = false;
    void (async () => {
      const mds = await refreshList();
      queueMicrotask(() => {
        canAutosaveRef.current = true;
      });
      if (mds.length > 0) {
        const first = mds[0].path;
        setSelectedPath(first);
        setLoadingFile(true);
        try {
          const r = await fetchPlanningFile(first);
          setContent(r.content);
          lastSnapRef.current = { content: r.content };
        } catch (e: unknown) {
          setMsg(String(e));
        } finally {
          setLoadingFile(false);
        }
      }
    })();
  }, [open, refreshList]);

  const loadPath = useCallback(
    async (path: string) => {
      setLoadingFile(true);
      setMsg(null);
      try {
        const r = await fetchPlanningFile(path);
        setContent(r.content);
        lastSnapRef.current = { content: r.content };
      } catch (e: unknown) {
        setMsg(String(e));
      } finally {
        setLoadingFile(false);
      }
    },
    [],
  );

  const selectPath = useCallback(
    async (path: string) => {
      if (path === selectedPath) return;
      if (selectedPath && canAutosaveRef.current) {
        const cur = content;
        if (cur !== lastSnapRef.current.content) {
          try {
            await savePlanningFile(selectedPath, cur);
            lastSnapRef.current = { content: cur };
          } catch (e: unknown) {
            if (e instanceof PmGuiConcurrencyError) {
              void onConcurrencyConflict();
              setMsg(
                "Files changed elsewhere; refreshed. Retry your save if needed.",
              );
              return;
            }
            setMsg(String(e));
            return;
          }
        }
      }
      setSelectedPath(path);
      await loadPath(path);
    },
    [selectedPath, content, loadPath, onConcurrencyConflict],
  );

  const addNote = useCallback(async () => {
    setMsg(null);
    const path = newWorkNotePath();
    try {
      await savePlanningFile(path, NEW_NOTE_TEMPLATE);
      await refreshList();
      setSelectedPath(path);
      setContent(NEW_NOTE_TEMPLATE);
      lastSnapRef.current = { content: NEW_NOTE_TEMPLATE };
      canAutosaveRef.current = true;
      setMsg("New note created.");
      if (messageClearTimeoutRef.current != null) {
        window.clearTimeout(messageClearTimeoutRef.current);
      }
      messageClearTimeoutRef.current = window.setTimeout(
        () => setMsg(null),
        2500,
      );
    } catch (e: unknown) {
      if (e instanceof PmGuiConcurrencyError) {
        void onConcurrencyConflict();
        setMsg(
          "Files changed elsewhere; refreshed. Retry create if needed.",
        );
        return;
      }
      setMsg(String(e));
    }
  }, [refreshList, onConcurrencyConflict]);

  useEffect(() => {
    if (!open || !canAutosaveRef.current || loadingFile || !selectedPath) {
      return;
    }
    if (content === lastSnapRef.current.content) return;

    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      savePlanningFile(selectedPath, content)
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
  }, [open, content, loadingFile, selectedPath, onConcurrencyConflict]);

  if (!open) return null;

  return (
    <ModalFrame
      title="Session notes"
      titleId="session-notes-title"
      onClose={onClose}
      storageKey="session-notes"
      footer={<ModalPersistStatusFooter msg={msg} persistMsg={persistMsg} />}
      bodyClassName="modal-body--workspace modal-body--work-notes"
    >
      <p className="outline-meta">
        Session notes and working markdown under <code>work/</code>. Files are
        plain repo files — saved automatically while you type.
      </p>
      <div className="workspace-notes-layout">
        <div className="workspace-notes-sidebar">
          <div className="workspace-notes-actions">
            <button type="button" onClick={() => void addNote()}>
              New session note
            </button>
          </div>
          {loadingList ? <p className="outline-meta">Loading list…</p> : null}
          <ul
            className="workspace-file-list"
            role="listbox"
            aria-label="Session note markdown files"
          >
            {mdFiles.length === 0 && !loadingList ? (
              <li className="workspace-empty">No notes yet — create one.</li>
            ) : (
              mdFiles.map((f) => (
                <li key={f.path}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selectedPath === f.path}
                    className={
                      selectedPath === f.path
                        ? "workspace-file-pill selected"
                        : "workspace-file-pill"
                    }
                    onClick={() => void selectPath(f.path)}
                  >
                    {f.name}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="workspace-notes-editor">
          {selectedPath ? (
            <label className="workspace-editor-label">
              <code>{selectedPath}</code>
              <MarkdownWorkspace
                className="constitution-md-workspace"
                value={content}
                onChange={setContent}
                spellCheck
                disabled={loadingFile}
                editorLabel={selectedPath}
              />
            </label>
          ) : (
            <p className="outline-meta">Select a file or create a new session note.</p>
          )}
        </div>
      </div>
    </ModalFrame>
  );
}
