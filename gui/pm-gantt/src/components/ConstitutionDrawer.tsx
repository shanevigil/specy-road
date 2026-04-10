import { useEffect, useRef, useState } from "react";
import {
  fetchPlanningFile,
  savePlanningFile,
  scaffoldConstitution,
} from "../api";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";

const PURPOSE_PATH = "constitution/purpose.md";
const PRINCIPLES_PATH = "constitution/principles.md";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ConstitutionDrawer({ open, onClose }: Props) {
  const [purpose, setPurpose] = useState("");
  const [principles, setPrinciples] = useState("");
  const [purposeMissing, setPurposeMissing] = useState(false);
  const [principlesMissing, setPrinciplesMissing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSnap = useRef({ purpose: "", principles: "" });
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
      lastSnap.current = { purpose: p, principles: pr };
      setLoading(false);
      queueMicrotask(() => {
        canAutosave.current = true;
      });
    };
    void load();
  }, [open]);

  useEffect(() => {
    if (!open || !canAutosave.current || loading) return;
    if (
      purpose === lastSnap.current.purpose &&
      principles === lastSnap.current.principles
    ) {
      return;
    }
    if (purposeMissing || principlesMissing) return;

    /* eslint-disable-next-line react-hooks/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      Promise.all([
        savePlanningFile(PURPOSE_PATH, purpose),
        savePlanningFile(PRINCIPLES_PATH, principles),
      ])
        .then(() => {
          lastSnap.current = { purpose, principles };
          setPurposeMissing(false);
          setPrinciplesMissing(false);
          setPersistMsg("Saved.");
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setMsg(String(e));
          setPersistMsg(null);
        });
    }, 600);
    return () => window.clearTimeout(t);
  }, [open, purpose, principles, loading, purposeMissing, principlesMissing]);

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
      lastSnap.current = {
        purpose: rp.content,
        principles: rpr.content,
      };
      canAutosave.current = true;
      setMsg("Starter files created. Edits save automatically.");
      window.setTimeout(() => setMsg(null), 4000);
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const footer = (
    <>
      {msg ? <span>{msg}</span> : null}
      {persistMsg ? <span>{persistMsg}</span> : null}
    </>
  );

  return (
    <ModalFrame
      title="Constitution"
      titleId="constitution-title"
      onClose={onClose}
      footer={msg || persistMsg ? footer : null}
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
          <MarkdownWorkspace
            className="constitution-md-workspace"
            value={purpose}
            onChange={setPurpose}
            spellCheck
            disabled={loading}
            defaultViewMode="split"
            sourceLabel={`${PURPOSE_PATH} source`}
            previewLabel={`${PURPOSE_PATH} preview`}
          />
        </label>
      </section>
      <section className="constitution-md-section">
        <h3>Principles</h3>
        <label>
          {PRINCIPLES_PATH}
          <MarkdownWorkspace
            className="constitution-md-workspace"
            value={principles}
            onChange={setPrinciples}
            spellCheck
            disabled={loading}
            defaultViewMode="split"
            sourceLabel={`${PRINCIPLES_PATH} source`}
            previewLabel={`${PRINCIPLES_PATH} preview`}
          />
        </label>
      </section>
    </ModalFrame>
  );
}
