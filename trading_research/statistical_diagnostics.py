"""Exploratory statistical diagnostics for frozen trading experiments.

These routines never select or tune a strategy. They quantify uncertainty in
already-frozen return streams. Because overlapping forecast returns are
serially dependent, a moving-block bootstrap is preferred to an IID bootstrap.
The output is explicitly diagnostic and must not be treated as proof of a
trading edge.
"""
from __future__ import annotations

from random import Random
from statistics import mean
from typing import Sequence


def moving_block_bootstrap_mean_ci(
    values: Sequence[float],
    *,
    block_length: int = 5,
    samples: int = 2000,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    """Estimate a moving-block bootstrap CI for the sample mean.

    The block preserves short-range temporal dependence. This is an
    uncertainty diagnostic for a frozen return stream, not a model-selection
    mechanism. A deterministic seed makes experiment output reproducible.
    """
    if not values:
        raise ValueError("values must not be empty")
    if block_length <= 0 or block_length > len(values):
        raise ValueError("block_length must be between 1 and len(values)")
    if samples <= 0:
        raise ValueError("samples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")

    n = len(values)
    starts = list(range(n - block_length + 1))
    rng = Random(seed)
    means: list[float] = []

    for _ in range(samples):
        draw: list[float] = []
        while len(draw) < n:
            start = rng.choice(starts)
            draw.extend(values[start : start + block_length])
        means.append(mean(draw[:n]))

    means.sort()
    alpha = 1.0 - confidence
    lower_index = int((alpha / 2.0) * (len(means) - 1))
    upper_index = int((1.0 - alpha / 2.0) * (len(means) - 1))
    return {
        "sample_mean": mean(values),
        "ci_lower": means[lower_index],
        "ci_upper": means[upper_index],
        "block_length": block_length,
        "samples": samples,
        "seed": seed,
        "confidence": confidence,
    }


def compare_frozen_streams(
    left: Sequence[float],
    right: Sequence[float],
    *,
    block_length: int = 5,
    samples: int = 2000,
    seed: int = 0,
) -> dict[str, object]:
    """Compare uncertainty of two already-frozen, non-overlapping streams."""
    if not left or not right:
        raise ValueError("both streams must contain values")
    return {
        "left": moving_block_bootstrap_mean_ci(
            left, block_length=min(block_length, len(left)), samples=samples, seed=seed
        ),
        "right": moving_block_bootstrap_mean_ci(
            right, block_length=min(block_length, len(right)), samples=samples, seed=seed + 1
        ),
        "difference_of_means": mean(left) - mean(right),
        "interpretation": "Exploratory uncertainty only; this comparison does not establish statistical significance or executable PnL.",
    }
