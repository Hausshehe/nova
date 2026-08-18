"""Tiny deterministic strategy-rule DSL.

AI-generated text can only become executable research rules when it exactly
matches this allow-listed grammar. No Python, expressions, imports, or order
commands are accepted.
"""

from __future__ import annotations

import re
from typing import Sequence

from .data import Bar
from .experiment import Signal

_ENTRY_RE = re.compile(r"^close\s*>\s*prior_high\((\d+)\)$")
_EXIT_RE = re.compile(r"^close\s*<\s*prior_low\((\d+)\)$")


def _window_value(bars: Sequence[Bar], index: int, length: int, *, high: bool) -> float:
    if length < 1 or index < length:
        raise ValueError("rule window is not available")
    window = bars[index - length:index]
    values = [bar.high if high else bar.low for bar in window]
    return max(values) if high else min(values)


def compile_long_flat_rules(rules: dict[str, str]) -> Signal:
    """Compile one allow-listed entry/exit pair into a deterministic signal."""
    if set(rules) - {"entry", "exit", "filters", "costs"}:
        raise ValueError("unsupported rule fields")
    entry = rules.get("entry", "").strip()
    exit_rule = rules.get("exit", "").strip()
    filters = rules.get("filters", "none").strip().lower()
    if filters != "none":
        raise ValueError("unsupported filters; only 'none' is allowed")

    entry_match = _ENTRY_RE.fullmatch(entry)
    exit_match = _EXIT_RE.fullmatch(exit_rule)
    if not entry_match or not exit_match:
        raise ValueError(
            "unsupported rule DSL; expected 'close > prior_high(N)' and 'close < prior_low(N)'"
        )

    entry_n = int(entry_match.group(1))
    exit_n = int(exit_match.group(1))

    def signal(bars: Sequence[Bar], index: int) -> bool:
        if index < max(entry_n, exit_n):
            return False

        # Derive the desired long/flat state from the most recent transition.
        # This keeps the signal stateless and safe to reuse across train,
        # validation, and test segments.
        for cursor in range(index, max(entry_n, exit_n) - 1, -1):
            entry_hit = bars[cursor].close > _window_value(bars, cursor, entry_n, high=True)
            exit_hit = bars[cursor].close < _window_value(bars, cursor, exit_n, high=False)
            if exit_hit:
                return False
            if entry_hit:
                return True
        return False

    return signal
