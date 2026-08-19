import json
from pathlib import Path

from trading_research.research_universe import MAX_CONTEXTS, build_research_universe


def test_manifest_matches_code_definition():
    manifest_path = Path(__file__).parents[2] / "docs" / "trading_research_universe_v2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["maximum_contexts"] == MAX_CONTEXTS
    assert manifest["maximum_contexts"] == len(build_research_universe())
    assert manifest["timeframes"] == ["1D", "4H"]
    assert manifest["hypothesis_families"] == [
        "momentum_continuation",
        "mean_reversion",
        "breakout_volatility_expansion",
        "cross_market_relative_behavior",
    ]
