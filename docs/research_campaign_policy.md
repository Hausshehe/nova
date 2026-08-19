# Nova Trading Research — Finite Campaign Policy

Date: 2026-08-19

## Purpose

Nova must search for genuine trading edge without turning research into an
unbounded strategy-generation or parameter-tuning loop.

## Frozen campaign rule

For a fixed dataset/evaluation protocol, Nova may evaluate at most **5 frozen
hypotheses** before requiring a materially new evidence source.

A frozen hypothesis must be specified before historical evaluation:

- explicit causal rules;
- explicit cost assumptions;
- explicit train/validation/test protocol;
- predefined success/failure criteria;
- no parameter search after seeing the result.

The campaign count is by **hypothesis family**, not by implementation tweak.
A renamed or lightly modified version of a rejected idea counts as the same
family.

## Current campaign

Dataset:

`data/research/eurusd_daily.csv`

Period:

`2012-12-04` through `2022-03-04`

SHA-256:

`e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`

Evaluation cost:

4 bps round-trip (1 bps fee + 1 bps slippage per side).

### Completed frozen hypotheses

| Family | Hypothesis | Disposition |
|---|---|---|
| Horizon/expert adaptation | fixed 8-bar / adaptive 2-4-8 family | REJECTED / NOT PROMOTED |
| Volatility mean reversion | 20-bar mean, 2-sigma long-only | REJECTED |
| Trend breakout | Donchian 55/20 long-only | REJECTED |
| Calendar effect | Friday continuation next-session long-only | REJECTED |
| Opening discontinuity | positive opening gap next-session long-only | REJECTED |

Campaign usage:

**5 / 5 frozen hypotheses used — CLOSED / STOPPED.**

No sixth same-dataset hypothesis may be generated from this campaign.

The executable campaign-closure guard is checked before AI proposal generation.
Restart requires either a materially new evidence source or an explicitly
materially new market question.

## Multiple-testing guardrail

A positive result found during this campaign is **exploratory evidence only**.
It cannot be treated as proof merely because it is the best of several
attempts.

Any candidate that appears promising must pass independent validation on a
new dataset or untouched evidence source. The pre-MT5 promotion gate remains
mandatory.

## Stop conditions

Stop research on the current evidence source when:

1. five frozen hypothesis families have been evaluated; or
2. a materially independent dataset becomes available and the campaign is
   deliberately restarted; or
3. the evidence repeatedly remains null and further hypotheses are unlikely
to add information without changing the data or market question.

For this campaign, condition 1 has been reached.

## Explicitly prohibited

Do not:

- retune a rejected hypothesis on the same dataset;
- create near-duplicate variants solely to search a better number;
- use AI to rescue failed historical results;
- select a strategy because it is the best among many failed attempts;
- treat repeated tests on the same sample as independent confirmation;
- begin MT5 execution work because a single historical run looks attractive;
- reopen this campaign without a materially new evidence source or a materially new market question.

## Goal

The objective is not to maximize the number of backtests. The objective is to
find out whether Nova can identify evidence of a robust, causal, reproducible
trading edge. If the evidence remains insufficient, stopping is a successful
research outcome.
