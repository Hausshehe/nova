#!/usr/bin/env python3
"""Bounded A/B equivalence test for current vs compact market prompts.

This is the final gate for prompt compaction. It never changes production
behavior and never suppresses AI reviews. A stratified deterministic sample
is evaluated through the existing Groq reasoner using identical model,
temperature, and response schema settings.

Environment:
    GROQ_API_KEY must be set.

Arguments:
    dataset output

Optional:
    --sample N   number of baseline review bars to compare (default: 32)

Deployment rule:
    Only an exact 100% match on material decision fields with 100% valid
    responses may produce "equivalent_candidate". Any material disagreement
    produces "not_equivalent". API/runtime failures produce "inconclusive".
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
import sys
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.data import load_csv
from trading_research.market_monitor import MarketMonitor, MarketEvent
from trading_research.market_reasoner import GroqMarketReasoner, MarketAnalysis, DEFAULT_MODEL
from trading_research.strategy_escalation_bridge import evaluate_strategy_escalation
from trading_research.strategy_escalation_efficiency import _actionable_indices

SYSTEM_PROMPT = (
    "You are Nova's market event analyst. Analyze the event and return a structured advisory recommendation. "
    "Do not place trades, choose position size, alter risk gates, or claim profitability. "
    "ENTER/EXIT must name an approved strategy and exact strategy version when one is relevant."
)


def _decision_key(analysis: MarketAnalysis) -> tuple:
    rec = analysis.recommendation
    if rec is None:
        return (
            analysis.assessment,
            analysis.urgency,
            tuple(analysis.relevant_strategies),
            None,
        )
    return (
        analysis.assessment,
        analysis.urgency,
        tuple(analysis.relevant_strategies),
        (
            rec.action,
            rec.strategy_name,
            rec.strategy_version,
            rec.urgency,
        ),
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


def _make_transport(reasoner: GroqMarketReasoner):
    return reasoner._transport


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


def _stratified_sample(decisions, sample_size: int):
    groups = defaultdict(list)
    for d in decisions:
        groups[d.strategy_hint.confidence_tier].append(d)
    tiers = sorted(groups)
    selected = []
    if sample_size <= 0:
        return selected
    while len(selected) < sample_size and any(groups.values()):
        progressed = False
        for tier in tiers:
            if groups[tier]:
                selected.append(groups[tier].pop(0))
                progressed = True
                if len(selected) >= sample_size:
                    break
        if not progressed:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--sample", type=int, default=32)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required for the equivalence experiment")

    bars = tuple(load_csv(args.dataset))
    events = MarketMonitor().observe_history("EURUSD", "15m", bars)
    decisions = evaluate_strategy_escalation(bars, events)
    baseline = [d for d in decisions if d.request_ai or d.strategy_hint.request_ai]
    sample = _stratified_sample(baseline, min(args.sample, len(baseline)))
    by_timestamp = {bar.timestamp: bar for bar in bars}
    reasoner = GroqMarketReasoner(api_key, model=DEFAULT_MODEL, temperature=0.1)

    comparisons = []
    errors = []
    current_chars = 0
    compact_chars = 0
    for d in sample:
        event = next((e for e in events if e.timestamp == by_timestamp[d.index].timestamp), None)
        if event is None:
            errors.append({"index": d.index, "error": "event_not_found"})
            continue
        try:
            fs, fu = _full_context(d, event)
            cs, cu = _compact_contexts(d, event)
            current_chars += len(fs) + len(fu)
            compact_chars += len(cs) + len(cu)
            full = _call(reasoner, fs, fu)
            compact = _call(reasoner, cs, cu)
            comparisons.append({
                "index": d.index,
                "full": _decision_key(full),
                "compact": _decision_key(compact),
                "match": _decision_key(full) == _decision_key(compact),
                "confidence_full": full.recommendation.confidence if full.recommendation else None,
                "confidence_compact": compact.recommendation.confidence if compact.recommendation else None,
            })
        except Exception as exc:
            errors.append({"index": d.index, "error": f"{type(exc).__name__}: {exc}"})

    matches = sum(1 for c in comparisons if c["match"])
    material_disagreements = [c for c in comparisons if not c["match"]]
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
        "schema_version": 1,
        "policy": "bounded_compact_prompt_equivalence",
        "dataset": args.dataset,
        "sample_requested": args.sample,
        "sample_tested": len(sample),
        "current_model": DEFAULT_MODEL,
        "temperature": 0.1,
        "coverage_unchanged": True,
        "comparisons": comparisons,
        "errors": errors,
        "agreement": {
            "exact_material_decision_agreement": agreement,
            "matches": matches,
            "disagreements": len(material_disagreements),
            "valid_responses": len(comparisons),
        },
        "wire_size": {
            "current_chars": current_chars,
            "compact_chars": compact_chars,
            "estimated_percent_savings": savings,
        },
        "deployment_status": status,
        "decision_rule": "Only 100% material decision agreement with zero errors can be promoted; any disagreement rejects compaction; runtime/API errors are inconclusive.",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
