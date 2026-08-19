#!/usr/bin/env python3
"""Profile baseline AI-request footprint without changing request coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation
from trading_research.strategy_escalation_efficiency import _actionable_indices

SYSTEM_PROMPT = (
    "You are Nova's market event analyst. Analyze the event and return a structured advisory recommendation. "
    "Do not place trades, choose position size, alter risk gates, or claim profitability. "
    "ENTER/EXIT must name an approved strategy and exact strategy version when one is relevant."
)


def _user_prompt(decision, *, market_context: str = "", strategy_context: str = "") -> str:
    event = decision.market_decision
    # The bridge exposes a deterministic event object through market_decision.
    market_event = decision.market_decision
    return (
        f"Event type: {market_event.event_type}\n"
        f"Symbol: EURUSD\n"
        f"Timeframe: 15m\n"
        f"Timestamp: {decision.strategy_hint.timestamp.isoformat() if hasattr(decision.strategy_hint, 'timestamp') else ''}\n"
        f"Price: {getattr(market_event, 'price', '')}\n"
        f"Change bps: {getattr(market_event, 'change_bps', None)}\n"
        f"Spread bps: {getattr(market_event, 'spread_bps', None)}\n"
        f"Reason: {decision.reason}\n\n"
        f"Market context:\n{market_context or 'none'}\n\n"
        f"Approved-strategy context:\n{strategy_context or 'none'}"
    )


def _fallback_event_text(decision) -> str:
    """Build a stable replay footprint from fields guaranteed by the escalation decision."""
    hint = decision.strategy_hint
    return (
        f"Index: {decision.index}\n"
        f"Reason: {decision.reason}\n"
        f"Strategy tier: {hint.confidence_tier}\n"
        f"Strategy reason: {hint.reason}\n"
        f"Momentum bps: {hint.momentum_bps:.4f}\n"
        f"SMA gap bps: {hint.sma_gap_bps:.4f}\n"
        f"Setup score: {hint.setup_score:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    args = parser.parse_args()

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = [d for d in decisions if d.request_ai or d.strategy_hint.request_ai]

    actionable = _actionable_indices(
        bars,
        future_bars=4,
        opportunity_move_bps=30.0,
        transaction_cost_bps_round_trip=4.0,
        fast_period=20,
        slow_period=50,
    )

    # This is intentionally a cost-only profile. It does not alter which bars
    # receive AI review. Token estimates are rough character/4 proxies, not
    # provider billing numbers, and no model-quality claim is made.
    event_lengths = [len(_fallback_event_text(d)) for d in baseline]
    system_len = len(SYSTEM_PROMPT)
    current_user_lengths = event_lengths
    full_lengths = [system_len + n for n in current_user_lengths]

    # A compact structured representation is a cost candidate only. It is
    # measured for wire-size comparison but is NOT substituted into Nova.
    compact_lengths = []
    for d in baseline:
        hint = d.strategy_hint
        compact = {
            "i": d.index,
            "r": d.reason,
            "tier": hint.confidence_tier,
            "mom": round(hint.momentum_bps, 4),
            "gap": round(hint.sma_gap_bps, 4),
            "score": round(hint.setup_score, 4),
        }
        compact_lengths.append(len(json.dumps(compact, separators=(",", ":"))))

    def summary(values: list[int]) -> dict[str, float | int]:
        ordered = sorted(values)
        p95_index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))) )
        p99_index = max(0, min(len(ordered) - 1, int(round(0.99 * (len(ordered) - 1)))) )
        return {
            "count": len(values),
            "total_chars": sum(values),
            "mean_chars": statistics.mean(values) if values else 0.0,
            "p50_chars": statistics.median(values) if values else 0.0,
            "p95_chars": ordered[p95_index] if ordered else 0,
            "p99_chars": ordered[p99_index] if ordered else 0,
            "max_chars": max(values) if values else 0,
            "estimated_tokens_char_div_4": sum(values) / 4.0,
        }

    current = summary(full_lengths)
    compact = summary([system_len + n for n in compact_lengths])
    estimated_savings = {
        "chars": current["total_chars"] - compact["total_chars"],
        "percent": (
            (current["total_chars"] - compact["total_chars"]) / current["total_chars"] * 100.0
            if current["total_chars"]
            else 0.0
        ),
    }

    payload = {
        "schema_version": 1,
        "dataset": args.dataset,
        "policy": "non_destructive_ai_request_cost_profile",
        "baseline_ai_review_bars": len(baseline),
        "baseline_unique_ai_review_bars": len({d.index for d in baseline}),
        "actionable_opportunities": len(actionable),
        "actionable_baseline_reviewed": len(actionable & {d.index for d in baseline}),
        "current_model_context": {
            "model": "openai/gpt-oss-120b",
            "temperature": 0.1,
            "response_format": "strict_json_schema",
        },
        "current_request_footprint": current,
        "compact_structured_wire_candidate": compact,
        "estimated_wire_size_savings_only": estimated_savings,
        "important_limitations": [
            "Token estimates use characters/4 as a rough proxy and are not provider billing measurements.",
            "The compact representation is a cost-only candidate and has not been tested for model-equivalence or decision quality.",
            "No baseline AI review bars are suppressed or removed by this tool.",
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
