"""Git remote and LLM connectivity helpers for roadmap_gui."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from roadmap_gui_lib import apply_llm_env_from_settings  # noqa: E402


def test_llm_connection(llm: dict[str, Any]) -> tuple[bool, str]:
    apply_llm_env_from_settings(llm)
    try:
        from openai import AzureOpenAI

        from review_node import _make_client

        client = _make_client()
        if isinstance(client, AzureOpenAI):
            model = os.environ["SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT"]
        else:
            model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=3,
        )
        _ = resp.choices[0].message.content
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
