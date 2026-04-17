import { useEffect, useRef, useState } from "react";
import {
  fetchPlanningFile,
  PmGuiConcurrencyError,
  savePlanningFile,
} from "../api";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";
import { ModalPersistStatusFooter } from "./ModalPersistStatusFooter";
import { VISION_STARTER } from "../visionStarter";

const VISION_PATH = "vision.md";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function VisionDrawer({ open, onClose }: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [content, setContent] = useState("");
  const [missing, setMissing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnapRef = useRef({ vision: "" });
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

  useEffect(() => {
    if (!open) return;
    /* eslint-disable @eslint-react/set-state-in-effect -- reset when dialog opens */
    setMsg(null);
    setPersistMsg(null);
    setLoading(true);
    canAutosaveRef.current = false;
    /* eslint-enable @eslint-react/set-state-in-effect */
    const load = async () => {
      try {
        const r = await fetchPlanningFile(VISION_PATH);
        setContent(r.content);
        setMissing(false);
        lastSnapRef.current = { vision: r.content };
      } catch {
        setContent("");
        setMissing(true);
        lastSnapRef.current = { vision: "" };
      }
      setLoading(false);
      queueMicrotask(() => {
        canAutosaveRef.current = true;
      });
    };
    void load();
  }, [open]);

  useEffect(() => {
    if (!open || !canAutosaveRef.current || loading) return;
    if (content === lastSnapRef.current.vision) return;
    if (missing) return;

    /* eslint-disable-next-line @eslint-react/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      savePlanningFile(VISION_PATH, content)
        .then(() => {
          lastSnapRef.current = { vision: content };
          setMissing(false);
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
  }, [open, content, loading, missing, onConcurrencyConflict]);

  if (!open) return null;

  const onCreateFile = async () => {
    setMsg(null);
    try {
      await savePlanningFile(VISION_PATH, VISION_STARTER);
      setContent(VISION_STARTER);
      setMissing(false);
      lastSnapRef.current = { vision: VISION_STARTER };
      canAutosaveRef.current = true;
      setMsg("Created vision.md. Edits save automatically.");
      if (messageClearTimeoutRef.current != null) {
        window.clearTimeout(messageClearTimeoutRef.current);
      }
      messageClearTimeoutRef.current = window.setTimeout(
        () => setMsg(null),
        4000,
      );
    } catch (e: unknown) {
      if (e instanceof PmGuiConcurrencyError) {
        void onConcurrencyConflict();
        setMsg(
          "Files changed elsewhere; refreshed. Retry create or save if needed.",
        );
        return;
      }
      setMsg(String(e));
    }
  };

  return (
    <ModalFrame
      title="Vision"
      titleId="vision-title"
      onClose={onClose}
      storageKey="vision"
      footer={<ModalPersistStatusFooter msg={msg} persistMsg={persistMsg} />}
      bodyClassName="modal-body--constitution modal-body--vision"
    >
      <p className="outline-meta">
        Repo-root product vision (see README). Human-authored — not{" "}
        ~/.specy-road settings. Changes save automatically.
      </p>
      {loading ? <p>Loading…</p> : null}
      {missing ? (
        <div className="constitution-missing-banner">
          <p>
            <code>{VISION_PATH}</code> is missing. Create it to edit vision in
            the repo.
          </p>
          <button type="button" onClick={() => void onCreateFile()}>
            Create vision.md
          </button>
        </div>
      ) : null}
      <section className="constitution-md-section">
        <h3>Vision</h3>
        <label>
          {VISION_PATH}
          {/* Mount only after load so Tiptap initializes with real markdown (avoids onUpdate clobbering state). */}
          {!loading && !missing ? (
            <MarkdownWorkspace
              className="constitution-md-workspace"
              value={content}
              onChange={setContent}
              spellCheck
              disabled={false}
              editorLabel={VISION_PATH}
            />
          ) : null}
        </label>
      </section>
    </ModalFrame>
  );
}
