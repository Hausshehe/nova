"""Bounded hybrid research: deterministic candidate policy plus AI adjudication.

The deterministic candidate policy remains authoritative. AI is advisory only.
This module is research-only and uses bounded retries/compact context so API
limits do not masquerade as strategy failures.
"""
from __future__ import annotations

import os
import time
from typing import Sequence

from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices
from .market_monitor import MarketEvent
from .market_reasoner import GroqMarketReasoner
from .online_expert_ensemble import EXPERTS, _direction


def _features(closes: Sequence[float], index: int) -> str:
    parts: list[str] = []
    for window in (4, 8, 12, 20):
        if index >= window:
            bps = (closes[index] / closes[index-window] - 1.0) * 10_000.0
            parts.append(f"m{window}={bps:.1f}")
    if index >= 49:
        fast = sum(closes[index-19:index+1]) / 20.0
        slow = sum(closes[index-49:index+1]) / 50.0
        gap = (fast / slow - 1.0) * 10_000.0
        parts.append(f"g={gap:.1f}")
    return ",".join(parts)


def evaluate_hybrid_ai_adjudication(
    bars: Sequence[Bar], *, limit: int = 12, model: str = "openai/gpt-oss-120b",
    max_retries: int = 2, retry_sleep_seconds: float = 4.5,
) -> dict[str, object]:
    if limit <= 0 or max_retries < 0 or retry_sleep_seconds < 0:
        raise ValueError("invalid parameters")
    candidates = sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    if not candidates:
        return {"policy": "hybrid_ai_adjudication", "candidate_bars": 0, "evaluated": 0, "api_errors": 0}

    # Deterministic bounded sample, evenly spaced across the candidate stream.
    step = max(1, len(candidates) // limit)
    sampled = candidates[::step][:limit]
    closes = [bar.close for bar in bars]
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for this bounded research experiment")
    reasoner = GroqMarketReasoner(api_key, model=model)
    comparisons: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    total_request_chars = 0
    retried_requests = 0

    for index in sampled:
        directions = {expert: _direction(closes, index, expert) for expert in EXPERTS}
        compact_directions = ",".join(f"{k}:{v or '-'}" for k, v in directions.items())
        event = MarketEvent(
            event_type="CANDIDATE_OPPORTUNITY",
            symbol="EURUSD",
            timeframe="1D",
            timestamp=bars[index].timestamp,
            reason="High-recall deterministic candidate; AI is advisory only.",
            price=bars[index].close,
        )
        context = (
            f"i={index};dirs={compact_directions};f={_features(closes, index)};"
            "candidate=1;ai_advisory_only=1"
        )
        total_request_chars += len(context)
        attempt = 0
        while True:
            try:
                analysis = reasoner.analyze(
                    event,
                    strategy_context="high_recall_candidate_policy",
                    market_context=context,
                )
                rec = analysis.recommendation
                comparisons.append({
                    "index": index,
                    "assessment": analysis.assessment,
                    "urgency": analysis.urgency,
                    "recommendation_action": rec.action if rec else None,
                    "recommendation_confidence": rec.confidence if rec else None,
                    "relevant_strategies": list(analysis.relevant_strategies),
                    "retries": attempt,
                })
                if attempt:
                    retried_requests += 1
                break
            except RuntimeError as exc:
                message = str(exc)
                is_rate_limit = "HTTP 429" in message or "rate_limit_exceeded" in message
                if is_rate_limit and attempt < max_retries:
                    attempt += 1
                    time.sleep(retry_sleep_seconds)
                    continue
                errors.append({"index": index, "error": f"{type(exc).__name__}: {exc}", "retries": attempt})
                if attempt:
                    retried_requests += 1
                break
            except Exception as exc:
                errors.append({"index": index, "error": f"{type(exc).__name__}: {exc}", "retries": attempt})
                break

    return {
        "policy": "bounded_hybrid_ai_adjudication",
        "candidate_bars": len(candidates),
        "sample_requested": limit,
        "sampled_candidate_bars": len(sampled),
        "evaluated": len(comparisons),
        "api_errors": len(errors),
        "comparisons": comparisons,
        "errors": errors,
        "model": model,
        "telemetry": {
            "total_context_chars": total_request_chars,
            "mean_context_chars": total_request_chars / len(sampled) if sampled else 0.0,
            "retried_requests": retried_requests,
            "max_retries": max_retries,
            "retry_sleep_seconds": retry_sleep_seconds,
        },
        "causal_rule": "Only current/past market state is sent to AI; future outcomes are not included in the request and are evaluation-only.",
        "safety_rule": "AI is advisory only; deterministic policy and permission boundaries remain authoritative.",
    }
