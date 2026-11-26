"""Helpers shared by tests that folded into more than one module."""

from __future__ import annotations




# --- F12 ------------------------------------------------------------------



def evidence_roster(
    opus_pub: str | None, human_pub: str | None = None, *, signed: bool = True,
) -> str:
    """One-reviewer roster text, with optional public keys and a signed-reviews flag."""
    human = (f"  - {{id: human, family: human, roles: [coordinator, reviewer], public_key: \"{human_pub}\"}}\n"
             if human_pub else "  - {id: human, family: human, roles: [coordinator, reviewer]}\n")
    opus = (f"  - {{id: opus, family: anthropic, roles: [reviewer], public_key: \"{opus_pub}\"}}\n"
            if opus_pub else "  - {id: opus, family: anthropic, roles: [reviewer]}\n")
    return ("version: 1\nroster:\n" + human + opus +
            f"policy: {{reviewers_required: 1, signed_reviews: {'true' if signed else 'false'}}}\n")
