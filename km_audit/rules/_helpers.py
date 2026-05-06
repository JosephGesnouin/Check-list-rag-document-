"""Shared helpers used across rule modules."""
from __future__ import annotations

from ..models import ParsedDoc


def truncate(s: str, n: int = 160) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def full_text(parsed: ParsedDoc) -> str:
    return "\n".join(parsed.text_blocks)
