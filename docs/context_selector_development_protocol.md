# Nova Context Selector — Development Protocol

Status: **development experiment; final test untouched**

## Research question

Can observable market context improve causal strategy/expert selection compared with a non-contextual causal selector, using only information available before each decision?

The immediate hypothesis is intentionally narrower than “Nova can make money”: contextual selection should outperform the global online expert ensemble on genuinely unseen development observations after the frozen transaction-cost assumption.

## Candidate policies

1. **Global selector**: the existing causal online expert ensemble, which ranks fixed directional experts using all completed historical outcomes.
2. **Contextual selector**: the existing causal contextual online expert ensemble, which ranks the same fixed experts separately within the current SMA-derived context, with a global fallback until contextual history is sufficient.

The expert set is frozen as the existing `EXPERTS` tuple. No new strategy family is introduced by this experiment.

## Data and holdout

Use the existing 26-context universe: 13 instruments x 2 timeframes.

Historical range: 2010-01-01 through 2025-12-31.

For this development experiment, only the earliest 80% of each chronological dataset may be evaluated. The final 20% is reserved and must not be read for model selection, threshold selection, parameter selection, or performance claims.

## Frozen cost

Use 4 bps round-trip, matching the existing online-ensemble implementation. Any cost sensitivity analysis is secondary and must not change the primary development comparison.

## Causality requirements

- A completed expert outcome becomes available only after its forecast horizon has elapsed.
- Context is computed from bars at or before the current decision.
- No future label is used to choose the current expert.
- No shuffling is allowed.
- No parameter tuning against the reserved final 20% is allowed.

## Primary comparison

For every context, report:

- decisions;
- decision rate;
- mean net return per decision in bps;
- positive-decision rate;
- fold-level mean net returns;
- number of positive folds;
- contextual minus global mean net return;
- whether contextual selection produced more net value than global selection.

Aggregate across all 26 contexts, but do not pool raw trades in a way that lets a single large dataset dominate the interpretation. Report both unweighted context-level means and the distribution of paired differences.

## Interpretation gates

This is a development experiment, not a final proof.

A positive result means the contextual selector has earned a larger, explicitly controlled follow-up experiment. It does **not** establish a robust trading edge.

A negative result means the simple context definition did not improve selection enough to justify promotion in its current form.

An infrastructure/data failure is inconclusive and should be repaired without changing the research question.

## Anti-overfitting rule

The SMA context definition, expert set, cost, history requirements, and 80% development boundary are frozen before evaluation on this branch.

Any new context family, expert family, parameter search, or model family created after reading the benchmark outcome is a new experiment.

No real-money trading is permitted.
