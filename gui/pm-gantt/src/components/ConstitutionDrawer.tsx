import { useEffect, useState } from "react";
import {
  fetchPlanningFile,
  savePlanningFile,
  scaffoldConstitution,
} from "../api";

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

  useEffect(() => {
    if (!open) return;
    setMsg(null);
    setLoading(true);
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
      setLoading(false);
    };
    void load();
  }, [open]);

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
      setMsg("Starter files created. Edit and save as needed.");
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const onSave = async () => {
    setMsg(null);
    try {
      await savePlanningFile(PURPOSE_PATH, purpose);
      await savePlanningFile(PRINCIPLES_PATH, principles);
      setPurposeMissing(false);
      setPrinciplesMissing(false);
      setMsg("Saved to repository.");
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  return (
    <>
      <div
        className="drawer-backdrop"
        role="presentation"
        onMouseDown={onClose}
      />
      <aside
        className="drawer constitution-drawer"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>Constitution</h2>
        <p className="outline-meta">
          Human-authored files in the repo (not ~/.specy-road settings). Agents
          read these before roadmap work — see <code>AGENTS.md</code> load
          order.
        </p>
        {loading ? <p>Loading…</p> : null}
        {msg ? <p>{msg}</p> : null}
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
        <h3>Purpose</h3>
        <label>
          {PURPOSE_PATH}
          <textarea
            className="constitution-editor"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            spellCheck
            disabled={loading}
          />
        </label>
        <h3>Principles</h3>
        <label>
          {PRINCIPLES_PATH}
          <textarea
            className="constitution-editor"
            value={principles}
            onChange={(e) => setPrinciples(e.target.value)}
            spellCheck
            disabled={loading}
          />
        </label>
        <div className="modal-actions" style={{ marginTop: "1rem" }}>
          <button type="button" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={loading}
          >
            Save both
          </button>
        </div>
      </aside>
    </>
  );
}
