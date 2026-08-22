# Nova Selective Trade Gate — Frozen Protocol

## Research question

Can causal abstention improve a fixed directional strategy by refusing trades whose observed state has not historically produced positive net outcomes?

## Why this is new

This is not the rejected context-selector experiment. The context selector chose among pre-existing experts and failed its untouched final test. This experiment keeps one fixed base strategy and asks a different question: **should this particular signal be taken or skipped?**

## Frozen base strategy

- 20-period SMA >= 50-period SMA: LONG.
- Otherwise: FLAT.
- Evaluation horizon: 4 bars.
- Entry/exit accounting: close-to-close for research consistency.
- Round-trip cost: 4 bps.

## Frozen gate

For each bar with a base LONG signal, define a causal state from:

- absolute 20/50 SMA gap bucketed in fixed 5 bps bins;
- signed 3-bar momentum bucketed in fixed 10 bps bins.

Using only completed development outcomes for that context state, take a future test trade only when:

- at least 40 completed historical base trades exist for the state; and
- the historical mean net outcome is strictly positive.

Otherwise the base signal is suppressed (no trade).

No parameters are optimized after observing the final test.

## Data split

The fixed 26-context universe is used. Each context uses its first 80% of bars for causal gate formation and its final 20% as the untouched test period.

## Promotion gate

Advance only if the frozen test shows all of:

- aggregate gated net contribution is positive;
- gated performance improves over the ungated base across the eligible test contexts;
- at least 70% of base trades are retained;
- at least 13 of the 26 contexts with sufficient test trades improve on mean net outcome.

The experiment is a research gate, not permission to trade.

## Kill rule

If the frozen final test fails, do not tune the state buckets, minimum sample count, confidence threshold, or base signal within this hypothesis family. Record the family as failed and move to the next genuinely different hypothesis.
