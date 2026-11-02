"""Lenses, diversity operators and directions the diverge prompts draw from.

The research behind brainstorm v2 (``docs/design-notes/v0-3-1-brainstorm-v2.md``)
found that named creativity methods add little on their own, while cheap
prompt mechanics — personas, random constraints, analogies, low-typicality
sampling, regeneration against the visible pool — carry the measured gains.
So the lenses stay as *coverage* scaffolding and the operators are the
diversity engine; the allocation grid in round 1 crosses one with the other.
Personas and directions are drawn from the frame's ``served`` answer once it
is recorded, and the ``personal`` profile fits a tool with one author.
"""

from __future__ import annotations

PRODUCT_LENSES: tuple[tuple[str, str], ...] = (
    ("SCAMPER", "Substitute, Combine, Adapt, Modify, Put to another use, Eliminate, "
                "Reverse — run each verb against the product's existing surfaces."),
    ("Analogous domains", "How has a different industry solved the shape of this problem? "
                          "Logistics, games, banking, healthcare. Port the mechanism, not the feature."),
    ("Inversion", "What would make this dramatically worse for the user? Invert each answer "
                  "into something to build."),
    ("Pre-mortem", "It is a year from now and this area failed. Write the causes, then propose "
                   "the work that would have prevented each one."),
    ("Constraint removal", "Drop the hardest current constraint (budget, latency, headcount, a "
                           "vendor) and say what becomes possible."),
    ("10x / 0.1x", "What would this look like with ten times the users, and what would the "
                   "smallest useful version be that ships in a week?"),
    ("Jobs to be done", "What is the user hiring this product to do, in which situation, and "
                        "what do they do today instead?"),
)

TECHNICAL_LENSES: tuple[tuple[str, str], ...] = (
    ("Failure modes", "Which component fails first under load, bad input, partial outage, or a "
                      "wrong deploy? Propose the work that removes each."),
    ("Operability", "What is hard to observe, roll back, or run at 3 a.m.? Dashboards, "
                    "runbooks, feature flags, kill switches."),
    ("Migration paths", "Which upgrade, deprecation or schema change is coming, and what makes "
                        "it boring?"),
    ("Debt and leverage", "Which abstraction, if fixed once, removes a class of bugs or a "
                          "class of tickets?"),
    ("Dependency risk", "Which library, vendor, or API could change terms, break, or be "
                        "abandoned; what is the fallback?"),
    ("Platform leverage", "What would make three future features cheap: a primitive, a "
                          "pipeline, a contract?"),
    ("Security and compliance", "Which CVE class, data flow, or audit requirement is "
                                "unaddressed?"),
)

PERSONAL_LENSES: tuple[tuple[str, str], ...] = (
    ("Friction log", "What did the author do by hand this month that the tool should have "
                     "done? Each chore is a candidate."),
    ("Future self", "Six months from now the author has forgotten how this works. What is "
                    "opaque, fragile, or undocumented to them?"),
    ("Inversion", "What would make this dramatically worse to use every day? Invert each "
                  "answer into something to build."),
    ("Delete before adding", "Which feature, option or dependency costs more to maintain than "
                             "it gives back? Propose removing it."),
    ("One evening", "What is the smallest change that ships in one sitting and is still "
                    "worth having?"),
    ("Analogous tools", "How do other people's tools of the same shape — dotfiles, editors, "
                        "scripts, notebooks — solve this? Port the mechanism, not the feature."),
    ("Jobs to be done", "What does the author reach for this tool to do, in which situation, "
                        "and what do they do when it is not there?"),
)

#: Who the personas operator imagines when the frame records no ``served`` answer.
_DEFAULT_PERSONAS = {
    "product": "a night-shift support engineer, a procurement officer at a regulated buyer, "
               "a first-week user",
    "technical": "the on-call engineer at 3 a.m., the developer onboarding next month, the "
                 "maintainer of a service that depends on this one",
    "personal": "the author on a tired evening, the author six months from now who has "
                "forgotten how it works, one friend who borrows the tool",
}

_PRODUCT_DIRECTIONS = ("user segments", "technical layers", "business model",
                       "risk and compliance", "a competing team's PM, given the same frame")

#: The ``served`` answer stands in for "user segments" when the frame records one.
_DIRECTIONS = {
    "product": _PRODUCT_DIRECTIONS,
    "technical": _PRODUCT_DIRECTIONS,
    "personal": ("daily use", "setup and maintenance", "the author's future self",
                 "technical layers", "someone else's tool of the same kind"),
}

_OTHER_OPERATORS: tuple[tuple[str, str], ...] = (
    ("Random constraints", "Impose a meaningful constraint that is not currently true (no "
                           "network, one engineer, must work on a phone, must be free) and "
                           "design inside it."),
    ("Analogical transfer", "Take the structure of a solution from an unrelated domain and map "
                            "it element by element onto this problem."),
    ("Low typicality", "List candidate ideas with your estimate of the probability a typical "
                       "PM would propose each; keep only those under 0.2."),
    ("Unoccupied regions", "Name the regions of the solution space the pool so far has not "
                           "touched, then put one idea in each."),
)

PROFILES: dict[str, tuple[tuple[str, str], ...]] = {
    "product": PRODUCT_LENSES,
    "technical": TECHNICAL_LENSES,
    "personal": PERSONAL_LENSES,
}
DEFAULT_KINDS_BY_PROFILE = {"product": "feature", "technical": "refactor", "personal": "feature"}


def lenses_for(profile: str) -> tuple[tuple[str, str], ...]:
    return PROFILES.get(profile, PRODUCT_LENSES)


def served_answer(frame: dict[str, str]) -> str:
    """The frame's ``served`` answer without its ``assumed:`` marker, or ``""``."""
    text = (frame.get("served") or "").strip()
    if text.lower().startswith("assumed:"):
        text = text[len("assumed:"):].strip()
    return text


def operators_for(profile: str, served: str = "") -> tuple[tuple[str, str], ...]:
    """The diversity engine; each cell of the allocation grid names one of these.

    The personas come from who the frame says is served, so a single-author
    tool is not brainstormed by a procurement officer.
    """
    if served:
        people = (f"Generate as three specific, ordinary people drawn from who the frame "
                  f"says is served — {served} — each in a concrete situation; not as a "
                  "visionary, and not as anyone the frame says is not served.")
    else:
        people = (f"Generate as three specific, ordinary people "
                  f"({_DEFAULT_PERSONAS.get(profile, _DEFAULT_PERSONAS['product'])}) — "
                  "not as a visionary.")
    return (("Ordinary personas", people), *_OTHER_OPERATORS)


def directions_for(profile: str, served: str = "") -> tuple[str, ...]:
    directions = _DIRECTIONS.get(profile, _DIRECTIONS["product"])
    if served and directions[0] == "user segments":
        return (f"segments of who is served ({served})", *directions[1:])
    return directions


#: The product profile with no frame — what the prompts showed before profiles
#: drew their personas and directions from the frame.
OPERATORS = operators_for("product")
DIRECTIONS = directions_for("product")
