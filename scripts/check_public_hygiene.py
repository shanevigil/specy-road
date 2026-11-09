#!/usr/bin/env python3
"""Fail when tracked files or commit messages carry personal data, one machine's setup or process content.

Each category is bounded so product paths and names pass:

- **Personal data:** an email address that ``scripts/public_hygiene_allow.txt`` does not list (an entry exempts only
  the address it matches, never its line); the local list's name tokens and username as whole words, which covers
  ``owner:`` values and ``<username>-s<digits>`` presence names. A ``github.com/<handle>`` URL is not a name hit,
  and a file name or decorator after an ``@`` (``x@AGENTS.team.md``, ``n@pytest.mark…``) is no address.
- **Machine setup:** a home directory (``/Users/<name>``, ``/home/<name>``, the ``-home-<name>-`` project-dir form
  Claude Code uses, ``C:\\Users\\<name>\\``), a harness temp dir (``/tmp/claude-<uid>``, ``/private/tmp/claude-<uid>``),
  a Mac hostname (``<host>-MacBook-Pro`` with ``.local``; a bare ``.local`` as in ``AGENTS.local.md`` is none), a home
  path into one of the local list's account directories (``~/.<tool>`` config paths pass), a home-prefixed conda or
  venv path, ``CLAUDE_CONFIG_DIR`` set to a path starting with ``/`` or ``~``, a literal number assigned to
  ``kernel.apparmor_restrict_unprivileged_userns``, and the local list's machine and apparmor profile names.
  Variable references and placeholders (``$X``, ``<n>``) are no literal values, and homes that name no person pass
  (``x``, ``<name>``, ``Shared``, ``runner``, ``linuxbrew``, Windows ``Public`` and ``Default``).
- **Process content:** the text denylist (research-report and Claude Code session mentions, the local list's
  phrases); in commit messages also mentions of ``sr/work``, ``sr/planning``, ``sr/roadmap`` and ``sr/tools``, which
  product text uses as project-root examples. Under ``--promotion``, the path denylist on tracked paths and
  ``--archive`` member names: ``sr/``, ``docs/design-notes/``, ``scripts/census/``, ``scripts/review_effort_study.py``,
  a ``research`` directory, a ``*-prompt.md`` or ``handoff-*`` file, except under ``specy_road/templates/`` and
  ``tests/parity/``.

Default mode scans tracked text files outside ``sr/`` (tracked there on the WIP line). ``--range A..B`` adds the
messages of ``git log A..B``; ``--promotion`` adds the path denylist and, over the range only, the identity check: an
author or committer address that is neither the allow file's ``public:`` entry nor a ``bot:`` entry. While
``public:`` reads ``PUBLIC_IDENTITY_UNSET`` that check only reports. ``--commit-msg FILE`` checks one message (the
commit-msg hook), without git's ``#`` comment lines and the diff under the scissors line.

The local list holds what must never be written into a tracked file: ``<kind>: <value>`` lines with kinds ``name``
(name tokens, the username), ``handle`` (the repo-owner GitHub handle, for the URL exemption), ``home`` (account-directory names
under ``~/``), ``machine`` (machine and apparmor profile names) and ``phrase``. It is read from
``<git common dir>/info/public-hygiene-local.txt`` (untracked, shared by linked worktrees) and from the
``PUBLIC_HYGIENE_LOCAL`` environment variable (the CI secret); with both empty those rules are skipped.

Usage: ``python scripts/check_public_hygiene.py [--root DIR] [--range A..B] [--promotion] [--archive FILE]...``
or ``python scripts/check_public_hygiene.py --commit-msg FILE``
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

ALLOW_FILE = Path("scripts") / "public_hygiene_allow.txt"
LOCAL_FILE = Path("info") / "public-hygiene-local.txt"
LOCAL_ENV = "PUBLIC_HYGIENE_LOCAL"
UNSET = "PUBLIC_IDENTITY_UNSET"
LOCAL_KINDS = ("name", "handle", "home", "machine", "phrase")

#: Placeholder, shared, system or CI-owned home directories that name no person.
_NO_PERSON = "x|Shared|runner|linuxbrew|Public|Default"
#: The name is exactly one of those: in a path a hyphen is part of the name (an ``x-user`` home is a person);
#: in an encoded project dir (``-home-x-repo``) the hyphen ends it.
_PATH_NAME = rf"(?!(?:{_NO_PERSON})(?![A-Za-z0-9._-])|<)[A-Za-z0-9._-]+"
_DIR_NAME = rf"(?!(?:{_NO_PERSON})(?![A-Za-z0-9._]))[A-Za-z0-9._]+"
_HOME = r"(?:~|\$HOME|\$\{HOME\})/"
_ALNUM_BEFORE, _ALNUM_AFTER = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"

MACHINE = re.compile(
    rf"/(?:Users|home)/{_PATH_NAME}"
    rf"|(?<![A-Za-z0-9])-(?:Users|home)-{_DIR_NAME}-"   # a project dir name, not prose
    rf"|[A-Za-z]:\\{{1,2}}(?i:users)\\{{1,2}}{_PATH_NAME}"
    r"|/(?:private/)?tmp/claude-\d"
    r"|-MacBook(?:-(?:Pro|Air))?(?:-\d+)?\.local\b"
    rf"|{_HOME}(?:(?:mini|ana)conda\d*|miniforge\d*|mambaforge|micromamba|\.conda/envs|\.virtualenvs|\.?venvs?)"
    rf"{_ALNUM_AFTER}"
    r"""|CLAUDE_CONFIG_DIR=["']?[/~]"""
    r"|kernel\.apparmor_restrict_unprivileged_userns\s*=\s*\d"
)
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![A-Za-z0-9-])")
_NOT_A_DOMAIN = re.compile(r"^pytest\.mark\b|\.(?:md|py|txt|json|ya?ml|toml|cfg|ini|sh|js|ts|html)$", re.I)
PROCESS_TEXT = re.compile(
    "|".join(map(re.escape, ("deep-research" + " report", "claude.ai/code/" + "session_", "Claude-" + "Session:"))),
    re.I,
)
SR_MENTION = re.compile(r"(?<![\w.-])sr/(?:work|planning|roadmap|tools)")
PROCESS_PATH = re.compile(
    r"(?:^|/)(?:sr/|docs/design-notes/|scripts/census/|research/|scripts/review_effort_study\.py$)"
    r"|(?:^|/)(?:[^/]*-prompt\.md|handoff-[^/]*)$"
)
SHIPPED_PATH = re.compile(r"(?:^|/)(?:specy_road/templates|tests/parity)/")
SCISSORS = "# ------------------------ >8 ------------------------"


