# Nova Experience Memory Model

## Purpose

Nova's experience memory records what was observed, under which evidence, and what disposition followed. Memory is evidence history, not a prediction engine and never an authority to trade.

## Knowledge classes

Every stored research result belongs to a temporal knowledge class:

- `HISTORICAL_RESEARCH`: frozen backtest evidence available before a later decision.
- `INDEPENDENT_VALIDATION`: later evidence using a genuinely new dataset/evidence source for an already-frozen hypothesis.
- `DEMO_OBSERVATION`: observed execution/outcome from MT5 DEMO after explicit approval.
- `HYPOTHESIS`: a proposed idea that has not yet been evaluated.
- `REJECTED`: an evaluated hypothesis that failed predefined evidence gates.
- `INCONCLUSIVE`: an evaluated hypothesis whose evidence was insufficient to establish success or failure.
- `PROMOTED`: a strategy that cleared every required promotion gate. This status is never inferred from a single backtest result.
- `RETIRED`: previously promoted strategy no longer authorized for research/execution.

## Core temporal rule

A decision at time `T` may only use evidence whose `observed_at` / experiment completion time is <= `T`.

A test result observed after the decision cannot be used to justify a decision that would have occurred before the test was available.

## Research lineage

Research records should be linked by:

`hypothesis_fingerprint -> dataset_sha256 -> experiment_id -> parent/derived experiment references`

This allows Nova to answer:

- What did we try?
- What evidence did we use?
- Was it duplicate or independent?
- What did the gates say?
- Why was it rejected?
- What later evidence, if any, changed the disposition?

## Safety rule

Memory may inform research planning and duplicate avoidance. It may not:

- authorize a trade;
- override a safety gate;
- convert a rejected result into a promoted strategy;
- inject future observations into historical evaluation;
- justify repeated same-dataset tuning.

## Future extension

A later schema migration may add explicit lineage and temporal-decision fields to the SQLite store. Until then, existing `record_json`, dataset hashes, hypothesis fingerprints, and experiment timestamps remain the source of truth.
