#!/usr/bin/env python3
"""Bounded A/B equivalence test for current vs compact market prompts.

Final gate for prompt compaction. It never changes production behavior and
never suppresses AI reviews. It samples one AI-review decision per bar and
compares current vs compact prompts using identical model settings.

Environment:
    GROQ_API_KEY must be set.

Arguments:
    dataset output

Optional:
    --sample N   number of unique baseline review bars to compare (default: 8)
    --model NAME model to use for this experiment; production model is not changed

Deployment rule:
    Only an exact 100% match on material decision fields with 100% valid
    responses may produce "equivalent_candidate". Any material disagreement
    produces "not_equivalent". API/runtime failures produce "inconclusive".
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor, MarketEvent
from trading_research.market_reasoner import GroqMarketReasoner, MarketAnalysis, DEFAULT_MODEL
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation

SYSTEM_PROMPT = (
    "You are Nova's market event analyst. Analyze the event and return a structured advisory recommendation. "
    "Do not place trades, choose position size, alter risk gates, or claim profitability. "
    "ENTER/EXIT must name an approved strategy and exact strategy version when one is relevant."
)


def _decision_key(analysis: MarketAnalysis) -> tuple:
    rec = analysis.recommendation
    if rec is None:
        return (analysis.assessment, analysis.urgency, tuple(analysis.relevant_strategies), None)
    return (
        analysis.assessment,
        analysis.urgency,
        tuple(analysis.relevant_strategies),
        (rec.action, rec.strategy_name, rec.strategy_version, rec.urgency),
    )


def _compact_context(decision) -> str:
    hint = decision.strategy_hint
    payload = {
        "index": decision.index,
        "reason": decision.reason,
        "strategy_tier": hint.confidence_tier,
        "strategy_reason": hint.reason,
        "momentum_bps": round(hint.momentum_bps, 4),
        "sma_gap_bps": round(hint.sma_gap_bps, 4),
        "setup_score": round(hint.setup_score, 4),
    }
    return json.dumps(payload, separators=(",", ":"))


def _full_context(decision, event: MarketEvent) -> tuple[str, str]:
    user = (
        f"Event type: {event.event_type}\n"
        f"Symbol: {event.symbol}\n"
        f"Timeframe: {event.timeframe}\n"
        f"Timestamp: {event.timestamp.isoformat()}\n"
        f"Price: {event.price}\n"
        f"Change bps: {event.change_bps}\n"
        f"Spread bps: {event.spread_bps}\n"
        f"Reason: {decision.reason}\n\n"
        "Market context:\nnone\n\n"
        "Approved-strategy context:\nnone"
    )
    return SYSTEM_PROMPT, user


def _compact_contexts(decision, event: MarketEvent) -> tuple[str, str]:
    user = (
        f"Event type: {event.event_type}\n"
        f"Symbol: {event.symbol}\n"
        f"Timeframe: {event.timeframe}\n"
        f"Timestamp: {event.timestamp.isoformat()}\n"
        f"Price: {event.price}\n"
        f"Change bps: {event.change_bps}\n"
        f"Spread bps: {event.spread_bps}\n"
        f"Reason: {decision.reason}\n\n"
        f"Compact decision-time context:\n{_compact_context(decision)}"
    )
    return SYSTEM_PROMPT, user


def _call(reasoner: GroqMarketReasoner, system_prompt: str, user_prompt: str) -> MarketAnalysis:
    payload = {
        "model": reasoner.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "nova_market_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "assessment": {"type": "string", "enum": ["NO_ACTION", "WATCH", "SETUP", "RISK"]},
                        "rationale": {"type": "string"},
                        "relevant_strategies": {"type": "array", "items": {"type": "string"}},
                        "urgency": {"type": "string", "enum": ["NORMAL", "ELEVATED", "CRITICAL"]},
                        "recommendation": {
                            "type": ["object", "null"],
                            "properties": {
                                "action": {"type": "string", "enum": ["NO_ACTION", "WATCH", "ENTER", "EXIT"]},
                                "strategy_name": {"type": ["string", "null"]},
                                "strategy_version": {"type": ["string", "null"]},
                                "rationale": {"type": "string"},
                                "urgency": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                                "confidence": {"type": "number"},
                            },
                            "required": ["action", "strategy_name", "strategy_version", "rationale", "urgency", "confidence"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["assessment", "rationale", "relevant_strategies", "urgency", "recommendation"],
                    "additionalProperties": False,
                },
            },
        },
    }
    response = reasoner._transport(payload)
    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)
    recommendation_payload = data.get("recommendation")
    from trading_research.decision_contract import AIRecommendation
    recommendation = (
        AIRecommendation(
            action=str(recommendation_payload["action"]),
            strategy_name=recommendation_payload["strategy_name"],
            strategy_version=recommendation_payload["strategy_version"],
            rationale=str(recommendation_payload["rationale"]),
            urgency=str(recommendation_payload["urgency"]),
            confidence=float(recommendation_payload["confidence"]),
        ) if recommendation_payload is not None else None
    )
    analysis = MarketAnalysis(
        assessment=str(data["assessment"]),
        rationale=str(data["rationale"]),
        relevant_strategies=tuple(str(x) for x in data["relevant_strategies"]),
        urgency=str(data["urgency"]),
        recommendation=recommendation,
    )
    analysis.validate()
    return analysis


def _unique_bar_sample(decisions, sample_size: int):
    by_index = defaultdict(list)
    for d in decisions:
        if d.request_ai or d.strategy_hint.request_ai:
            by_index[d.index].append(d)
    selected = []
    for index in sorted(by_index):
        selected.append(by_index[index][0])
        if len(selected) >= sample_size:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--sample", type=int, default=8)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required for the equivalence experiment")

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    ai_indices = {d.index for d in decisions if d.request_ai or d.strategy_hint.request_ai}
    sample = _unique_bar_sample(decisions, min(args.sample, len(ai_indices)))

    bar_index_by_timestamp = {bar.timestamp: index for index, bar in enumerate(bars)}
    event_by_index = {
        bar_index_by_timestamp[event.timestamp]: event
        for event in events
        if event.timestamp in bar_index_by_timestamp
    }

    print(f"bounded equivalence: {len(sample)} unique bars / {len(sample) * 2} AI calls", flush=True)
    print(f"model: {args.model}", flush=True)
    reasoner = GroqMarketReasoner(api_key, model=args.model)

    comparisons = []
    errors = []
    current_chars = 0
    compact_chars = 0
    for position, d in enumerate(sample, start=1):
        event = event_by_index.get(d.index)
        if event is None:
            errors.append({"index": d.index, "error": "event_not_found"})
            print(f"[{position}/{len(sample)}] index={d.index}: event not found", flush=True)
            continue
        try:
            fs, fu = _full_context(d, event)
            cs, cu = _compact_contexts(d, event)
            current_chars += len(fs) + len(fu)
            compact_chars += len(cs) + len(cu)
            print(f"[{position}/{len(sample)}] index={d.index}: full", flush=True)
            full = _call(reasoner, fs, fu)
            print(f"[{position}/{len(sample)}] index={d.index}: compact", flush=True)
            compact = _call(reasoner, cs, cu)
            match = _decision_key(full) == _decision_key(compact)
            comparisons.append({
                "index": d.index,
                "full": _decision_key(full),
                "compact": _decision_key(compact),
                "match": match,
                "confidence_full": full.recommendation.confidence if full.recommendation else None,
                "confidence_compact": compact.recommendation.confidence if compact.recommendation else None,
            })
            print(f"[{position}/{len(sample)}] index={d.index}: {'MATCH' if match else 'MISMATCH'}", flush=True)
        except Exception as exc:
            errors.append({"index": d.index, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{position}/{len(sample)}] index={d.index}: ERROR {type(exc).__name__}: {exc}", flush=True)

    matches = sum(1 for c in comparisons if c["match"])
    valid = len(comparisons) == len(sample) and not errors
    agreement = matches / len(comparisons) if comparisons else 0.0
    savings = ((current_chars - compact_chars) / current_chars * 100.0) if current_chars else 0.0

    if not valid:
        status = "inconclusive"
    elif agreement == 1.0:
        status = "equivalent_candidate"
    else:
        status = "not_equivalent"

    payload = {
        "schema_version": 3,
        "policy": "bounded_compact_prompt_equivalence",
        "dataset": args.dataset,
        "sample_requested": args.sample,
        "sample_tested": len(sample),
        "sample_unique_bars": len({d.index for d in sample}),
        "current_model": args.model,
        "temperature": 0.1,
        "coverage_unchanged": True,
        "comparisons": comparisons,
        "errors": errors,
        "agreement": {
            "exact_material_decision_agreement": agreement,
            "matches": matches,
            "disagreements": len(comparisons) - matches,
            "valid_responses": len(comparisons),
        },
        "wire_size": {
            "current_chars": current_chars,
            "compact_chars": compact_chars,
            "estimated_percent_savings": savings,
        },
        "deployment_status": status,
        "decision_rule": "Only 100% material decision agreement with zero errors can be promoted; any disagreement rejects compaction; runtime/API errors are inconclusive.",
        "fallback_rule": "If not_equivalent, keep the current hard-coded/full request format and do not begin another prompt-optimization loop.",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
