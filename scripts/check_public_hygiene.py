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
``public:`` reads ``PUBLIC_IDENTITY_UNSET`` that check only reports. On a promotion range every newly reachable
commit is diffed too, side branches included and merges with ``-m``: an addition, modification or rename destination
at a denied path is refused, and a deletion passes. The script and the allow file are taken from the base commit
when that commit has them. A missing endpoint or any failed git query in the range exits 1 and says the history is
incomplete. ``--tree DIR`` checks an unpacked distribution (no git index; paths relative to that directory).
``--archive`` reports an sdist member relative to the distribution root: a directory entry (a trailing slash, or a
name another member sits under) is not a file, and that single top directory is then removed. A directory entry with
neither mark is kept, because it cannot be told from a file. A wheel is not stripped. ``--drop-denied`` removes every
tracked path the denylist refuses. ``--commit-msg FILE`` checks one message (the
commit-msg hook), without git's ``#`` comment lines and the diff under the scissors line.

The local list holds what must never be written into a tracked file: ``<kind>: <value>`` lines with kinds ``name``
(name tokens, the username), ``handle`` (the repo-owner GitHub handle, for the URL exemption), ``home`` (account-directory names
under ``~/``), ``machine`` (machine and apparmor profile names) and ``phrase``. It is read from
``<git common dir>/info/public-hygiene-local.txt`` (untracked, shared by linked worktrees) and from the
``PUBLIC_HYGIENE_LOCAL`` environment variable (the CI secret); with both empty those rules are skipped.

Usage: ``python scripts/check_public_hygiene.py [--root DIR] [--range A..B] [--promotion] [--archive FILE]... [--tree DIR]...``
or ``python scripts/check_public_hygiene.py --commit-msg FILE`` or ``python scripts/check_public_hygiene.py --drop-denied``
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

ALLOW_FILE = Path("scripts") / "public_hygiene_allow.txt"
LOCAL_FILE = Path("info") / "public-hygiene-local.txt"
LOCAL_ENV = "PUBLIC_HYGIENE_LOCAL"
ALLOW_ENV = "PUBLIC_HYGIENE_ALLOW"
FROM_BASE = "PUBLIC_HYGIENE_FROM_BASE"
UNSET = "PUBLIC_IDENTITY_UNSET"
_STATUS = re.compile(r"^([ACDMRTUX])\d*$")
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


class Rules(NamedTuple):
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


class _HistoryIncomplete(Exception):
    """A promotion range whose endpoints or git queries cannot be read."""


class _ScanFailed(Exception):
    """An archive or distribution tree that cannot be read."""


def _range_git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git " + " ".join(args)
        raise _HistoryIncomplete(detail)
    return result.stdout.decode("utf-8", "replace")


def _blob(root: Path, spec: str) -> str | None:
    """The file at ``commit:path``, or None when that path is not in the commit."""
    result = subprocess.run(["git", "show", spec], cwd=root, capture_output=True)
    if result.returncode == 0:
        return result.stdout.decode("utf-8", "replace")
    err = result.stderr.decode("utf-8", "replace")
    if "does not exist" in err or "exists on disk, but not in" in err:
        return None
    raise _HistoryIncomplete(err.strip() or spec)


def _incomplete(detail: str) -> int:
    print(f"history is incomplete: {detail}", file=sys.stderr)
    return 1


def load_rules(root: Path) -> Rules:
    allow_path = Path(os.environ[ALLOW_ENV]) if os.environ.get(ALLOW_ENV) else root / ALLOW_FILE
    allowed, bots, public = [], [], None
    for entry in _entries(allow_path.read_text(encoding="utf-8")):
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
        except OSError as exc:
            raise _ScanFailed(f"{name}: {exc}") from exc
        hits += text_hits(name, text, rules)
    return hits


