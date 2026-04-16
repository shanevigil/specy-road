import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { getSettings, postGitTest, putSettings, testLlmSettings } from "../api";
import { getDefaultSettingsModalRect } from "../modalRect";
import { IconMonitor, IconMoon, IconSun } from "../toolbarIcons";
import { ModalFrame } from "./ModalFrame";

export type ThemeMode = "light" | "dark" | "system";

type Props = {
  open: boolean;
  onClose: () => void;
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
  /** Gantt / outline preferences (stored in localStorage by App). */
  highlightDepChain: boolean;
  onHighlightDepChainChange: (value: boolean) => void;
  showInheritedDeps: boolean;
  onShowInheritedDepsChange: (value: boolean) => void;
  refreshSec: number;
  onRefreshSecChange: (sec: number) => void;
};

const BACKENDS = ["openai", "azure", "compatible", "anthropic"] as const;

function normalizeBackend(raw: string): string {
  const l = raw.trim().toLowerCase();
  return BACKENDS.includes(l as (typeof BACKENDS)[number]) ? l : "openai";
}

function SettingsToggleRow({
  checked,
  onChange,
  label,
  optionTitle,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  /** Shown as native tooltip on the label and switch. */
  optionTitle: string;
}) {
  const labelId = useId();
  return (
    <div className="settings-toggle-row">
      <span
        id={labelId}
        className="settings-toggle-label"
        title={optionTitle}
      >
        {label}
      </span>
      <button
        type="button"
        className="settings-toggle"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        title={optionTitle}
        onClick={() => onChange(!checked)}
      >
        <span className="settings-toggle-thumb" aria-hidden />
      </button>
    </div>
  );
}

const THEME_ORDER: ThemeMode[] = ["light", "dark", "system"];

function ThemeModeSegmented({
  value,
  onChange,
}: {
  value: ThemeMode;
  onChange: (mode: ThemeMode) => void;
}) {
  const groupLabelId = useId();

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const i = THEME_ORDER.indexOf(value);
      if (i < 0) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        onChange(THEME_ORDER[(i + 1) % THEME_ORDER.length]!);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        onChange(
          THEME_ORDER[(i - 1 + THEME_ORDER.length) % THEME_ORDER.length]!,
        );
      }
    },
    [value, onChange],
  );

  return (
    <div className="settings-theme-row">
      <span id={groupLabelId} className="settings-theme-label">
        Theme
      </span>
      <div
        className="settings-theme-segmented"
        role="radiogroup"
        aria-labelledby={groupLabelId}
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        <button
          type="button"
          className="settings-theme-option"
          role="radio"
          aria-checked={value === "light"}
          tabIndex={-1}
          title="Light"
          onClick={() => onChange("light")}
        >
          <IconSun />
          <span className="settings-theme-option-text">Light</span>
        </button>
        <button
          type="button"
          className="settings-theme-option"
          role="radio"
          aria-checked={value === "dark"}
          tabIndex={-1}
          title="Dark"
          onClick={() => onChange("dark")}
        >
          <IconMoon />
          <span className="settings-theme-option-text">Dark</span>
        </button>
        <button
          type="button"
          className="settings-theme-option"
          role="radio"
          aria-checked={value === "system"}
          tabIndex={-1}
          title="Match system appearance"
          onClick={() => onChange("system")}
        >
          <IconMonitor />
          <span className="settings-theme-option-text">System</span>
        </button>
      </div>
    </div>
  );
}

function buildLlmPayload(llm: Record<string, string>) {
  return {
    backend: normalizeBackend(llm.backend || "openai"),
    openai_api_key: llm.openai_api_key || "",
    openai_model: llm.openai_model || "",
    openai_base_url: llm.openai_base_url || "",
    azure_endpoint: llm.azure_endpoint || "",
    azure_api_key: llm.azure_api_key || "",
    azure_deployment: llm.azure_deployment || "",
    azure_api_version: llm.azure_api_version || "",
    anthropic_api_key: llm.anthropic_api_key || "",
    anthropic_model: llm.anthropic_model || "",
  };
}

