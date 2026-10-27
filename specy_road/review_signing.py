"""Sign and verify review records with SSH keys (slice 6).

A review record is a file, and anything with write access to ``work/`` can
produce one naming any rostered reviewer; the gate cannot tell "Opus reviewed
this" from "the executor wrote a file saying Opus reviewed this". Signing
closes that gap: a roster entry carries a ``public_key`` (an OpenSSH public
key line), the reviewer signs its record with the matching private key, and
with ``policy.signed_reviews: true`` the gate counts only records whose
signature verifies. The boundary becomes the key: the executor's process
must not hold a reviewer's private key, which is a deployment line the team
controls rather than a file permission it cannot.

OpenSSH signatures (``ssh-keygen -Y sign`` / ``-Y verify``, OpenSSH 8.1+)
rather than GPG or a Python library: every reviewer identity already has,
or can make, an SSH key, and the toolkit gains no dependency. The namespace
``specy-road-review`` keeps a signature made for anything else from being
replayed here.

What is signed is the canonical form of the reviewer-authored front matter:
every field except ``signature`` itself and the two ``review record`` writes
afterwards (``family``, ``independence``). Canonical means JSON with sorted
keys and no whitespace, so the same record always signs the same bytes.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

NAMESPACE = "specy-road-review"
UNSIGNED_KEYS = frozenset({"signature", "family", "independence"})


class SigningError(Exception):
    """Signing or verifying could not run (missing tool, bad key, bad input)."""


def canonical_bytes(data: dict[str, Any]) -> bytes:
    body = {k: v for k, v in data.items() if k not in UNSIGNED_KEYS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _keygen() -> str:
    path = shutil.which("ssh-keygen")
    if not path:
        raise SigningError("ssh-keygen not found; signing review records needs OpenSSH 8.1 or newer")
    return path


def sign(data: dict[str, Any], key_path: Path) -> str:
    """The record's signature as one base64 line (the ``.sig`` block, encoded)."""
    keygen = _keygen()
    if not Path(key_path).is_file():
        raise SigningError(f"signing key not found: {key_path}")
    with tempfile.TemporaryDirectory() as d:
        msg = Path(d) / "record"
        msg.write_bytes(canonical_bytes(data))
        r = subprocess.run(
            [keygen, "-Y", "sign", "-n", NAMESPACE, "-f", str(key_path), str(msg)],
            capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            raise SigningError(r.stderr.strip() or "ssh-keygen -Y sign failed")
        sig = (Path(d) / "record.sig").read_text(encoding="utf-8")
    return base64.b64encode(sig.encode("utf-8")).decode("ascii")


def verify(data: dict[str, Any], signature: str, public_key: str, identity: str) -> tuple[bool, str]:
    """``(ok, reason)``: whether ``signature`` is ``identity``'s signature over ``data``."""
    try:
        sig_text = base64.b64decode(signature, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False, "signature is not a base64-encoded SSH signature"
    parts = public_key.split()
    if len(parts) < 2:
        return False, "roster public_key is not an OpenSSH public key line"
    try:
        keygen = _keygen()
    except SigningError as e:
        return False, str(e)
    with tempfile.TemporaryDirectory() as d:
        sig = Path(d) / "record.sig"
        sig.write_text(sig_text, encoding="utf-8")
        allowed = Path(d) / "allowed_signers"
        allowed.write_text(f"{identity} {parts[0]} {parts[1]}\n", encoding="utf-8")
        r = subprocess.run(
            [keygen, "-Y", "verify", "-n", NAMESPACE, "-f", str(allowed), "-I", identity, "-s", str(sig)],
            input=canonical_bytes(data), capture_output=True, check=False,
        )
    if r.returncode == 0:
        return True, ""
    return False, (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["ssh-keygen -Y verify failed"])[-1]