def archive_members(path: Path) -> list[str]:
    """Member names of a wheel (zip) or an sdist (tar)."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return archive.namelist()
        with tarfile.open(path) as archive:
            return archive.getnames()
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise _ScanFailed(f"{path}: {exc}") from exc


def denied_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if PROCESS_PATH.search(p) and not SHIPPED_PATH.search(p)]


def promotion_path_hits(paths: list[str], archives: list[Path]) -> list[str]:
    hits = [f"{p}: process content path" for p in denied_paths(paths)]
    for archive in archives:
        sdist = not zipfile.is_zipfile(archive)
        members = [rel for _, rel in _relative_members(archive_members(archive), sdist=sdist)]
        hits += [f"{archive}: {member}: process content path" for member in denied_paths(members)]
    return hits


def missing_endpoints(root: Path, base: str, head: str) -> list[str]:
    return [end for end in (base, head) if subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{end}^{{commit}}"], cwd=root, capture_output=True).returncode]


def range_hits(root: Path, base: str, head: str, rules: Rules) -> list[str]:
    hits = []
    for record in _range_git(root, "log", "--format=%h%x00%B%x1e", f"{base}..{head}").split("\x1e"):
        sha, _, body = record.lstrip("\n").partition("\0")
        hits += text_hits(f"commit {sha}", body, rules, message=True) if sha else []
    return hits


def identity_hits(root: Path, base: str, head: str, rules: Rules) -> list[str]:
    """Author and committer addresses in the range that are neither the public identity nor a bot, once each."""
    trusted = rules.bots + ([rules.public] if rules.public else [])
    first: dict[tuple[str, str, str], str] = {}
    for line in _range_git(root, "log", "--format=%h%x00%an%x00%ae%x00%cn%x00%ce", f"{base}..{head}").splitlines():
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


def _diff_destinations(blob: str) -> list[tuple[str, str]]:
    """``(status, path)`` from ``git diff-tree -z``. A rename or copy yields its destination."""
    parts = blob.split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    found, i = [], 0
    while i < len(parts):
        match = _STATUS.match(parts[i])
        if not match:
            i += 1
            continue
        kind = match.group(1)
        width = 3 if kind in "RC" else 2
        if i + width > len(parts):
            raise _HistoryIncomplete("truncated diff")
        found.append((kind, parts[i + width - 1]))
        i += width
    return found


def changed_path_hits(root: Path, base: str, head: str) -> list[str]:
    """Denied additions, modifications and rename destinations in ``base..head``, deletions omitted."""
    hits = []
    for sha in _range_git(root, "rev-list", f"{base}..{head}").split():
        diff = _range_git(root, "diff-tree", "-m", "-r", "--name-status", "--find-renames", "-z", sha)
        seen = set()
        for kind, path in _diff_destinations(diff):
            if kind != "D" and path not in seen and denied_paths([path]):
                seen.add(path)
                hits.append(f"commit {sha}: {path}: process content path")
    return hits


def _file_members(names: list[str]) -> list[str]:
    """Stored file names. A directory ends with ``/`` or has another member under it."""
    return [
        name for name in names
        if name and not name.endswith("/") and not any(other.startswith(f"{name}/") for other in names if other)
    ]


def _relative_members(names: list[str], *, sdist: bool) -> list[tuple[str, str]]:
    """``(stored name, path relative to the distribution root)``. An sdist's single top directory is removed."""
    files = _file_members(names)
    tops = {name.split("/", 1)[0] for name in files}
    if sdist and len(tops) == 1 and all("/" in name for name in files):
        prefix = next(iter(tops)) + "/"
        return [(name, name[len(prefix):]) for name in files]
    return [(name, name) for name in files]


def _member_texts(path: Path, sdist: bool) -> list[tuple[str, str]]:
    """``(relative path, text)`` for each text member. A read failure is a scan failure."""
    pairs = []
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for stored, rel in _relative_members(archive.namelist(), sdist=False):
                    pairs.append((rel, archive.read(stored)))
        else:
            with tarfile.open(path) as archive:
                for stored, rel in _relative_members(archive.getnames(), sdist=sdist):
                    extracted = archive.extractfile(stored)
                    pairs.append((rel, b"" if extracted is None else extracted.read()))
    except (OSError, zipfile.BadZipFile, tarfile.TarError, KeyError) as exc:
        raise _ScanFailed(f"{path}: {exc}") from exc
    texts = []
    for rel, data in pairs:
        try:
            texts.append((rel, data.decode("utf-8")))
        except UnicodeDecodeError:
            continue
    return texts


def archive_promotion_hits(path: Path, rules: Rules) -> list[str]:
    """Denied member paths, and denied text in a member, for a wheel or an sdist."""
    try:
        sdist = not zipfile.is_zipfile(path)
        names = [rel for _, rel in _relative_members(archive_members(path), sdist=sdist)]
        hits = [f"{path}: {member}: process content path" for member in denied_paths(names)]
        for rel, text in _member_texts(path, sdist):
            hits += text_hits(f"{path}: {rel}", text, rules)
    except _ScanFailed as exc:
        return [str(exc)]
    return hits


def listed_files(root: Path) -> list[str]:
    """Files under ``root``, relative to it, without consulting a git index."""
    if not root.is_dir():
        raise _ScanFailed(f"{root}: not a directory")
    try:
        return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    except OSError as exc:
        raise _ScanFailed(f"{root}: {exc}") from exc


def _drop_denied(root: Path) -> int:
    """Remove denied tracked paths. ``-f`` is required after ``read-tree``: HEAD is still main, so the snapshot is staged."""
    paths = denied_paths(tracked(root))
    if not paths:
        return 0
    result = subprocess.run(
        ["git", "rm", "-r", "-f", "--ignore-unmatch", "-q", "--pathspec-from-file=-", "--pathspec-file-nul"],
        cwd=root, input="\0".join(paths).encode(), capture_output=True)
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        return result.returncode or 1
    return 0