export function SettingsDrawer({
  open,
  onClose,
  themeMode,
  onThemeModeChange,
  highlightDepChain,
  onHighlightDepChainChange,
  showInheritedDeps,
  onShowInheritedDepsChange,
  refreshSec,
  onRefreshSecChange,
}: Props) {
  const [llm, setLlm] = useState<Record<string, string>>({});
  const [git, setGit] = useState<Record<string, string>>({});
  const [inheritLlm, setInheritLlm] = useState(true);
  const [inheritPmGui, setInheritPmGui] = useState(true);
  const [registryRemoteOverlay, setRegistryRemoteOverlay] = useState(false);
  const [integrationBranchAutoFf, setIntegrationBranchAutoFf] = useState(false);
  const [gitRemoteTestedOk, setGitRemoteTestedOk] = useState(false);
  const [repoLabel, setRepoLabel] = useState<string>("");
  const [msg, setMsg] = useState<string | null>(null);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  /** Last saved effective `pm_gui.registry_remote_overlay` from GET /settings. */
  const pmGuiOverlayPersistedRef = useRef(false);
  /** True after the user changes the overlay toggle (until a successful save). */
  const pmGuiOverlayDirtyRef = useRef(false);

  const skipAutosave = useRef(true);

  useEffect(() => {
    if (!open) return;
    skipAutosave.current = true;
    /* eslint-disable @eslint-react/set-state-in-effect -- reset when opening */
    setMsg(null);
    setPersistMsg(null);
    /* eslint-enable @eslint-react/set-state-in-effect */
    getSettings()
      .then((s) => {
        const l = (s.llm as Record<string, unknown>) || {};
        const g = (s.git_remote as Record<string, unknown>) || {};
        if (typeof s.inherit_llm === "boolean") setInheritLlm(s.inherit_llm);
        if (typeof s.inherit_pm_gui === "boolean") setInheritPmGui(s.inherit_pm_gui);
        const pm = (s.pm_gui as Record<string, unknown>) || {};
        const tested = s.git_remote_tested_ok === true;
        pmGuiOverlayPersistedRef.current = pm.registry_remote_overlay === true;
        pmGuiOverlayDirtyRef.current = false;
        setGitRemoteTestedOk(tested);
        setRegistryRemoteOverlay(pmGuiOverlayPersistedRef.current && tested);
        setIntegrationBranchAutoFf(pm.integration_branch_auto_ff === true);
        const root = typeof s.repo_root === "string" ? s.repo_root : "";
        setRepoLabel(root ? root : "");
        setLlm(
          Object.fromEntries(
            Object.entries(l).map(([k, v]) => [k, v == null ? "" : String(v)]),
          ),
        );
        setGit(
          Object.fromEntries(
            Object.entries(g).map(([k, v]) => [k, v == null ? "" : String(v)]),
          ),
        );
      })
      .catch((e: unknown) => setMsg(String(e)))
      .finally(() => {
        queueMicrotask(() => {
          skipAutosave.current = false;
        });
      });
  }, [open]);

  useEffect(() => {
    if (!open || skipAutosave.current) return;
    /* eslint-disable-next-line @eslint-react/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      const overlayOutbound = pmGuiOverlayDirtyRef.current
        ? registryRemoteOverlay
        : pmGuiOverlayPersistedRef.current;
      putSettings({
        inherit_llm: inheritLlm,
        inherit_git_remote: false,
        inherit_pm_gui: inheritPmGui,
        llm: buildLlmPayload(llm),
        git_remote: {
          provider: git.provider || "github",
          repo: git.repo || "",
          token: git.token || "",
          base_url: git.base_url || "",
        },
        pm_gui: {
          registry_remote_overlay: overlayOutbound,
          integration_branch_auto_ff: integrationBranchAutoFf,
        },
      })
        .then(() => {
          pmGuiOverlayPersistedRef.current = overlayOutbound;
          pmGuiOverlayDirtyRef.current = false;
          setPersistMsg("Saved.");
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setMsg(String(e));
          setPersistMsg(null);
        });
    }, 800);
    return () => window.clearTimeout(t);
  }, [
    llm,
    git,
    inheritLlm,
    inheritPmGui,
    registryRemoteOverlay,
    integrationBranchAutoFf,
    open,
  ]);

  if (!open) return null;

  const backend = normalizeBackend(llm.backend || "openai");

  const testLlm = async () => {
    setMsg(null);
    try {
      const out = await testLlmSettings(buildLlmPayload(llm));
      setMsg(out.message || "LLM endpoint responded.");
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const testGit = async () => {
    setMsg(null);
    try {
      const out = await postGitTest({
        provider: git.provider || "github",
        repo: git.repo || "",
        token: git.token || "",
        base_url: git.base_url || "",
      });
      setMsg(out.message || "Git remote responded.");
      if (out.git_remote_tested_ok) {
        setGitRemoteTestedOk(true);
        setRegistryRemoteOverlay(pmGuiOverlayPersistedRef.current);
      }
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const footer = <span>{persistMsg || msg}</span>;

  return (
    <ModalFrame
      title="Settings"
      titleId="settings-title"
      onClose={onClose}
      getDefaultRect={getDefaultSettingsModalRect}
      reanchorOnResize
      resizable={false}
      footer={footer}
    >
      <p className="outline-meta">
        Credentials live in ~/.specy-road/gui-settings.json (global LLM defaults when
        enabled below; Git remote is always per open repository). API keys use simple
        obfuscation on disk, not encryption. Environment variables still override saved
        values when set. Changes save automatically.
      </p>
      {repoLabel ? (
        <p className="outline-meta" title={repoLabel}>
          Open repository: <code className="settings-repo-path">{repoLabel}</code>
        </p>
      ) : null}
      <div className="settings-section-heading">
        <h3>This repository</h3>
      </div>
      <SettingsToggleRow
        checked={inheritLlm}
        onChange={setInheritLlm}
        label="Use global LLM settings for this repository"
        optionTitle="When on, values you save become the global LLM defaults. When off, the form starts blank for this repository only—enter credentials here to store them for this checkout (nothing is shared with other projects)."
      />
      <SettingsToggleRow
        checked={inheritPmGui}
        onChange={setInheritPmGui}
        label="Use global PM GUI options for this repository"
        optionTitle="When off, the PM GUI toggles below (registry overlay, integration fast-forward) are stored only for this repository."
      />
      <SettingsToggleRow
        checked={registryRemoteOverlay}
        onChange={(next) => {
          if (next && !gitRemoteTestedOk) {
            setMsg(
              'Use "Test Git" successfully (GitHub/GitLab API) before enabling this option.',
            );
            return;
          }
          pmGuiOverlayDirtyRef.current = true;
          setRegistryRemoteOverlay(next);
        }}
        label="Merge registry from remote feature branches"
        optionTitle={
          gitRemoteTestedOk
            ? "When on, the server reads roadmap/registry.yaml from refs/remotes/<remote>/feature/rm-* (periodic git fetch, same cadence as chart auto-refresh by default) and merges active claims with your working tree."
            : 'Disabled until Git remote credentials are saved and "Test Git" succeeds (GitHub or GitLab).'
        }
      />
      <SettingsToggleRow
        checked={integrationBranchAutoFf}
        onChange={setIntegrationBranchAutoFf}
        label="Fast-forward integration branch (git fetch + merge --ff-only)"
        optionTitle="When you are checked out on the integration branch from roadmap/git-workflow.yaml and the working tree is clean, the server periodically runs git fetch and merge --ff-only so the PM chart matches the remote trunk (throttled; interval matches registry fetch by default, overridable via SPECY_ROAD_GUI_INTEGRATION_FF_INTERVAL_S). Ignored on other branches or with local changes."
      />
      <h3 className="settings-appearance-title">Appearance</h3>
      <ThemeModeSegmented value={themeMode} onChange={onThemeModeChange} />
      <h3
        className="settings-pm-chart-title"
        title="Chart display and refresh options are saved in this browser only (localStorage), keyed to the repository shown under Open repository (same scope as server settings)."
      >
        PM Chart Settings
      </h3>
      <SettingsToggleRow
        checked={highlightDepChain}
        onChange={onHighlightDepChainChange}
        label="Highlight full dependency chain on chart"
        optionTitle="Tint Gantt rows for every preceding dependency of the selection: transitive prerequisites using explicit deps and deps inherited from ancestor nodes (independent of dashed-line display)"
      />
      <SettingsToggleRow
        checked={showInheritedDeps}
        onChange={onShowInheritedDepsChange}
        label="Show inherited dependencies (dashed lines)"
        optionTitle="Show dashed lines for dependencies inherited from ancestor nodes (group-level)"
      />
      <label>
        Auto-refresh
        <select
          value={refreshSec}
          onChange={(e) => onRefreshSecChange(Number(e.target.value))}
          title="Poll roadmap files; reload when the fingerprint changes"
        >
          <option value={0}>Off</option>
          <option value={5}>5 s</option>
          <option value={10}>10 s</option>
          <option value={15}>15 s</option>
          <option value={30}>30 s</option>
          <option value={60}>60 s</option>
          <option value={120}>120 s</option>
        </select>
      </label>
      <hr className="settings-section-rule" aria-hidden="true" />
      <div className="settings-section-heading">
        <h3>Git remote</h3>
        <button type="button" onClick={() => void testGit()}>
          Test Git
        </button>
      </div>
      <label>
        Provider
        <select
          value={git.provider || "github"}
          onChange={(e) => setGit({ ...git, provider: e.target.value })}
        >
          <option value="github">github</option>
          <option value="gitlab">gitlab</option>
          <option value="custom">custom (GitLab)</option>
        </select>
      </label>
      <label>
        Repo (owner/name)
        <input
          value={git.repo || ""}
          onChange={(e) => setGit({ ...git, repo: e.target.value })}
        />
      </label>
      <label>
        Token
        <input
          type="password"
          value={git.token || ""}
          onChange={(e) => setGit({ ...git, token: e.target.value })}
          autoComplete="off"
        />
      </label>
      <label>
        Base URL (GitLab)
        <input
          value={git.base_url || ""}
          onChange={(e) => setGit({ ...git, base_url: e.target.value })}
          placeholder="https://gitlab.com"
        />
      </label>
      <hr className="settings-section-rule" aria-hidden="true" />
      <div className="settings-section-heading">
        <h3>LLM (optional)</h3>
        <button type="button" onClick={() => void testLlm()}>
          Test LLM
        </button>
      </div>
      <label>
        Backend
        <select
          value={backend}
          onChange={(e) => setLlm({ ...llm, backend: e.target.value })}
        >
          <option value="openai">openai</option>
          <option value="azure">azure</option>
          <option value="compatible">compatible (OpenAI-compatible API)</option>
          <option value="anthropic">anthropic (Claude)</option>
        </select>
      </label>
      {backend === "azure" ? (
        <>
          <label>
            Azure endpoint
            <input
              value={llm.azure_endpoint || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_endpoint: e.target.value })
              }
            />
          </label>
          <label>
            Azure API key
            <input
              type="password"
              value={llm.azure_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Deployment name
            <input
              value={llm.azure_deployment || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_deployment: e.target.value })
              }
            />
          </label>
          <label>
            API version
            <input
              value={llm.azure_api_version || ""}
              placeholder="2024-02-15-preview"
              onChange={(e) =>
                setLlm({ ...llm, azure_api_version: e.target.value })
              }
            />
          </label>
        </>
      ) : null}
      {backend === "anthropic" ? (
        <>
          <label>
            Anthropic API key
            <input
              type="password"
              value={llm.anthropic_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, anthropic_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Model
            <input
              value={llm.anthropic_model || ""}
              onChange={(e) =>
                setLlm({ ...llm, anthropic_model: e.target.value })
              }
              placeholder="claude-sonnet-4-20250514"
            />
          </label>
        </>
      ) : null}
      {backend === "openai" || backend === "compatible" ? (
        <>
          <label>
            API key
            <input
              type="password"
              value={llm.openai_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, openai_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Model
            <input
              value={llm.openai_model || ""}
              onChange={(e) =>
                setLlm({ ...llm, openai_model: e.target.value })
              }
              placeholder="gpt-4o-mini"
            />
          </label>
          {backend === "compatible" ? (
            <label>
              Base URL
              <input
                value={llm.openai_base_url || ""}
                onChange={(e) =>
                  setLlm({ ...llm, openai_base_url: e.target.value })
                }
              />
            </label>
          ) : null}
        </>
      ) : null}
    </ModalFrame>
  );
}
