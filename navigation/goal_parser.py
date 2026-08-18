"""Deterministic extraction of generic open-navigation goal paths."""

from __future__ import annotations

import re
from typing import List


_OPEN_SPLIT = re.compile(
    r"\s*,?\s*(?:and|then)\s+(?:open|launch|start)\s+",
    flags=re.IGNORECASE,
)


def parse_open_path(goal: str) -> List[str]:
    """Extract sequential destinations without deciding how Android reaches them."""
    text = re.sub(r"\s+", " ", str(goal or "").strip())
    if not text:
        return []

    text = re.sub(
        r"^(?:please\s+)?(?:open|launch|start)\s+",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    parts = [part.strip(" ,") for part in _OPEN_SPLIT.split(text)]
    return [part for part in parts if part]
