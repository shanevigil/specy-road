---
# A reviewer copies this, fills it in from work/reviews/<NODE_ID>/PACKET.md only,
# and files it with:
#   specy-road review record <NODE_ID> --model <roster id> --verdict approve|block --file <this file>
# One `acceptance` entry per A# in the packet's brief. Approve may not list a
# failing item or required_changes; use block. Quote SHAs.
# With policy.signed_reviews, add --sign-key <path to your private key>; the
# roster entry for your --model must carry the matching public_key.
node_id: M1.1
model: your-roster-id
date: 2026-01-31
verdict: approve
commit: "the packet's 'Commit under review'"
acceptance: {A1: pass, A2: pass}
findings: {correctness: [], regression: [], boundary: [], test_integrity: []}
commands_rerun: []
# verify_pre_existing: [pytest -q tests/foo.py]   # optional: READY verifiers already failing on the integration branch
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
---
Free-form review notes.