@dataclass
class Rules:
    """The allow file's address patterns and every text rule, the local list's included."""

    allowed: list[re.Pattern[str]]
    bots: list[re.Pattern[str]]
    public: re.Pattern[str] | None   # None while the allow file holds the placeholder
    text: list[tuple[str, re.Pattern[str]]]
    handle_urls: re.Pattern[str] | None


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout
    return out.decode("utf-8", "replace")


def _entries(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _any(values: list[str], before: str = _ALNUM_BEFORE, after: str = _ALNUM_AFTER) -> re.Pattern[str] | None:
    return re.compile(f"{before}(?:{'|'.join(map(re.escape, values))}){after}", re.I) if values else None


def load_local(root: Path) -> dict[str, list[str]]:
    """The local list's values by kind, from the untracked file and the CI secret; a malformed line stops the run."""
    path = root / _git(root, "rev-parse", "--git-common-dir").strip() / LOCAL_FILE
    sources = {str(path): path.read_text(encoding="utf-8") if path.is_file() else "",
               LOCAL_ENV: os.environ.get(LOCAL_ENV, "")}
    local: dict[str, list[str]] = {kind: [] for kind in LOCAL_KINDS}
    for source, text in sources.items():
        for n, line in enumerate(text.splitlines(), 1):
            kind, _, value = (part.strip() for part in line.partition(":"))
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if kind not in local or not value:   # the line itself is never echoed: it may hold a secret
                raise SystemExit(f"{source}: line {n}: want `<kind>: <value>` with kind one of {', '.join(LOCAL_KINDS)}")
            local[kind].append(value)
    return local


def load_rules(root: Path) -> Rules:
    allowed, bots, public = [], [], None
    for entry in _entries((root / ALLOW_FILE).read_text(encoding="utf-8")):
        kind, sep, value = entry.partition(": ")
        kind, value = (kind, value) if sep else ("", entry)
        if value == UNSET:
            continue
        pattern = re.compile(re.escape(value).replace(r"\*", r"[^@\s]*"), re.I)
        allowed.append(pattern)
        bots += [pattern] if kind == "bot" else []
        public = pattern if kind == "public" else public
    local = load_local(root)
    text = [("machine setup", MACHINE), ("process content", PROCESS_TEXT)] + [
        (category, pattern) for category, pattern in (
            ("personal data", _any(local["name"])),
            ("machine setup", _any(local["home"], before=_HOME, after=r"(?![A-Za-z0-9._-])")),
            ("machine setup", _any(local["machine"])),
            ("process content", _any(local["phrase"], before="", after="")),
        ) if pattern
    ]
    return Rules(allowed, bots, public, text, _any(local["handle"], before=r"github\.com/", after=r"(?![A-Za-z0-9-])"))


def line_hits(line: str, rules: Rules) -> list[str]:
    """The categories ``line`` falls under; an address hit names the address."""
    found = [f"personal data ({m.group()})" for m in EMAIL.finditer(line)
             if not _NOT_A_DOMAIN.search(m.group(1)) and not any(p.fullmatch(m.group()) for p in rules.allowed)]
    if rules.handle_urls:
        line = rules.handle_urls.sub("github.com/", line)
    return found + [category for category, pattern in rules.text if pattern.search(line)]


def text_hits(where: str, text: str, rules: Rules, *, message: bool = False) -> list[str]:
    """``<where>:<line>: <categories>: <text>`` per hit line; a commit message also refuses ``sr/`` mentions."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        found = line_hits(line, rules) + (["process content"] if message and SR_MENTION.search(line) else [])
        if found:
            hits.append(f"{where}:{n}: {', '.join(dict.fromkeys(found))}: {line.strip()[:160]}")
    return hits


def clean_message(text: str) -> str:
    """The message git keeps: comment lines blanked (line numbers hold), nothing under the ``commit -v`` scissors."""
    return "\n".join("" if line.startswith("#") else line for line in text.partition(SCISSORS)[0].splitlines())


def tracked(root: Path) -> list[str]:
    return [name for name in _git(root, "ls-files", "-z").split("\0") if name]


def file_hits(root: Path, paths: list[str], rules: Rules) -> list[str]:
    hits = []
    for name in paths:
        if name.startswith("sr/"):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue   # binary
        hits += text_hits(name, text, rules)
    return hits


def archive_members(path: Path) -> list[str]:
    """Member names of a wheel (zip) or an sdist (tar)."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path) as archive:
        return archive.getnames()


def denied_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if PROCESS_PATH.search(p) and not SHIPPED_PATH.search(p)]


