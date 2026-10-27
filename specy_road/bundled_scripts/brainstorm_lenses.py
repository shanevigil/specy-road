"""Lenses, diversity operators and directions the diverge prompts draw from.

The research behind brainstorm v2 (``docs/design-notes/v0-3-1-brainstorm-v2.md``)
found that named creativity methods add little on their own, while cheap
prompt mechanics — personas, random constraints, analogies, low-typicality
sampling, regeneration against the visible pool — carry the measured gains.
So the lenses stay as *coverage* scaffolding and the operators are the
diversity engine; the allocation grid in round 1 crosses one with the other.
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

#: The diversity engine. Each cell of the allocation grid names one of these.
OPERATORS: tuple[tuple[str, str], ...] = (
    ("Ordinary personas", "Generate as three specific, ordinary people (a night-shift "
                          "support engineer, a procurement officer at a regulated buyer, a "
                          "first-week user) — not as a visionary."),
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

DIRECTIONS: tuple[str, ...] = (
    "user segments", "technical layers", "business model", "risk and compliance",
    "a competing team's PM, given the same frame",
)

PROFILES: dict[str, tuple[tuple[str, str], ...]] = {
    "product": PRODUCT_LENSES,
    "technical": TECHNICAL_LENSES,
}
DEFAULT_KINDS_BY_PROFILE = {"product": "feature", "technical": "refactor"}


def lenses_for(profile: str) -> tuple[tuple[str, str], ...]:
    return PROFILES.get(profile, PRODUCT_LENSES)
