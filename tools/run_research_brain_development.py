"""Run Nova Research Brain v1 against a development-only XAGUSD sample.

This runner deliberately has no confirmation-data input. It generates one
structured brief, downloads only the pre-cutoff development period, validates
the data, and executes the deterministic bounded regime research plan.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from trading_research.data import load_csv
from trading_research.dukascopy_history import DukascopyClient, write_csv
from trading_research.regime_conditioned_research import run_development_regime_research
from trading_research.research_brain import ResearchBrain, ResearchQuestion

DEVELOPMENT_START_UTC = "2010-01-01T00:00:00+00:00"
DEVELOPMENT_END_UTC = "2023-01-01T00:00:00+00:00"
SYMBOL = "XAGUSD"
TIMEFRAME = "4H"
TRANSACTION_COST_BPS = 4.0


def _brief_payload(brief) -> dict[str, object]:
    return {
        "research_question": brief.research_question,
        "mechanism": brief.mechanism,
        "hypothesis": brief.hypothesis,
        "why_it_might_work": brief.why_it_might_work,
        "what_would_falsify_it": brief.what_would_falsify_it,
        "primary_test": brief.primary_test,
        "development_only_exploration": list(brief.development_only_exploration),
        "confirmation_rule": brief.confirmation_rule,
        "key_risks": list(brief.key_risks),
        "research_priority": brief.research_priority,
        "next_action": brief.next_action,
        "experiment_plan": brief.experiment_plan.__dict__,
    }


def run(output_dir: str | Path) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    question = ResearchQuestion(
        question=(
            "Investigate whether short-horizon continuation or reversal in "
            "XAGUSD on 4H data is meaningfully conditioned on the current "
            "market regime. Choose the mechanism yourself; do not assume "
            "momentum, mean reversion, volatility, or a specific indicator "
            "family in advance."
        ),
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        constraints=(
            "Development data only for discovery and exploration. Do not use "
            "confirmation data, do not change gates, include realistic costs, "
            "and do not claim a real edge."
        ),
    )

    brain = ResearchBrain()
    brief = brain.investigate(question)
    brief_payload = _brief_payload(brief)
    (output / "research_brief.json").write_text(
        json.dumps(brief_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    client = DukascopyClient()
    candles = client.historical_prices(
        instrument=SYMBOL,
        timeframe=TIMEFRAME,
        start_utc=DEVELOPMENT_START_UTC,
        end_utc=DEVELOPMENT_END_UTC,
        progress=print,
    )
    if len(candles) < 250:
        raise ValueError(f"insufficient development bars: {len(candles)}")

    dataset_path = output / f"{SYMBOL}_{TIMEFRAME}_development.csv"
    dataset_sha256 = write_csv(candles, dataset_path)
    bars = load_csv(dataset_path)

    result = run_development_regime_research(
        bars,
        brief.experiment_plan,
        transaction_cost_bps=TRANSACTION_COST_BPS,
    )
    result_payload = {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "development_start_utc": DEVELOPMENT_START_UTC,
        "development_end_utc_exclusive": DEVELOPMENT_END_UTC,
        "confirmation_data_loaded": False,
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "dataset_sha256": dataset_sha256,
        "bars": len(bars),
        "research_brief": brief_payload,
        "development_result": result.to_dict(),
    }
    (output / "development_result.json").write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result_payload, indent=2, sort_keys=True))
    return result_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="research_artifacts/research_brain_development")
    args = parser.parse_args()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is required")
    run(args.output_dir)


if __name__ == "__main__":
    main()