def _write_allow(directory: Path, text: str | None) -> None:
    if text is None or os.environ.get(ALLOW_ENV):
        return
    path = directory / "public_hygiene_allow.txt"
    path.write_text(text, encoding="utf-8")
    os.environ[ALLOW_ENV] = str(path)


def _child_argv(root: Path, argv: list[str] | None) -> list[str]:
    child = list(sys.argv[1:] if argv is None else argv)
    if "--root" not in child:
        child = ["--root", str(root), *child]
    return child


def _delegate_base(root: Path, span: str, argv: list[str] | None) -> int | None:
    """Run the copy of this gate committed at the base, with that commit's allow file."""
    if os.environ.get(FROM_BASE):
        return None
    base, _, head = span.partition("..")
    missing = missing_endpoints(root, base, head)
    if missing:
        return _incomplete(f"range endpoint not found: {', '.join(map(repr, missing))}")
    script = _blob(root, f"{base}:scripts/check_public_hygiene.py")
    allow = _blob(root, f"{base}:{ALLOW_FILE.as_posix()}")
    if script is None:
        if allow is not None and not os.environ.get(ALLOW_ENV):
            directory = Path(tempfile.mkdtemp(prefix="hygiene-allow-"))
            _write_allow(directory, allow)
            os.environ["PUBLIC_HYGIENE_ALLOW_DIR"] = str(directory)
        return None
    directory = Path(tempfile.mkdtemp(prefix="hygiene-base-"))
    script_path = directory / "check_public_hygiene.py"
    script_path.write_text(script, encoding="utf-8")
    _write_allow(directory, allow)
    os.environ[FROM_BASE] = "1"
    try:
        spec = importlib.util.spec_from_file_location("hygiene_base_policy", script_path)
        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise _HistoryIncomplete(f"{base}: scripts/check_public_hygiene.py")
        spec.loader.exec_module(module)
        return module.main(_child_argv(root, argv))
    finally:
        os.environ.pop(FROM_BASE, None)
        os.environ.pop(ALLOW_ENV, None)
        shutil.rmtree(directory, ignore_errors=True)


def _tree_hits(trees: list[Path], rules: Rules, promotion: bool) -> list[str]:
    hits = []
    for tree in trees:
        paths = listed_files(tree)
        hits += file_hits(tree, paths, rules)
        if promotion:
            hits += [f"{path}: process content path" for path in denied_paths(paths)]
    return hits


def _span_hits(root: Path, span: str, rules: Rules, promotion: bool) -> list[str]:
    base, _, head = span.partition("..")
    missing = missing_endpoints(root, base, head)
    if missing:
        raise _HistoryIncomplete(f"range endpoint not found: {', '.join(map(repr, missing))}")
    hits = range_hits(root, base, head, rules)
    if promotion:
        hits += identity_report(root, base, head, rules)
        hits += changed_path_hits(root, base, head)
    return hits


def _release_allow_dir() -> None:
    if os.environ.get(FROM_BASE):
        return
    os.environ.pop(ALLOW_ENV, None)
    directory = os.environ.pop("PUBLIC_HYGIENE_ALLOW_DIR", None)
    if directory:
        shutil.rmtree(directory, ignore_errors=True)


def _run(args: argparse.Namespace, argv: list[str] | None) -> int:
    if args.range and args.promotion:
        delegated = _delegate_base(args.root, args.range, argv)
        if delegated is not None:
            return delegated
    rules = load_rules(args.root)
    if args.commit_msg:
        text = clean_message(args.commit_msg.read_text(encoding="utf-8"))
        return _report(text_hits(str(args.commit_msg), text, rules, message=True))
    if args.tree:
        hits = _tree_hits(args.tree, rules, args.promotion)
    else:
        paths = tracked(args.root)
        hits = file_hits(args.root, paths, rules)
        if args.promotion:
            hits += promotion_path_hits(paths, args.archive)
    if args.range:
        hits += _span_hits(args.root, args.range, rules, args.promotion)
    return _report(hits)


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
                        help="add the path denylist and, over --range, history, identity and the base commit's policy")
    parser.add_argument("--archive", type=Path, action="append", default=[], metavar="FILE",
                        help="with --promotion, check member names; an sdist directory entry (a trailing slash, or a "
                             "name another member sits under) is not a file, and the single top directory is removed")
    parser.add_argument("--tree", type=Path, action="append", default=[], metavar="DIR",
                        help="with --promotion, check this unpacked tree instead of the git index")
    parser.add_argument("--drop-denied", action="store_true",
                        help="git rm every tracked path the promotion denylist refuses")
    parser.add_argument("--commit-msg", type=Path, metavar="FILE", help="check this commit message only")
    args = parser.parse_args(argv)
    if args.drop_denied:
        return _drop_denied(args.root)
    try:
        return _run(args, argv)
    except _HistoryIncomplete as exc:
        return _incomplete(str(exc))
    except _ScanFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        _release_allow_dir()


if __name__ == "__main__":
    sys.exit(main())
