"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import subprocess

def key(tmp_path: Path, name: str) -> tuple[Path, str]:
    """Shared test helper."""
    key = tmp_path / f"{name}_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, (tmp_path / f"{name}_key.pub").read_text(encoding="utf-8").strip()
