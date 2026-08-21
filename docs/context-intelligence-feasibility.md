# Nova Context-Intelligence Feasibility Experiment

## Purpose

Test one specific claim before expanding Nova's autonomous trading architecture:

> Does giving Nova causal market context improve decision quality beyond price-only information?

This experiment is a feasibility gate, not a strategy-search campaign.

## Frozen research question

Compare two information sets on the same historical decision points:

1. **Price-only baseline**: OHLCV/market-structure information available from the market series.
2. **Context-enriched model**: the same price information plus time-causal external context such as economic releases, macro state, major-news/event features, and related-market confirmation.

The context-enriched model is not allowed to modify the historical sample, choose the evaluation period after seeing outcomes, or use future information.

## Experimental rules

- Historical timestamps are ordered strictly forward in time.
- Every context item must carry an availability timestamp. Information published after the decision timestamp is forbidden.
- Evaluation periods are locked before results are inspected.
- No parameter tuning on the final test period.
- No candidate recycling after a failed final test.
- The same transaction-cost assumptions apply to both variants.
- `WAIT` is a valid decision.
- The LLM is an analyst, not an unrestricted optimizer. It cannot rewrite the evaluation rules.

## Phase 1: feasibility

Start with one liquid market and a bounded historical window.

The first implementation should use context sources that can be reconstructed causally and reproducibly. Macro/economic-release data should use release/vintage timing rather than revised values when possible. News should be reduced first to timestamped, reproducible event/sentiment features rather than arbitrary hindsight summaries.

The external-context layer should answer simple questions before any complex trading logic is attempted:

- Was there a relevant macro/news event?
- What direction/pressure did the event imply?
- Did related markets confirm or contradict it?
- What was the market regime immediately before the decision?

## Primary comparison

The main result is **incremental predictive value**:

`context_enriched_score - price_only_score`

The exact score should be defined before the final test and must include:

- directional decision quality;
- opportunity precision;
- abstention quality (`WAIT` should not be penalized as a mistake when no favorable opportunity exists);
- trading return after costs as a secondary metric;
- drawdown and trade count.

## What counts as evidence

A favorable backtest by itself is not sufficient.

The context layer should only be considered useful if it improves out-of-sample decision quality by a meaningful margin while remaining stable across multiple subperiods and without requiring repeated tuning.

A single lucky period, a tiny number of trades, or an improvement that disappears when the test window changes is not a pass.

## Kill criteria

Stop this research direction if the context-enriched variant repeatedly fails to improve over the price-only baseline under pre-registered tests.

Do **not** respond to failure by adding more indicators, more prompts, more model size, or more search dimensions without a new falsifiable hypothesis.

## Why this is different from the previous campaign

The previous campaign searched a finite set of trading hypotheses and selected screen-positive candidates. Independent 2026 validation rejected both frozen candidates: NAS100 had too few trades and XAGUSD failed on return/profit factor.

This experiment therefore does not start by searching for another profitable rule. It asks whether richer information actually adds measurable value to Nova's decision process.

## Decision gate

- **PASS:** context produces robust incremental value -> continue toward adaptive context-aware research.
- **MIXED:** context helps only in a narrow, identifiable condition -> isolate and test that condition once.
- **FAIL:** no robust incremental value -> stop treating richer context as the core solution.
