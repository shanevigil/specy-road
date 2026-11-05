"""What a reviewer is told to probe, and the check ``review record`` makes on an approve (M11.75).

An evaluation of reviewer effectiveness found approving reviewers re-running only the executor's own
tests, reading loose acceptance text in the leaf's favour, and naming real defects in their notes as
"advisory" or "non-blocking", or describing a crash, lost data or refused valid input, while approving.
:data:`PROBE_RULES_LINES` goes into every reviewer prompt; :func:`check_record` is the record check for
``specy-road review record``, which also refuses an approve with a findings entry, or notes that name a
defect or describe a concrete failure, with neither a ``required_changes`` entry nor a :data:`NOT_A_DEFECT` line,
and an approve with no ``acceptance`` entry for an unplanned test removal (:mod:`specy_road.integrity_removals`).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.integrity_removals import REQUIRED_HEADING, missing_removal_entries, target_unplanned_removals
from specy_road.review_files import HUMAN, load_review
from specy_road.review_target import ReviewTarget, milestone_open_problem, same_commit

NOT_A_DEFECT = "not a defect because"
PROBE_RULES_LINES = [
    "Probe the change yourself; the executor's checks show only what the executor thought to try:",
    "",
    "1. Run the tests that import each changed module, not only the executor's selection or the READY's "
    "verifiers (search the tests directory for the module's import name).",
    "2. For each changed public function, try at least one input that the diff's tests do not use, and report "
    "it, with what it returned, under `commands_rerun`.",
    "3. Fail an acceptance item whose observed behaviour differs from its text, even when the difference looks "
    "minor; do not read a loose criterion in the leaf's favour.",
    "4. List every defect your notes or findings describe under `required_changes` (and block), or explain on "
    f"that same line why it is not one, starting `{NOT_A_DEFECT}`. On an approve, `review record` treats every "
    "`findings` entry and every observation line of the notes as a possible defect, whatever its wording, and "
    f"refuses the record unless that line says `{NOT_A_DEFECT} <reason>`, the phrase standing on its own and "
    "outside backticks, with the reason after it. An observation line is any line of two "
    "words or more outside code spans, other than a heading, a `>` quote, fenced code, a table separator row or "
    "horizontal rule, or a bare acceptance result such as `A1: pass`; so write each observation with its reason "
    "on the same line, and quote text or test output in backticks, a `>` line or fenced code. One explanation "
    "covers one observation, the sentence or clause it ends or the one just before it, and that text may join a "
    "second observation, with a comma or a conjunction such as `and`, `but` or `while`, only when no joined part "
    "names a defect: parts that name none are one observation however they are joined. Give each observation its "
    "own explanation, and keep each reason to one clause that names no defect itself.",
    "",
]
# Executors once deleted unrelated docstrings and messages to stay under a line cap; reviewers caught it a round late.
# Moved here from role_prompt.py, which is at the file-limits cap, beside the other reviewer-only prompt lines.
REMOVED_TEXT_LINES = [
    "Also check the diff for docstrings, comments or messages removed or shortened that the leaf did not need to "
    "touch (often to fit a file-limits cap), and require their restoration under `required_changes`.",
    "",
]
# Words a reviewer uses for a defect it lets through, and wording that describes a concrete failure.
# Each counts unless negated ("no defect", "never crashes"); bare "fails" or "drops" usually describe intended
# behaviour (a refusal, a filter), so only a drop or loss of something a user keeps counts.
_KEPT = (r"(?:data|records?|reviews?|work|changes?|commits?|files?|messages?|events?|entr(?:y|ies)|input|output|"
         r"results?|state|edits?)")
_DEFECT = re.compile(
    r"\b(advisory|non-?blocking|not\s+blocking|nit(?:pick)?s?|minor|cosmetic|residual|latent|optional\s+fix|"
    r"weak\s+assertions?|bugs?|defects?|crash(?:es|ed|ing)?|hangs?|hung|deadlocks?|corrupt(?:s|ed|ion|ing)?|"
    r"data\s+loss|leaks?|leaking|infinite\s+loop|race\s+condition|(?:unhandled|uncaught)\s+(?:exception|error)s?|"
    r"traceback|incorrect(?:ly)?|"
    r"(?:drops?|dropped|dropping|loses?|losing|overwrites?|overwrote|overwriting)\s+"
    rf"(?:(?:the|a|an|its|their|this|that|any|every|all|some|user's)\s+)?(?:[\w'-]+\s+)?{_KEPT}|"
    r"(?:is|are|was|were|gets?|got)\s+(?:silently\s+)?(?:lost|dropped|corrupted|overwritten)|"
    r"silently\s+(?:drop|ignore|accept|lose|skip|swallow|fail|pass)\w*|"
    r"(?:returns?|gives?|prints?|reports?|writes?)\s+(?:the\s+|a\s+)?wrong|"
    r"wrong\s+(?:result|answer|value|output|path|commit|exit)s?|"
    # valid input refused, and a non-zero exit where success was due: "valid input raises ValueError",
    # "rejects a valid ledger", "fails on valid input", "exits 1 instead of filing the review"
    r"valid\s+[\w'-]+\s+(?:raises|fails|errors|crashes|is\s+rejected|is\s+refused)|"
    r"(?:rejects|refuses)\s+(?:a\s+|an\s+|the\s+)?valid|"
    r"(?:raises|fails|errors)\s+(?:[\w'-]+\s+){0,2}(?:on|for|with)\s+(?:a\s+|an\s+|the\s+)?valid|"
    r"exits?\s+(?:with\s+)?(?:code\s+)?(?:[1-9]\d*|non-?zero)(?=[^.;]*\binstead\s+of\b)|"
    # ordering and races: "the second call reads the registry before the first writes it", "a stale read"
    r"reads?\s+[^.;]*?\bbefore\s+[^.;]*?\b(?:writes?|wrote|is\s+written|commits?|flushes|finishes|lands)|"
    r"stale\s+reads?|reads?\s+(?:a\s+|the\s+)?stale|out\s+of\s+order|lost\s+updates?|toctou|time-of-check|"
    r"check-then-act)\b", re.I)
# A negation only negates when nothing but qualifiers stand between it and the word: "no other correctness
# defect" is negated, "no workaround for this bug" is not.
_QUALIFIER = (r"(?:other|more|new|real|known|actual|obvious|remaining|further|such|open|proven|significant|serious|"
              r"blocking|correctness|regression|boundary|functional|visible|user-visible|outstanding|additional|"
              r"reachable|concrete|demonstrated|longer)")
_NEGATED = re.compile(r"\b(?:no|none|nothing|not(?:\s+an?)?|\w+n't|cannot|without|zero|never|rather\s+than|"
                      rf"instead\s+of)\s+(?:{_QUALIFIER}\s+){{0,3}}$", re.I)
_CODE_SPAN = re.compile(r"`[^`]*`")
# The explanation marker: the whole phrase standing alone (not "xnot a defect becausey") and followed by a reason
# on the same line, outside code spans, which quote rather than explain. Only spaces and tabs may separate its
# words and the reason: a line break of any kind str.splitlines knows would put the reason on another line.
_EXPLAINED = re.compile(r"(?<![\w-])not[ \t]+a[ \t]+defect[ \t]+because[ \t]+"
                        r"[^\w\n\r\v\f\x1c-\x1e\x85\u2028\u2029]*\w", re.I)


def explained(text: str) -> bool:
    """``text`` carries a standalone :data:`NOT_A_DEFECT` followed by a reason on the same line, outside code
    spans."""
    return bool(_EXPLAINED.search(_CODE_SPAN.sub("", text)))


# Lines of approve notes that carry no observation: a bare acceptance result ("- **A1:** pass", "| A1 | pass |")
# and a table separator row or horizontal rule. Any other line of two words or more is an observation and needs a
# NOT_A_DEFECT reason.
_ACCEPTANCE_RESULT = re.compile(r"^[-*+|\s]*[*_]*A[1-9]\d*[*_\s]*[:|\u2014\u2013-]?[*_\s]*(?:pass|n/a)"
                                r"[*_\s.,;|]*$", re.I)
_RULE = re.compile(r"^[\s|:*_-]*$")
_WORD = re.compile(r"[A-Za-z][\w'-]*")


# A clause ends at ., !, ?, or ; before whitespace, except after a common abbreviation ("e.g. the lock").
_CLAUSE_END = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<!\bcf\.)(?<=[.!?;])\s+", re.I)


def _named_defect(text: str) -> str | None:
    for m in _DEFECT.finditer(text):
        if not _NEGATED.search(text[:m.start()]):
            return m.group(1)
    return None


def defect_word(line: str) -> str | None:
    """The first word in ``line`` that names a defect, or ``None``; a line carrying :data:`NOT_A_DEFECT`,
    a heading, a ``>`` quote and code spans name none."""
    text = _CODE_SPAN.sub("", line).strip()
    if explained(text) or text.startswith(("#", ">")):
        return None
    return _named_defect(text)


def _observation(clause: str) -> str | None:
    """Why one clause would need a reason: it names a defect, or it has two words or more and is not a bare
    acceptance result or a table separator row or horizontal rule."""
    word = _named_defect(clause)
    if word:
        return f'says "{word}"'
    if _ACCEPTANCE_RESULT.match(clause.strip()) or _RULE.match(clause) or len(_WORD.findall(clause)) < 2:
        return None
    return "is an observation"


# Inside the text one explanation covers, parts joined by a comma or a coordinating conjunction; a part opening
# with one of _CONTINUES carries on the same observation ("x accepts malformed input, so y reaches execution").
_PARTS = re.compile(r"\s*,\s*|\s+(?:and|but|while|whereas|although|though|yet|plus)\s+", re.I)
_CONTINUES = re.compile(r"(?:so|which|that|because|since|as|causing|meaning|thus|hence|therefore|then|when|if|"
                        r"unless|until|where|rather|instead|including|such|for|with|without|via|by|from|to|in|on|"
                        r"at|of|after|before|e\.g\.|i\.e\.)\b", re.I)


# Quoted text, which names rather than joins: a conjunction inside a double-quoted, single-quoted or backtick span is
# not a split point ("compares 'base and HEAD'"). A single quote opens and closes only beside a non-word character,
# so an apostrophe ("user's") is not one.
_QUOTED = re.compile(r"`[^`]*`|\"[^\"\n]*\"|(?<!\w)'[^'\n]*'(?!\w)")


def _parts(text: str) -> list[tuple[str, str]]:
    """``(joining word, part)`` for each non-empty part of ``text`` split by :data:`_PARTS`, outside quoted spans;
    the first part's joining word is empty and a comma's is ``,``."""
    spans = [m.span() for m in _QUOTED.finditer(text)]
    out, start, joiner = [], 0, ""
    for m in _PARTS.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        out.append((joiner, text[start:m.start()].strip()))
        joiner, start = m.group().strip() or ",", m.end()
    out.append((joiner, text[start:].strip()))
    return [(j, part) for j, part in out if part]


def _second_observation(text: str) -> str | None:
    """Why ``text``, which one explanation covers, holds more than one observation, or ``None``. It can only when
    some joined part names a defect: parts that name none are one observation, whatever joins them. Then a part
    counts when it names a defect, or has three words or more and does not carry on the part before it, and the
    first part counts from two words when a comma or "and" part names a defect ("X fails and Y crashes"). The
    answer names the word that joins the second observation to the first and quotes both parts."""
    parts = [(joiner, part, _named_defect(part)) for joiner, part in _parts(text)]
    if not any(word for _joiner, _part, word in parts):
        return None
    listed = any(word and joiner.lower() in (",", "and") for joiner, _part, word in parts)
    found = []   # (why, joining word, part)
    for i, (joiner, part, word) in enumerate(parts):
        if word:
            found.append((f'says "{word}"', joiner, part))
        elif i == 0 and len(_WORD.findall(part)) >= (2 if listed else 3):
            found.append(("is an observation", joiner, part))
        elif i and len(_WORD.findall(part)) >= 3 and not _CONTINUES.match(part):
            found.append(("is an observation", joiner, part))
    if len(found) < 2:
        return None
    why = next(f[0] for f in found if f[0].startswith("says"))
    (_, _, first), (_, joiner, second) = (f[:2] + (f[2].rstrip(".;:!? "),) for f in found[:2])
    gap = "" if joiner == "," else " "
    return f'{why}, two observations joined by "{joiner}": "{first}"{gap}{joiner} "{second}"'


def clause_problem(text: str) -> str | None:
    """Why ``text`` (a notes line or a findings entry, code spans ignored) is not fully explained, or ``None``.
    One explanation covers one observation: the clause it ends ("x, not a defect because y"), or, when the marker
    opens its clause, the one clause just before it ("x; not a defect because y", "x. Not a defect because y").
    Any other clause that would need a reason fails, so does a covered clause that joins a second observation to
    the first (:func:`_second_observation`), and so does a reason that itself names a defect."""
    pending = None   # (why, clause) for an observation no explanation has covered yet
    for clause in _CLAUSE_END.split(_CODE_SPAN.sub("", text).strip()):
        m = _EXPLAINED.search(clause)
        if not m:
            if pending:
                return pending[0]
            why = _observation(clause)
            pending = (why, clause) if why else None
            continue
        own = clause[:m.start()]
        if pending and _observation(own):   # this marker explains its own clause, not the last
            return pending[0]
        covered = own if _observation(own) or not pending else pending[1]
        pending = None
        why = _second_observation(covered)
        if why:
            return why
        word = _named_defect(clause[m.end() - 1:])   # the reason, from its first word character
        if word:
            return f'says "{word}" in its reason'
    return pending[0] if pending else None


def note_problem(line: str) -> str | None:
    """Why one line of approve notes needs a :data:`NOT_A_DEFECT` reason, or ``None``: ``says "<word>"`` when
    a clause names a defect, else ``is an observation`` when a clause has two words or more outside code spans
    and is not a bare acceptance result or a table separator row or horizontal rule (:func:`clause_problem`).
    Headings and ``>`` quotes are skipped."""
    text = _CODE_SPAN.sub("", line).strip()
    if text.startswith(("#", ">")):
        return None
    return clause_problem(text)


def offending_lines(data: dict[str, Any], body: str) -> list[tuple[str, str]]:
    """``(where and why, text)`` for each findings entry and notes line :func:`unexplained_defects` names, with
    the entry's or line's own text."""
    out = []
    for key, items in (data.get("findings") or {}).items():
        for i, item in enumerate(items or []):
            why = clause_problem(str(item)) or (None if explained(str(item)) else "is a finding")
            if why:
                out.append((f"findings.{key}[{i}] " + why.replace("is an observation", "is a finding"), str(item)))
    fenced = False
    for n, line in enumerate(body.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        why = None if fenced else note_problem(line)
        if why:
            out.append((f"notes line {n} {why}", line))
    return out


def unexplained_defects(data: dict[str, Any], body: str) -> list[str]:
    """``<where> says "<word>"`` for each findings entry and notes line that names a defect without a
    :data:`NOT_A_DEFECT` line; fenced code in the notes is skipped. A word list cannot catch every way of
    describing a defect, so every findings entry (``<where> is a finding``) and every observation line of the
    notes (``<where> is an observation``, :func:`note_problem`) without that line counts, whatever its wording.
    Each explanation covers one observation (:func:`clause_problem`)."""
    return [where for where, _text in offending_lines(data, body)]


# The rule an approve's refusal states, in one sentence.
NOT_A_DEFECT_RULE = (f"each line below has no required_changes entry and no '{NOT_A_DEFECT}' line, and on an "
                     "approve every findings entry and every observation line of the notes needs that line: say on "
                     f"it why it is not a defect ('{NOT_A_DEFECT} <reason>', one explanation per observation), or "
                     "list the defect under required_changes and block.")


def approve_defect_problem(data: dict[str, Any], body: str) -> str | None:
    """Why an approve may not be filed as written, or ``None``: the rule in one sentence, then each offending line
    with its number (or findings entry) and text."""
    if data.get("verdict") != "approve":
        return None
    named = offending_lines(data, body)
    if not named:
        return None
    return (f"verdict: approve refused: {NOT_A_DEFECT_RULE}\n"
            + "\n".join(f"  {where}: {text.strip()}" for where, text in named))


def check_record(ns: argparse.Namespace, root: Path, t: ReviewTarget) -> tuple[dict | None, str | None]:
    if ns.model == HUMAN or milestone_open_problem(t):   # a milestone with an open leaf takes no record yet
        return None, milestone_open_problem(t) or ("a human review is filed only by the interactive approve in "
                                                   "specy-road mark-implementation-reviewed, so an agent cannot file one")
    rec = load_review(Path(ns.file), acceptance_ids(t.node))
    if not rec.ok:
        return None, f"{ns.file}: " + "; ".join(rec.errors)
    for key, want in (("node_id", ns.node_id), ("model", ns.model), ("verdict", ns.verdict)):
        if rec.data.get(key) != want:
            return None, f"{ns.file}: {key} is {rec.data.get(key)!r}, the command says {want!r}"
    if not same_commit(root, rec.data["commit"], t.commit):
        return None, (f"the record reviews {rec.data['commit']}, but the commit under review is "
                      f"{t.commit} ({t.ref}). Re-review the current commit.")
    why = approve_defect_problem(rec.data, rec.body) or unplanned_removal_problem(root, t, rec.data)
    if why:
        return None, f"{ns.file}: {why}"
    return {"data": rec.data, "body": rec.body}, None


def unplanned_removal_problem(root: Path, t: ReviewTarget, data: dict[str, Any]) -> str | None:
    """Why an approve has no acceptance entry for an unplanned test removal, or ``None``; ``policy.integrity_gate``
    plays no part."""
    if data.get("verdict") != "approve":
        return None
    missing = missing_removal_entries(data.get("acceptance") or {}, target_unplanned_removals(root, t))
    if not missing:
        return None
    keys = ", ".join(f'"{line}": pass' for line in missing)
    return (f"verdict: approve without the packet's '{REQUIRED_HEADING}' entries: {'; '.join(missing)} "
            f"(not in {t.node_id}'s planned_test_changes). Add {keys} to acceptance if the acceptance and the "
            "diff justify each, or block with a required_changes entry")
