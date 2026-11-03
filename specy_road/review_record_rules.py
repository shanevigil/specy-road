"""What a reviewer is told to probe, and the check ``review record`` makes on an approve (M11.75).

An evaluation of reviewer effectiveness found approving reviewers re-running only the executor's own
tests, reading loose acceptance text in the leaf's favour, and naming real defects in their notes as
"advisory" or "non-blocking" while approving. :data:`PROBE_RULES_LINES` goes into every reviewer prompt;
:func:`check_record` is the record check for ``specy-road review record``, which also refuses an approve whose
findings or notes name a defect with neither a ``required_changes`` entry nor a :data:`NOT_A_DEFECT` line.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
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
    f"that same line why it is not one, starting `{NOT_A_DEFECT}`. `review record` refuses an approve whose "
    "findings or notes call something advisory, non-blocking, minor, a nit, a bug or a defect without that "
    "line; text you quote in backticks or on a `>` line is not checked.",
    "",
]
# Words a reviewer uses for a defect it lets through. `defect` and `bug` count unless negated ("no defect").
_DEFECT = re.compile(r"\b(advisory|non-?blocking|not\s+blocking|nit(?:pick)?s?|minor|cosmetic|residual|latent|"
                     r"optional\s+fix|weak\s+assertions?|bugs?|defects?)\b", re.I)
_NEGATED = re.compile(r"\b(?:no|none|nothing|not\s+an?|without|zero|never)\s+(?:[\w'-]+\s+){0,3}$", re.I)
_CODE_SPAN = re.compile(r"`[^`]*`")


def defect_word(line: str) -> str | None:
    """The first word in ``line`` that names a defect, or ``None``; a line carrying :data:`NOT_A_DEFECT`,
    a heading, a ``>`` quote and code spans name none."""
    text = _CODE_SPAN.sub("", line).strip()
    if NOT_A_DEFECT in text.lower() or text.startswith(("#", ">")):
        return None
    for m in _DEFECT.finditer(text):
        if not _NEGATED.search(text[:m.start()]):
            return m.group(1)
    return None


def unexplained_defects(data: dict[str, Any], body: str) -> list[str]:
    """``<where> says "<word>"`` for each findings entry and notes line that names a defect without a
    :data:`NOT_A_DEFECT` line; fenced code in the notes is skipped."""
    out = []
    for key, items in (data.get("findings") or {}).items():
        for i, item in enumerate(items or []):
            word = defect_word(str(item))
            if word:
                out.append(f'findings.{key}[{i}] says "{word}"')
    fenced = False
    for n, line in enumerate(body.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        word = None if fenced else defect_word(line)
        if word:
            out.append(f'notes line {n} says "{word}"')
    return out


def approve_defect_problem(data: dict[str, Any], body: str) -> str | None:
    """Why an approve may not be filed as written, or ``None``."""
    if data.get("verdict") != "approve":
        return None
    named = unexplained_defects(data, body)
    if not named:
        return None
    return (f"verdict: approve, but {'; '.join(named)} with no required_changes entry and no "
            f"'{NOT_A_DEFECT}' line: list each defect under required_changes and block, or say on that line "
            f"why it is not one ('{NOT_A_DEFECT} <reason>')")


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
    why = approve_defect_problem(rec.data, rec.body)
    if why:
        return None, f"{ns.file}: {why}"
    return {"data": rec.data, "body": rec.body}, None
