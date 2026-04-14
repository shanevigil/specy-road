import type { GitWorkflowPayload } from "../types";
import { computeGitWorkflowPresentation } from "../gitWorkflowUi";

type Props = {
  gitWorkflow: GitWorkflowPayload | undefined;
};

/**
 * Read-only status next to the settings gear (not a button).
 * Red / yellow / green per contract + git connectivity.
 */
export function GitWorkflowStatusLabel({ gitWorkflow }: Props) {
  if (gitWorkflow === undefined) {
    return (
      <span
        className="app-header-git-workflow app-header-git-workflow--loading"
        aria-hidden="true"
      >
        Git —…
      </span>
    );
  }

  const pres = computeGitWorkflowPresentation(gitWorkflow);
  const tipId = "git-workflow-status-tip";
  const { resolved } = gitWorkflow;

  return (
    <div className="app-header-git-workflow-tooltip app-header-doc-tooltip">
      <span
        id="git-workflow-status-label"
        className={`app-header-git-workflow-label app-header-git-workflow-label--${pres.tone}`}
        tabIndex={0}
        aria-describedby={tipId}
      >
        {pres.label}
      </span>
      <div
        id={tipId}
        role="tooltip"
        className="app-header-doc-tip app-header-doc-tip--wide app-header-doc-tip--git-workflow"
      >
        <p className="git-workflow-tip-intro">{pres.tooltipIntro}</p>
        {gitWorkflow.issues.length > 0 ? (
          <div className="git-workflow-issues-block">
            <div className="git-workflow-tip-section-title">Details</div>
            {gitWorkflow.issues.map((issue) => (
              <div key={issue.code} className="git-workflow-issue">
                <strong>{issue.message}</strong>
                <div className="git-workflow-issue-detail">{issue.detail}</div>
              </div>
            ))}
          </div>
        ) : null}
        <div className="git-workflow-resolved-block">
          <div className="git-workflow-tip-section-title">Resolved</div>
          <ul className="git-workflow-resolved-list">
            <li>
              Integration branch:{" "}
              <code>{resolved.integration_branch}</code>
            </li>
            <li>
              Remote: <code>{resolved.remote}</code>
            </li>
            <li>
              Current branch:{" "}
              {resolved.git_branch_current != null &&
              resolved.git_branch_current.length > 0
                ? resolved.git_branch_current
                : "(detached or unnamed)"}
            </li>
            {resolved.git_head_short ? (
              <li>
                HEAD: <code>{resolved.git_head_short}</code>
              </li>
            ) : null}
          </ul>
        </div>
      </div>
    </div>
  );
}
