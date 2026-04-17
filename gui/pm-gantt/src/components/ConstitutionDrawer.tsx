import { useEffect, useRef, useState } from "react";
import {
  fetchPlanningFile,
  PmGuiConcurrencyError,
  savePlanningFile,
  scaffoldConstitution,
} from "../api";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";
import { ModalPersistStatusFooter } from "./ModalPersistStatusFooter";

const PURPOSE_PATH = "constitution/purpose.md";
const PRINCIPLES_PATH = "constitution/principles.md";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ConstitutionDrawer({ open, onClose }: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [purpose, setPurpose] = useState("");
  const [principles, setPrinciples] = useState("");
  const [purposeMissing, setPurposeMissing] = useState(false);
  const [principlesMissing, setPrinciplesMissing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnapRef = useRef({ purpose: "", principles: "" });
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
      let p = "";
      let pr = "";
      let pMiss = false;
      let prMiss = false;
      try {
        const r = await fetchPlanningFile(PURPOSE_PATH);
        p = r.content;
      } catch {
        pMiss = true;
      }
      try {
        const r = await fetchPlanningFile(PRINCIPLES_PATH);
        pr = r.content;
      } catch {
        prMiss = true;
      }
      setPurpose(p);
      setPrinciples(pr);
      setPurposeMissing(pMiss);
      setPrinciplesMissing(prMiss);
      lastSnapRef.current = { purpose: p, principles: pr };
      setLoading(false);
      queueMicrotask(() => {
        canAutosaveRef.current = true;
      });
    };
    void load();
  }, [open]);

  useEffect(() => {
    if (!open || !canAutosaveRef.current || loading) return;
    if (
      purpose === lastSnapRef.current.purpose &&
      principles === lastSnapRef.current.principles
    ) {
      return;
    }
    if (purposeMissing || principlesMissing) return;

    /* eslint-disable-next-line @eslint-react/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      Promise.all([
        savePlanningFile(PURPOSE_PATH, purpose),
        savePlanningFile(PRINCIPLES_PATH, principles),
      ])
        .then(() => {
          lastSnapRef.current = { purpose, principles };
          setPurposeMissing(false);
          setPrinciplesMissing(false);
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
  }, [
    open,
    purpose,
    principles,
    loading,
    purposeMissing,
    principlesMissing,
    onConcurrencyConflict,
  ]);

  if (!open) return null;

  const anyMissing = purposeMissing || principlesMissing;

  const onScaffold = async () => {
    setMsg(null);
    try {
      await scaffoldConstitution(false);
      setPurposeMissing(false);
      setPrinciplesMissing(false);
      const [rp, rpr] = await Promise.all([
        fetchPlanningFile(PURPOSE_PATH),
        fetchPlanningFile(PRINCIPLES_PATH),
      ]);
      setPurpose(rp.content);
      setPrinciples(rpr.content);
      lastSnapRef.current = {
        purpose: rp.content,
        principles: rpr.content,
      };
      canAutosaveRef.current = true;
      setMsg("Starter files created. Edits save automatically.");
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
          "Files changed elsewhere; refreshed. Retry scaffold or save if needed.",
        );
        return;
      }
      setMsg(String(e));
    }
  };

  return (
    <ModalFrame
      title="Constitution"
      titleId="constitution-title"
      onClose={onClose}
      storageKey="constitution"
      footer={<ModalPersistStatusFooter msg={msg} persistMsg={persistMsg} />}
      bodyClassName="modal-body--constitution"
    >
      <p className="outline-meta">
        Human-authored files in the repo (not ~/.specy-road settings). Agents
        read these before roadmap work — see <code>AGENTS.md</code> load
        order. Changes are saved automatically.
      </p>
      {loading ? <p>Loading…</p> : null}
      {anyMissing ? (
        <div className="constitution-missing-banner">
          <p>
            One or both files are missing: <code>{PURPOSE_PATH}</code>,{" "}
            <code>{PRINCIPLES_PATH}</code>.
          </p>
          <button type="button" onClick={() => void onScaffold()}>
            Create starter files
          </button>
        </div>
      ) : null}
      <section className="constitution-md-section">
        <h3>Purpose</h3>
        <label>
          {PURPOSE_PATH}
          {!loading && !purposeMissing ? (
            <MarkdownWorkspace
              className="constitution-md-workspace"
              value={purpose}
              onChange={setPurpose}
              spellCheck
              disabled={false}
              editorLabel={PURPOSE_PATH}
            />
          ) : null}
        </label>
      </section>
      <section className="constitution-md-section">
        <h3>Principles</h3>
        <label>
          {PRINCIPLES_PATH}
          {!loading && !principlesMissing ? (
            <MarkdownWorkspace
              className="constitution-md-workspace"
              value={principles}
              onChange={setPrinciples}
              spellCheck
              disabled={false}
              editorLabel={PRINCIPLES_PATH}
            />
          ) : null}
        </label>
      </section>
    </ModalFrame>
  );
}
