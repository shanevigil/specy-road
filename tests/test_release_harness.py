"""Golden tests for the release harness.

These tests are *not* about exercising the release flow at runtime
(that lives in `docs/release-runbook.md`). They lock down the **shape**
of the workflow files and helper scripts so a future rename, regex
typo, or trust-binding drift fails CI before it breaks an actual
release.

Specifically guarded:

- The two GitHub environments named in `release-publish.yml`
  (`pypi`, `testpypi`) match what the PyPI Trusted Publisher records
  expect. A rename here breaks publishing until the trust binding
  is updated on `pypi.org` / `test.pypi.org`.
- The tag glob in `release-publish.yml` accepts `vX.Y.Z` and prerelease
  forms (`vX.Y.Z-rcN`).
- The release-marker regex in `main-release-tag-gate.yml` requires
  the leading ``v`` (the bare ``release: 0.1.0`` form is rejected) and
  accepts both finals and prereleases.
- ``check_release_version.py`` PEP 440 normalization (``vX.Y.Z-rcN`` ↔
  pyproject ``X.Y.ZrcN``) round-trips correctly.
- ``post_release_readme_cleanup.py`` is idempotent (re-running on a
  clean README is a no-op).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"


def _load_yaml(path: Path) -> dict:
    with path.open("rb") as f:
        return yaml.safe_load(f)


def test_release_publish_workflow_parses() -> None:
    doc = _load_yaml(WORKFLOWS / "release-publish.yml")
    assert isinstance(doc, dict)
    # PyYAML parses the bare 'on' key as boolean True; either is fine
    # so long as the trigger block exists.
    assert ("on" in doc) or (True in doc)
    assert "jobs" in doc


def test_main_release_tag_gate_workflow_parses() -> None:
    doc = _load_yaml(WORKFLOWS / "main-release-tag-gate.yml")
    assert isinstance(doc, dict)
    assert "jobs" in doc


def test_pr_conventions_workflow_parses() -> None:
    doc = _load_yaml(WORKFLOWS / "pr-conventions.yml")
    assert isinstance(doc, dict)
    assert "jobs" in doc


def test_validate_workflow_parses() -> None:
    doc = _load_yaml(WORKFLOWS / "validate.yml")
    assert isinstance(doc, dict)
    assert "jobs" in doc


def test_release_publish_environment_names_are_stable() -> None:
    """``pypi`` and ``testpypi`` are bound to the OIDC trust on real PyPI.

    Renaming either of them silently breaks publishing — the trust
    binding on `pypi.org` and `test.pypi.org` records the GitHub
    environment name verbatim. Read the workflow source as text (not
    parsed YAML) so the assertion is robust against PyYAML's
    treatment of the ``on:`` key.
    """
    src = (WORKFLOWS / "release-publish.yml").read_text(encoding="utf-8")
    # The 'pypi' job's environment.name and the 'testpypi' job's
    # environment.name must both appear, exactly. Both trust bindings
    # are "owner/repo + workflow file + environment name"; environment
    # name is the only one we control inside this file.
    assert "name: pypi\n" in src, (
        "release-publish.yml lost its `environment: name: pypi` line; "
        "this will break PyPI trusted publishing until the trust "
        "binding on pypi.org is updated to the new name."
    )
    assert "name: testpypi\n" in src, (
        "release-publish.yml lost its `environment: name: testpypi` line; "
        "this will break TestPyPI trusted publishing until the trust "
        "binding on test.pypi.org is updated to the new name."
    )


def test_release_publish_tag_glob_matches_finals_and_prereleases() -> None:
    """``on.push.tags: ['v*.*.*']`` must match both ``v0.1.0`` and ``v0.1.0-rc1``."""
    src = (WORKFLOWS / "release-publish.yml").read_text(encoding="utf-8")
    # Glob style, not regex. Verify the literal glob is present; then
    # re-derive whether it would match the canonical examples by hand
    # (fnmatch-style: '*' matches any sequence except path separator,
    # and '.' is literal here).
    assert "- 'v*.*.*'" in src, (
        "release-publish.yml lost its 'v*.*.*' tag glob trigger; "
        "tag pushes will no longer fire the publish workflow."
    )
    import fnmatch

    assert fnmatch.fnmatch("v0.1.0", "v*.*.*")
    assert fnmatch.fnmatch("v0.1.0-rc1", "v*.*.*")
    assert fnmatch.fnmatch("v1.2.3", "v*.*.*")
    # Negative: bare semver without the v prefix would NOT trigger.
    assert not fnmatch.fnmatch("0.1.0", "v*.*.*")


def test_release_marker_regex_requires_v_prefix() -> None:
    """The PR-title regex in main-release-tag-gate.yml rejects ``release: 0.1.0``."""
    src = (WORKFLOWS / "main-release-tag-gate.yml").read_text(encoding="utf-8")
    # The regex literal lives in a YAML env block; pull it out.
    m = re.search(r"RELEASE_TITLE_RE:\s*'([^']+)'", src)
    assert m, "RELEASE_TITLE_RE env var is missing from main-release-tag-gate.yml"
    title_re = re.compile(m.group(1), re.IGNORECASE)
    # Accepts the canonical forms.
    assert title_re.search("release: v0.1.0")
    assert title_re.search("release: v0.1.0-rc1")
    assert title_re.search("release: v1.2.3")
    # Rejects the leading-v-missing forms.
    assert not title_re.search("release: 0.1.0")
    assert not title_re.search("release:0.1.0")
    # Rejects garbage.
    assert not title_re.search("release: vfoo")
    assert not title_re.search("release: v0.1")


def test_check_release_version_pep440_normalization(tmp_path: Path) -> None:
    """``vX.Y.Z-rcN`` (tag form) compares equal to ``X.Y.ZrcN`` (pyproject form)."""
    # Stage a tmp pyproject.toml with a prerelease version and assert
    # the script exits 0 against the matching dash-form tag.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "specy-road"\nversion = "0.2.0rc1"\n',
        encoding="utf-8",
    )
    script = REPO / "scripts" / "check_release_version.py"
    r = subprocess.run(
        [sys.executable, str(script), "v0.2.0-rc1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"expected ok, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "ok:" in r.stdout

    # Final form passes through unchanged.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "specy-road"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(script), "v0.2.0"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "ok:" in r.stdout


def test_check_release_version_rejects_mismatch(tmp_path: Path) -> None:
    """Mismatch must exit 1 with a clear error."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "specy-road"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    script = REPO / "scripts" / "check_release_version.py"
    r = subprocess.run(
        [sys.executable, str(script), "v0.2.0"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "does NOT match tag" in r.stderr


def test_post_release_readme_cleanup_idempotent(tmp_path: Path) -> None:
    """Re-running the cleanup script on an already-clean README is a no-op."""
    # Use the actual current README (post-cleanup, on this branch) to
    # exercise the idempotency path.
    readme_src = (REPO / "README.md").read_text(encoding="utf-8")

    script = REPO / "scripts" / "post_release_readme_cleanup.py"
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    target = workdir / "README.md"
    target.write_text(readme_src, encoding="utf-8")

    r1 = subprocess.run(
        [sys.executable, str(script), "0.1.0"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stderr
    after_first = target.read_text(encoding="utf-8")

    r2 = subprocess.run(
        [sys.executable, str(script), "0.1.0"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr
    after_second = target.read_text(encoding="utf-8")

    assert after_first == after_second, (
        "post_release_readme_cleanup.py is not idempotent; "
        "second run produced a different README"
    )


def test_release_runbook_exists_and_referenced() -> None:
    """The canonical release runbook must exist and be referenced from key places."""
    runbook = REPO / "docs" / "release-runbook.md"
    assert runbook.is_file(), "docs/release-runbook.md is missing"
    body = runbook.read_text(encoding="utf-8")
    assert "RC release to TestPyPI" in body
    assert "Final release to PyPI" in body
    # Recovery section by symbol/heading text — keeps the test stable
    # if formatting tweaks renumber the entries.
    assert "If something goes wrong" in body

    agents_md = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "release-runbook.md" in agents_md, (
        "AGENTS.md must link to docs/release-runbook.md"
    )

    cursor_rule = (
        REPO / ".cursor" / "rules" / "030-git-workflow-management.mdc"
    ).read_text(encoding="utf-8")
    assert "release-runbook.md" in cursor_rule, (
        ".cursor/rules/030-git-workflow-management.mdc must link to "
        "docs/release-runbook.md"
    )
    # The rule must use the v-prefixed marker form, not the bare form.
    assert "release: vX.Y.Z" in cursor_rule
    assert "release: x.x.x" not in cursor_rule


def test_followup_readme_cleanup_step_has_continue_on_error() -> None:
    """release-publish.yml's PR-create step must tolerate the 'Actions cannot create PRs' policy."""
    src = (WORKFLOWS / "release-publish.yml").read_text(encoding="utf-8")
    # Find the followup-readme-cleanup job block, then assert that
    # continue-on-error: true appears under the create-PR step within it.
    job_match = re.search(
        r"followup-readme-cleanup:.*?(?=\n  [a-z_]|\Z)",
        src,
        re.DOTALL,
    )
    assert job_match, "followup-readme-cleanup job not found in release-publish.yml"
    block = job_match.group(0)
    assert "continue-on-error: true" in block, (
        "followup-readme-cleanup must mark the PR-create step "
        "continue-on-error so a blocked Actions-create-PRs setting "
        "does not red the whole release run"
    )
    assert "GITHUB_STEP_SUMMARY" in block, (
        "followup-readme-cleanup must include a step-summary fallback "
        "that prints the gh pr create command when the auto-create fails"
    )


def test_tag_main_commit_retries_on_no_pr_found() -> None:
    """tag-main-commit must retry the PR association lookup before failing."""
    src = (WORKFLOWS / "main-release-tag-gate.yml").read_text(encoding="utf-8")
    job_match = re.search(
        r"tag-main-commit:.*?(?=\n  [a-z_]|\Z)",
        src,
        re.DOTALL,
    )
    assert job_match, "tag-main-commit job not found in main-release-tag-gate.yml"
    block = job_match.group(0)
    # Look for the retry loop and the sleep.
    assert "for (let attempt = 1; attempt <= 3" in block, (
        "tag-main-commit must retry the commit→PR API call up to 3 times"
    )
    assert "sleep(30000)" in block, (
        "tag-main-commit must sleep 30s between retry attempts"
    )


def test_pre_merge_version_check_job_exists() -> None:
    """main-release-tag-gate.yml must run check_release_version.py at PR time."""
    src = (WORKFLOWS / "main-release-tag-gate.yml").read_text(encoding="utf-8")
    assert "check-version-vs-marker:" in src, (
        "main-release-tag-gate.yml must have a check-version-vs-marker "
        "job that runs scripts/check_release_version.py against the PR "
        "head before merge"
    )
    assert "scripts/check_release_version.py" in src
    # Confirm the job is gated to PR events only (not push) and runs
    # after validate-release-intent so the version is well-formed.
    job_match = re.search(
        r"check-version-vs-marker:.*?(?=\n  [a-z_]|\Z)",
        src,
        re.DOTALL,
    )
    assert job_match
    block = job_match.group(0)
    assert "if: github.event_name == 'pull_request'" in block
    assert "needs: [validate-release-intent]" in block


@pytest.mark.parametrize(
    "version,expect_target",
    [
        ("0.2.0", "PyPI"),
        ("0.2.0-rc1", "TestPyPI"),
        ("1.0.0", "PyPI"),
        ("1.0.0-beta1", "TestPyPI"),
    ],
)
def test_release_target_routing_documented(version: str, expect_target: str) -> None:
    """The RC vs final routing is documented in the runbook."""
    body = (REPO / "docs" / "release-runbook.md").read_text(encoding="utf-8")
    if expect_target == "TestPyPI":
        assert "TestPyPI" in body
        # The runbook must call out that prereleases route to TestPyPI.
        assert re.search(r"prereleas.*TestPyPI|TestPyPI.*prereleas", body, re.IGNORECASE)
    else:
        assert "PyPI" in body
        assert re.search(r"final.*PyPI|PyPI.*final", body, re.IGNORECASE)
