# Nova Trading Research — Broader Universe Protocol

Date: 2026-08-19

## Purpose

The first EURUSD-daily campaign answered a narrow question:

> Do five frozen hypothesis families produce convincing evidence on one EURUSD daily dataset?

Answer: no.

That result must **not** be interpreted as proof that Nova cannot find trading edge.
It means the evidence source was narrow.

This protocol opens a materially broader, but still finite, research campaign.

## Research question

> Can Nova identify a causal, reproducible, cost-aware trading edge that survives
> unseen data across more than one market context?

This is a capability question, not a search for the single best backtest.

## Universe

### Asset families

Tier A — FX majors:

- EURUSD
- GBPUSD
- USDJPY
- AUDUSD
- USDCAD
- USDCHF
- NZDUSD

Tier B — major index instruments:

- US500
- NAS100
- US30

Tier C — liquid commodities:

- XAUUSD
- XAGUSD
- WTI

Canonical names are research identifiers only. Broker-specific MT5 symbol
names must be mapped separately and must never change the research identity.

## Timeframes

Primary discovery timeframes:

- 1D
- 4H

1H is reserved for a later execution-oriented question and is **not** part of
the first broader screening campaign. This prevents microstructure and cost
complexity from obscuring the initial capability question.

## Fixed hypothesis families

The first broader campaign uses four structurally different families:

1. Momentum / trend continuation
2. Mean reversion
3. Breakout / volatility expansion
4. Cross-market relative behavior

Each family must be specified before evaluation.

No post-result parameter rescue, cherry-picking, or family splitting is allowed.
A minor parameter modification remains the same hypothesis family.

## Evaluation design

For every market/timeframe context:

- causal execution only;
- explicit transaction costs;
- train / validation / test separation;
- untouched final holdout;
- provenance and dataset fingerprint;
- experiment lineage;
- statistical diagnostics;
- minimum trade/evidence requirements;
- parameter stability checks when a family intrinsically requires parameters.

Discovery results are exploratory. A positive result is **not** promotion evidence.

## Breadth and multiple-testing control

The universe intentionally contains many contexts, so a single positive context
must not be treated as proof.

A family becomes interesting only when:

- evidence is positive after costs;
- it is not isolated to one instrument;
- it survives unseen data;
- uncertainty is acceptable;
- the effect is not explained by an obvious data/execution artifact.

Independent replication is required before any transition to MT5 DEMO.

## Campaign budget

The screening universe is fixed at:

- 13 instruments
- 2 discovery timeframes
- 4 hypothesis families

Maximum screening contexts:

**104 market/timeframe/family evaluations.**

This is a hard campaign budget.

The budget is large enough to test breadth, but finite enough to terminate.
We do not expand the universe because a result looks promising.

Expansion requires a new research question and a new campaign declaration.

## Stop / decision checkpoints

### Checkpoint 1 — Broad screening complete

After the fixed 104-context matrix is evaluated, stop and answer:

> Is there credible evidence of a repeatable edge anywhere in the broader universe?

If no: stop trading research unless a materially new market question is justified.

If yes: do **not** trade it. Move to independent replication.

### Checkpoint 2 — Independent replication

A promising family/context must be frozen and evaluated on an untouched evidence
source or materially independent dataset.

If replication fails: reject the candidate and return to the campaign decision.

If replication succeeds: proceed to robustness and execution hardening.

### Checkpoint 3 — DEMO readiness

Only a candidate that survives research, independent replication, costs,
uncertainty, and risk gates may proceed toward MT5 DEMO.

## Data-source policy

The research dataset is identified by content hash and provenance metadata.
A source is not considered independent merely because it was downloaded on a
different date.

For the first broader campaign, historical data may use an external provider
with coverage across the selected asset families (for example Dukascopy's
historical export), subject to checksum, schema, timestamps, and coverage audit.
Dukascopy documents historical data for Forex, commodities, and indices and
supports multiple timeframes. The exact downloaded files must be frozen before
testing.

A separate provider/dataset should be used for independent replication when
feasible.

## What this campaign is NOT

It is not:

- 104 opportunities to find one lucky winner;
- permission to retune after results;
- permission to keep adding markets;
- permission to select the strongest market after seeing the data;
- evidence that a strategy works because it works in one context;
- a reason to start MT5 execution early.

## Final principle

The purpose of the broader universe is to answer the real question with enough
breadth that a negative result is meaningful and a positive result is difficult
to explain away as a narrow backtest artifact.

When the evidence can answer the question, **stop and make the decision**.
