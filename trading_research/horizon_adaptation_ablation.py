from __future__ import annotations

from typing import Sequence

from .data import Bar
from .online_horizon_expert_ensemble import HORIZONS, evaluate_online_horizon_expert_ensemble

CONFIGURATIONS = {
    "fixed_2": (2,),
    "fixed_4": (4,),
    "fixed_8": (8,),
    "adaptive_2_4_8": HORIZONS,
}


def evaluate_horizon_adaptation_ablation(
    bars: Sequence[Bar],
    *,
    transaction_cost_bps: float = 4.0,
    half_life: float = 60.0,
    min_history: int = 120,
    folds: int = 4,
) -> dict[str, object]:
    results: dict[str, object] = {}
    for name, horizons in CONFIGURATIONS.items():
        results[name] = evaluate_online_horizon_expert_ensemble(
            bars,
            horizons=horizons,
            transaction_cost_bps=transaction_cost_bps,
            half_life=half_life,
            min_history=min_history,
            folds=folds,
        )
    return {
        "policy": "causal_horizon_adaptation_ablation",
        "configurations": list(CONFIGURATIONS),
        "selection_rule": "Fixed-horizon and adaptive-horizon configurations are evaluated independently; no future outcomes select a configuration.",
        "results": results,
        "causal_rule": "Each configuration uses only outcomes whose own horizons completed before the current decision; future outcomes are evaluation-only.",
    }