def promotion_path_hits(paths: list[str], archives: list[Path]) -> list[str]:
    hits = [f"{p}: process content path" for p in denied_paths(paths)]
    for archive in archives:
        hits += [f"{archive}: {m}: process content path" for m in denied_paths(archive_members(archive))]
    return hits


def missing_endpoints(root: Path, base: str, head: str) -> list[str]:
    return [end for end in (base, head) if subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{end}^{{commit}}"], cwd=root, capture_output=True).returncode]


def range_hits(root: Path, base: str, head: str, rules: Rules) -> list[str]:
    hits = []
    for record in _git(root, "log", "--format=%h%x00%B%x1e", f"{base}..{head}").split("\x1e"):
        sha, _, body = record.lstrip("\n").partition("\0")
        hits += text_hits(f"commit {sha}", body, rules, message=True) if sha else []
    return hits


def identity_hits(root: Path, base: str, head: str, rules: Rules) -> list[str]:
    """Author and committer addresses in the range that are neither the public identity nor a bot, once each."""
    trusted = rules.bots + ([rules.public] if rules.public else [])
    first: dict[tuple[str, str, str], str] = {}
    for line in _git(root, "log", "--format=%h%x00%an%x00%ae%x00%cn%x00%ce", f"{base}..{head}").splitlines():
        sha, author, author_email, committer, committer_email = line.split("\0")
        for who in (("author", author, author_email), ("committer", committer, committer_email)):
            if not any(p.fullmatch(who[2]) for p in trusted):
                first.setdefault(who, sha)
    return [f"commit {sha}: {role} {name} <{email}> is neither the public identity nor a bot"
            for (role, name, email), sha in first.items()]


def identity_report(root: Path, base: str, head: str, rules: Rules) -> list[str]:
    """The identity hits that fail the run: none while the public identity is the placeholder, which only reports."""
    hits = identity_hits(root, base, head, rules)
    if rules.public is None:
        for hit in hits:
            print(f"advisory (public identity unset): {hit}")
        return []
    return hits


def _report(hits: list[str]) -> int:
    for hit in hits:
        print(hit)
    if hits:
        print(f"{len(hits)} public-hygiene hit(s): personal data, machine setup or process content. Remove or reword "
              "them and resolve paths at run time; scripts/check_public_hygiene.py lists the rules.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--range", metavar="A..B", help="also check the messages of git log A..B")
    parser.add_argument("--promotion", action="store_true",
                        help="add the path denylist and, over --range, the author and committer identity check")
    parser.add_argument("--archive", type=Path, action="append", default=[], metavar="FILE",
                        help="with --promotion, also check a wheel's or sdist's member names")
    parser.add_argument("--commit-msg", type=Path, metavar="FILE", help="check this commit message only")
    args = parser.parse_args(argv)
    rules = load_rules(args.root)
    if args.commit_msg:
        text = clean_message(args.commit_msg.read_text(encoding="utf-8"))
        return _report(text_hits(str(args.commit_msg), text, rules, message=True))
    paths = tracked(args.root)
    hits = file_hits(args.root, paths, rules)
    if args.promotion:
        hits += promotion_path_hits(paths, args.archive)
    if args.range:
        base, _, head = args.range.partition("..")
        missing = missing_endpoints(args.root, base, head)
        if missing:
            print(f"range endpoint not found: {', '.join(map(repr, missing))}", file=sys.stderr)
            return 1
        hits += range_hits(args.root, base, head, rules)
        if args.promotion:
            hits += identity_report(args.root, base, head, rules)
    return _report(hits)


if __name__ == "__main__":
    sys.exit(main())
