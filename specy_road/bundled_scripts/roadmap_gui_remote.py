"""Git remote and LLM connectivity helpers for the PM GUI (FastAPI and scripts)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from specy_road.git_workflow_config import git_branch_tip_author
from urllib.parse import quote

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from roadmap_gui_lib import apply_llm_env_from_settings  # noqa: E402
from roadmap_gui_pr_pickers import github_pulls_for_branch, gitlab_mrs_for_branch, pick_latest_github_pr, pick_latest_gitlab_mr  # noqa: E402


def test_llm_connection(llm: dict[str, Any]) -> tuple[bool, str]:
    apply_llm_env_from_settings(llm)
    try:
        from review_node import ping_llm

        ping_llm()
        return True, "LLM endpoint responded."
    except Exception as e:
        return False, str(e)


def test_git_remote(gr: dict[str, Any]) -> tuple[bool, str]:
    provider = (gr.get("provider") or "github").strip().lower()
    repo = (gr.get("repo") or "").strip()
    token = (gr.get("token") or "").strip()
    base = (gr.get("base_url") or "").strip()
    if not repo or not token:
        return False, "Repository and token are required."
    if provider == "github":
        url = f"https://api.github.com/repos/{repo}"
        hdrs = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=hdrs, timeout=15)
        if r.status_code == 200:
            return True, "GitHub API OK."
        return False, f"GitHub HTTP {r.status_code}: {r.text[:200]}"
    if provider in ("gitlab", "custom"):
        host = base.rstrip("/") if base else "https://gitlab.com"
        enc = quote(repo, safe="")
        url = f"{host}/api/v4/projects/{enc}"
        r = requests.get(url, headers={"PRIVATE-TOKEN": token}, timeout=15)
        if r.status_code == 200:
            return True, "GitLab API OK."
        return False, f"GitLab HTTP {r.status_code}: {r.text[:200]}"
    return False, f"Provider {provider!r} not implemented for test."


def _github_pr_line(repo: str, branch_name: str, token: str) -> str | None:
    owner, _, proj = repo.partition("/")
    if not proj:
        return None
    head = f"{owner}:{branch_name}"
    url = f"https://api.github.com/repos/{repo}/pulls"
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        url,
        params={"head": head, "state": "open"},
        headers=hdrs,
        timeout=15,
    )
    if r.status_code != 200 or not r.json():
        return None
    pr = r.json()[0]
    num = pr.get("number")
    st = pr.get("state")
    link = pr.get("html_url", "")
    return f"PR #{num} ({st}) {link}"


def _gitlab_mr_line(gr: dict[str, Any], repo: str, branch_name: str, token: str) -> str | None:
    raw_base = (gr.get("base_url") or "").strip().rstrip("/")
    host = raw_base or "https://gitlab.com"
    enc = quote(repo, safe="")
    url = f"{host}/api/v4/projects/{enc}/merge_requests"
    r = requests.get(
        url,
        params={"source_branch": branch_name, "state": "opened"},
        headers={"PRIVATE-TOKEN": token},
        timeout=15,
    )
    if r.status_code != 200 or not r.json():
        return None
    mr = r.json()[0]
    iid = mr.get("iid")
    web = mr.get("web_url", "")
    return f"MR !{iid} {web}"


def fetch_pr_hint(gr: dict[str, Any], branch_name: str) -> str | None:
    provider = (gr.get("provider") or "github").strip().lower()
    repo = (gr.get("repo") or "").strip()
    token = (gr.get("token") or "").strip()
    if not repo or not token or not branch_name:
        return None
    try:
        if provider == "github":
            return _github_pr_line(repo, branch_name, token)
        if provider in ("gitlab", "custom"):
            return _gitlab_mr_line(gr, repo, branch_name, token)
    except (
        requests.RequestException,
        KeyError,
        IndexError,
        ValueError,
        TypeError,
    ):
        return None
    return None


def build_pr_hints(
    by_reg: dict[str, dict[str, Any]],
    gr: dict[str, Any],
) -> dict[str, str]:
    pr_hints: dict[str, str] = {}
    for nid, entry in by_reg.items():
        br = entry.get("branch") or ""
        hint = fetch_pr_hint(gr, br)
        if hint:
            pr_hints[nid] = hint
        line = br
        started = entry.get("started")
        if started:
            line = f"{line} · {started}" if line else str(started)
        if line and nid not in pr_hints:
            pr_hints[nid] = line
        elif line and nid in pr_hints:
            pr_hints[nid] = pr_hints[nid] + "<br>" + line
    return pr_hints


def _github_dict_from_pr(
    repo: str,
    branch_name: str,
    token: str,
    pr: dict[str, Any],
    *,
    pr_state: str,
) -> dict[str, Any]:
    merged = bool(pr.get("merged")) or (pr.get("merged_at") is not None)
    assignees = [a.get("login", "") for a in (pr.get("assignees") or []) if a.get("login")]
    user = pr.get("user") or {}
    author = str(user.get("login") or "")
    gr_stub = {"provider": "github", "repo": repo, "token": token}
    return {
        "kind": "github_pr",
        "pr_state": pr_state,
        "merged": merged,
        "title": str(pr.get("title") or ""),
        "url": str(pr.get("html_url") or ""),
        "author": author,
        "assignees": assignees,
        "updated_at": pr.get("updated_at"),
        "hint_line": fetch_pr_hint(gr_stub, branch_name),
    }


def _github_pr_detail(repo: str, branch_name: str, token: str) -> dict[str, Any] | None:
    """Open PR for `head`, else newest PR for that head from `state=all` (merged vs rejected)."""
    owner, _, proj = repo.partition("/")
    if not proj:
        return None
    head = f"{owner}:{branch_name}"
    url = f"https://api.github.com/repos/{repo}/pulls"
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        url,
        params={"head": head, "state": "open"},
        headers=hdrs,
        timeout=15,
    )
    if r.status_code == 200:
        # Error JSON can be an object; never index unless the body is a list.
        raw = r.json()
        data = raw if isinstance(raw, list) else []
        if data:
            scoped = github_pulls_for_branch(data, branch_name)
            pr_open = pick_latest_github_pr(scoped)
            return _github_dict_from_pr(
                repo, branch_name, token, pr_open, pr_state="open"
            )
    r2 = requests.get(
        url,
        params={
            "head": head,
            "state": "all",
            "per_page": 30,
            "sort": "updated",
            "direction": "desc",
        },
        headers=hdrs,
        timeout=15,
    )
    if r2.status_code != 200:
        return None
    raw2 = r2.json()
    pulls = raw2 if isinstance(raw2, list) else []
    if not pulls:
        return None
    scoped = github_pulls_for_branch(pulls, branch_name)
    pr = pick_latest_github_pr(scoped)
    st = (pr.get("state") or "").lower()
    merged = bool(pr.get("merged")) or (pr.get("merged_at") is not None)
    if st == "open":
        pr_state = "open"
    elif merged:
        pr_state = "merged"
    else:
        pr_state = "rejected"
    return _github_dict_from_pr(repo, branch_name, token, pr, pr_state=pr_state)


def _gitlab_dict_from_mr(
    gr: dict[str, Any],
    repo: str,
    branch_name: str,
    token: str,
    mr: dict[str, Any],
    *,
    pr_state: str,
    merged: bool,
) -> dict[str, Any]:
    assignees = [
        str(a.get("username") or a.get("name") or "")
        for a in (mr.get("assignees") or [])
        if a
    ]
    author_o = mr.get("author") or {}
    author = str(author_o.get("username") or author_o.get("name") or "")
    gr_full = {
        "provider": "gitlab",
        "repo": repo,
        "token": token,
        "base_url": gr.get("base_url"),
    }
    return {
        "kind": "gitlab_mr",
        "pr_state": pr_state,
        "merged": merged,
        "title": str(mr.get("title") or ""),
        "url": str(mr.get("web_url") or ""),
        "author": author,
        "assignees": [x for x in assignees if x],
        "updated_at": mr.get("updated_at"),
        "hint_line": fetch_pr_hint(gr_full, branch_name),
    }


def _gitlab_mr_detail(gr: dict[str, Any], repo: str, branch_name: str, token: str) -> dict[str, Any] | None:
    raw_base = (gr.get("base_url") or "").strip().rstrip("/")
    host = raw_base or "https://gitlab.com"
    enc = quote(repo, safe="")
    url = f"{host}/api/v4/projects/{enc}/merge_requests"
    common = {"source_branch": branch_name, "order_by": "updated_at", "sort": "desc"}
    hdrs = {"PRIVATE-TOKEN": token}

    r = requests.get(
        url,
        params={**common, "state": "opened"},
        headers=hdrs,
        timeout=15,
    )
    if r.status_code == 200:
        raw_o = r.json()
        data = raw_o if isinstance(raw_o, list) else []
        if data:
            scoped = gitlab_mrs_for_branch(data, branch_name)
            mr = pick_latest_gitlab_mr(scoped)
            return _gitlab_dict_from_mr(
                gr, repo, branch_name, token, mr, pr_state="open", merged=False
            )

    r = requests.get(
        url,
        params={**common, "state": "merged"},
        headers=hdrs,
        timeout=15,
    )
    if r.status_code == 200:
        raw_m = r.json()
        data = raw_m if isinstance(raw_m, list) else []
        if data:
            scoped = gitlab_mrs_for_branch(data, branch_name)
            mr = pick_latest_gitlab_mr(scoped)
            m = bool(mr.get("merge_commit_sha"))
            return _gitlab_dict_from_mr(
                gr, repo, branch_name, token, mr, pr_state="merged", merged=m
            )

    r = requests.get(
        url,
        params={**common, "state": "closed"},
        headers=hdrs,
        timeout=15,
    )
    if r.status_code != 200:
        return None
    raw_c = r.json()
    data = raw_c if isinstance(raw_c, list) else []
    if not data:
        return None
    scoped = gitlab_mrs_for_branch(data, branch_name)
    mr = pick_latest_gitlab_mr(scoped)
    if mr.get("merge_commit_sha"):
        return _gitlab_dict_from_mr(
            gr, repo, branch_name, token, mr, pr_state="merged", merged=True
        )
    return _gitlab_dict_from_mr(
        gr, repo, branch_name, token, mr, pr_state="rejected", merged=False
    )


def fetch_branch_enrichment(gr: dict[str, Any], branch_name: str) -> dict[str, Any] | None:
    """PR/MR metadata for `branch_name`, or None if misconfigured, HTTP error, or no PR exists."""
    provider = (gr.get("provider") or "github").strip().lower()
    repo = (gr.get("repo") or "").strip()
    token = (gr.get("token") or "").strip()
    if not repo or not token or not branch_name:
        return None
    try:
        if provider == "github":
            return _github_pr_detail(repo, branch_name, token)
        if provider in ("gitlab", "custom"):
            return _gitlab_mr_detail(gr, repo, branch_name, token)
    except (
        requests.RequestException,
        KeyError,
        IndexError,
        ValueError,
        TypeError,
    ):
        return None
    return None


def enrichment_is_mr_rejected(entry: dict[str, Any] | None) -> bool:
    """True when Git enrichment indicates a closed PR/MR without merge (same rules as the PM GUI)."""
    if not entry:
        return False
    kind = str(entry.get("kind") or "")
    if kind not in ("github_pr", "gitlab_mr"):
        return False
    ps = str(entry.get("pr_state") or "").lower()
    if ps == "rejected":
        return True
    if ps == "closed" and not entry.get("merged"):
        return True
    return False


def build_registry_enrichment(
    by_reg: dict[str, dict[str, Any]],
    gr: dict[str, Any],
    *,
    repo_root: Path | None = None,
    remote: str = "origin",
) -> dict[str, dict[str, Any]]:
    """Per node_id: PR/MR lifecycle detail when a forge token is set, else remote tip or registry hint."""
    out: dict[str, dict[str, Any]] = {}
    rm = (remote or "").strip() or "origin"
    for nid, entry in by_reg.items():
        br = entry.get("branch") or ""
        detail = fetch_branch_enrichment(gr, br) if br else None
        if detail:
            out[nid] = detail
            continue
        tip_author: str | None = None
        if br and repo_root is not None:
            tip_author = git_branch_tip_author(repo_root, rm, br)
        if tip_author:
            out[nid] = {
                "kind": "remote_tip",
                "author": tip_author,
                "branch": br,
                "hint_line": f"{br} · {tip_author}",
            }
            continue
        line = br
        started = entry.get("started")
        if started:
            line = f"{line} · {started}" if line else str(started)
        if line:
            out[nid] = {
                "kind": "registry",
                "branch": br,
                "started": entry.get("started"),
                "hint_line": line,
            }
    return out
