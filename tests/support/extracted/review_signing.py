"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def _roster(opus_pub: str, human_pub: str | None = None, *, signed: bool = True) -> str:
    human = f"  - {{id: human, family: human, roles: [coordinator, reviewer], public_key: \"{human_pub}\"}}\n" if human_pub \
        else "  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
    return ("version: 1\nroster:\n" + human +
            f"  - {{id: opus, family: anthropic, roles: [reviewer], public_key: \"{opus_pub}\"}}\n"
            "  - {id: sol, family: openai, roles: [reviewer]}\n"
            f"policy: {{reviewers_required: 1, signed_reviews: {'true' if signed else 'false'}}}\n")
