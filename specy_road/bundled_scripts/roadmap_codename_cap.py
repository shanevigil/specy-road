"""Codename length cap for title-derived slugs (M15.38)."""

from __future__ import annotations

CODENAME_MAX_CHARS = 64


def cap_codename_slug(slug: str, *, max_chars: int = CODENAME_MAX_CHARS) -> str:
    """Shorten a kebab slug on word boundaries; never leave a trailing ``-``."""
    s = (slug or "").strip("-")
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    parts = [p for p in s.split("-") if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:max_chars].rstrip("-")
    kept: list[str] = []
    used = 0
    for part in parts:
        extra = len(part) + (1 if kept else 0)
        if used + extra > max_chars:
            break
        kept.append(part)
        used += extra
    return "-".join(kept).rstrip("-") if kept else parts[0][:max_chars].rstrip("-")


def derived_codename_from_title(title: str, *, max_words: int | None = None) -> str:
    """Title slug capped at ``CODENAME_MAX_CHARS`` (add-node / heal / title sync)."""
    from specy_road.bundled_scripts.roadmap_edit_fields import title_to_codename

    return cap_codename_slug(title_to_codename(title, max_words=max_words))


def codename_length_error(codename: str) -> str | None:
    """One-line ``error:`` body when an explicit codename exceeds the cap."""
    n = len(codename)
    if n > CODENAME_MAX_CHARS:
        return (
            f"codename is {n} characters; the limit is {CODENAME_MAX_CHARS} "
            "(it names feature/rm-<codename> and the planning file)"
        )
    return None
