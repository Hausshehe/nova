"""Finite research-universe definition for the broader trading campaign."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

ASSET_FAMILIES: dict[str, tuple[str, ...]] = {
    "FX_MAJOR": (
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "USDCAD",
        "USDCHF",
        "NZDUSD",
    ),
    "INDEX": ("US500", "NAS100", "US30"),
    "COMMODITY": ("XAUUSD", "XAGUSD", "WTI"),
}
TIMEFRAMES: tuple[str, ...] = ("1D", "4H")
HYPOTHESIS_FAMILIES: tuple[str, ...] = (
    "momentum_continuation",
    "mean_reversion",
    "breakout_volatility_expansion",
    "cross_market_relative_behavior",
)
MAX_CONTEXTS = 104


@dataclass(frozen=True)
class ResearchContext:
    asset_family: str
    instrument: str
    timeframe: str
    hypothesis_family: str



def all_instruments() -> tuple[tuple[str, str], ...]:
    return tuple(
        (family, instrument)
        for family, instruments in ASSET_FAMILIES.items()
        for instrument in instruments
    )


def build_research_universe() -> tuple[ResearchContext, ...]:
    contexts = tuple(
        ResearchContext(asset_family, instrument, timeframe, hypothesis_family)
        for (asset_family, instrument), timeframe, hypothesis_family in product(
            all_instruments(), TIMEFRAMES, HYPOTHESIS_FAMILIES
        )
    )
    if len(contexts) != MAX_CONTEXTS:
        raise AssertionError(
            f"research-universe size drifted: expected {MAX_CONTEXTS}, got {len(contexts)}"
        )
    return contexts


def validate_context(context: ResearchContext) -> None:
    if context.asset_family not in ASSET_FAMILIES:
        raise ValueError(f"unknown asset family: {context.asset_family}")
    if context.instrument not in ASSET_FAMILIES[context.asset_family]:
        raise ValueError(f"instrument is not valid for asset family: {context.instrument}")
    if context.timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported research timeframe: {context.timeframe}")
    if context.hypothesis_family not in HYPOTHESIS_FAMILIES:
        raise ValueError(f"unsupported hypothesis family: {context.hypothesis_family}")
