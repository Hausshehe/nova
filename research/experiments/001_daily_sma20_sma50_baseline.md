# Experiment 001 — EURUSD Daily SMA20/SMA50 Baseline

Date: 2026-08-19
Branch: `trading-research-lab`
Status: `REJECT`

## Objective

Validate the end-to-end deterministic research pipeline with one fixed, pre-registered hypothesis. This experiment is a pipeline baseline, not a strategy-optimization exercise.

## Hypothesis

A 20-day SMA above a 50-day SMA on EURUSD daily closes indicates persistent upward momentum and produces positive expectancy after stated transaction costs.

- Entry: signal evaluated after a completed bar; enter at the next bar open.
- Exit: signal evaluated after a completed bar; exit at the next bar open.
- Fee: 1 bps per side.
- Slippage: 1 bps per side.
- Falsifier: non-positive held-out test expectancy or failure of the initial research gates.
- Parameters were fixed before this result and were not optimized.

## Dataset

- Symbol: EURUSD
- Timeframe: 1D
- Rows: 2,400
- First timestamp: 2012-12-04 UTC
- Last timestamp: 2022-03-04 UTC
- Split: chronological train/validation/test

## Results

| Split | Bars | Trades | Net Return | Max Drawdown | Profit Factor | Expectancy | Win Rate | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Train | 1,440 | 14 | -4.704% | 13.772% | 0.7790 | -0.002980 | 35.71% | REJECT |
| Validation | 480 | 6 | -6.779% | 6.779% | 0.0000 | -0.011559 | 0.00% | REJECT |
| Test | 480 | 6 | -0.880% | 6.131% | 0.8806 | -0.001248 | 33.33% | REJECT |

## Gate reasons

### Train

- `too_few_trades:14<100`
- `profit_factor_below_gate:0.7789<1.1500`
- `expectancy_not_positive:-0.002980<=0.000000`

### Validation

- `too_few_trades:6<100`
- `profit_factor_below_gate:0.0000<1.1500`
- `expectancy_not_positive:-0.011559<=0.000000`
- `win_rate_below_gate:0.0000<0.3500`

### Test

- `too_few_trades:6<100`
- `profit_factor_below_gate:0.8806<1.1500`
- `expectancy_not_positive:-0.001248<=0.000000`
- `win_rate_below_gate:0.3333<0.3500`

## Decision

**REJECT.** The pre-registered baseline does not provide evidence of positive edge. The held-out test is negative and fails the profit-factor and expectancy gates.

The low trade count also means this experiment is not strong evidence about the long-run performance of this particular strategy. It is primarily evidence that the research pipeline can execute a fixed hypothesis and reject it without optimization.

## Next action

Do **not** tune SMA parameters based on this result. First perform a separate research-methodology experiment to determine whether the current statistical gates are appropriately calibrated for different strategy frequencies and sample sizes. Any gate change must be justified independently of this observed result and locked before the next strategy test.
