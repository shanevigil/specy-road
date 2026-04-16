import { useEffect, useRef, useState } from "react";
import { fetchPlanningFile, savePlanningFile } from "../api";
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
  const [content, setContent] = useState("");
  const [missing, setMissing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnap = useRef({ vision: "" });
  const canAutosave = useRef(false);

  useEffect(() => {
    if (!open) return;
    /* eslint-disable react-hooks/set-state-in-effect -- reset when dialog opens */
    setMsg(null);
    setPersistMsg(null);
    setLoading(true);
    canAutosave.current = false;
    /* eslint-enable react-hooks/set-state-in-effect */
    const load = async () => {
      try {
        const r = await fetchPlanningFile(VISION_PATH);
        setContent(r.content);
        setMissing(false);
        lastSnap.current = { vision: r.content };
      } catch {
        setContent("");
        setMissing(true);
        lastSnap.current = { vision: "" };
      }
      setLoading(false);
      queueMicrotask(() => {
        canAutosave.current = true;
      });
    };
    void load();
  }, [open]);

  useEffect(() => {
    if (!open || !canAutosave.current || loading) return;
    if (content === lastSnap.current.vision) return;
    if (missing) return;

    /* eslint-disable-next-line react-hooks/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      savePlanningFile(VISION_PATH, content)
        .then(() => {
          lastSnap.current = { vision: content };
          setMissing(false);
          setPersistMsg("Saved.");
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setMsg(String(e));
          setPersistMsg(null);
        });
    }, 600);
    return () => window.clearTimeout(t);
  }, [open, content, loading, missing]);

  if (!open) return null;

  const onCreateFile = async () => {
    setMsg(null);
    try {
      await savePlanningFile(VISION_PATH, VISION_STARTER);
      setContent(VISION_STARTER);
      setMissing(false);
      lastSnap.current = { vision: VISION_STARTER };
      canAutosave.current = true;
      setMsg("Created vision.md. Edits save automatically.");
      window.setTimeout(() => setMsg(null), 4000);
    } catch (e: unknown) {
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
