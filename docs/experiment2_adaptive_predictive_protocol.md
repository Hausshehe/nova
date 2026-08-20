# Nova Experiment 2 — Adaptive Predictive Trading Research Protocol

Status: **research scaffold; not yet frozen for the final test**

## Research question

Can an adaptive predictive trading system learn signals whose out-of-sample predictive value and net trading value survive chronological walk-forward evaluation, realistic costs, multiple markets, and anti-overfitting stress tests?

A successful result must demonstrate both predictive usefulness and economic usefulness. A profitable-looking backtest alone is insufficient.

## Core rules

1. The final test period is never used for feature selection, model selection, hyperparameter tuning, threshold selection, regime definitions, or strategy choice.
2. Every feature at timestamp `t` must be computable using information available no later than `t`.
3. Labels use strictly future returns; labels must never leak into features.
4. Model fitting and normalization are performed inside each training window only.
5. Validation data may select among pre-declared candidate models/hyperparameters, but may not be repeatedly mined until a desired result appears.
6. The final test is run once after the model/protocol is frozen.
7. Baselines are mandatory: buy-and-hold/naive direction, sign-of-last-return, and a simple moving-average/trend baseline where applicable.
8. A model must beat relevant baselines after the frozen cost model to be considered economically useful.
9. Robustness checks are mandatory: parameter perturbation, block bootstrap, time-window stability, and cross-market breadth.
10. A single excellent market/context is not evidence of a general edge.
11. No real-money trading is permitted during research.
12. Any post-test modification creates a new experiment; it cannot reuse the same test result as confirmation.

## Proposed data and horizon

Initial development universe: the same broad 13-instrument universe used in Experiment 1, with 1D and 4H bars where data quality supports them.

Historical development window: 2010-01-01 through 2025-12-31.

Chronological design:

- Development/train: earliest 60%
- Validation: next 20%
- Final test: last 20%

For model development, use rolling/expanding walk-forward windows inside the development portion. The final 20% remains untouched until the protocol is frozen.

## Prediction targets

Primary targets:

- next-bar direction;
- next-bar return;
- multi-bar forward return;
- probability of a return exceeding a cost-adjusted threshold.

The system should be evaluated first as a predictor and only then translated into trades.

## Feature families

Only pre-declared, leakage-safe families may be used in the initial experiment:

- lagged returns and momentum;
- rolling volatility and range;
- trend distance and moving-average structure;
- normalized candle/range features;
- volume-derived features where the dataset provides meaningful volume;
- cross-market lagged returns and relative strength, using only synchronized historical values.

No feature may use future bars, future normalization statistics, or information derived from the final test.

## Model families

Start with robust, interpretable baselines before expensive models:

1. logistic regression / linear probability model;
2. regularized linear regression for return prediction;
3. tree-based gradient boosting if available and justified;
4. a simple ensemble of independently trained candidates.

Do not start with reinforcement learning. RL is a later experiment requiring its own environment, execution model, and validation protocol.

## Trading conversion

A model prediction becomes a trade only when expected edge exceeds the frozen round-trip cost allowance plus a safety margin defined before test evaluation.

The system may abstain. No-trade is a valid prediction.

Position sizing is not part of the first edge test. First establish whether the signal has incremental predictive value. Risk sizing is a later layer.

## Costs

Initial research cost model should remain conservative and explicit. Use the same baseline assumptions as Experiment 1 where compatible, with fee and slippage applied symmetrically per side.

Cost sensitivity must be evaluated after the primary result using pre-declared stress levels.

## Statistical evidence

For each candidate and context, report:

- number of observations/trades;
- out-of-sample mean return;
- median return;
- hit rate where meaningful;
- profit factor where trades exist;
- maximum drawdown for the trading implementation;
- bootstrap uncertainty using contiguous trade blocks where appropriate;
- stability across walk-forward windows;
- performance relative to baseline.

Multiple-testing awareness is mandatory. Screening hundreds/thousands of model-feature combinations creates selection bias; model selection must therefore be limited and documented.

## Promotion rule

A candidate can proceed to final test only if it passes all pre-test gates:

- leakage checks;
- sufficient sample size;
- beats pre-declared baselines on validation;
- survives reasonable parameter perturbations;
- does not depend on a tiny number of observations;
- does not rely on a single market;
- passes implementation/reproducibility checks.

The final test then runs once.

## Final classification

YES: robust out-of-sample evidence supports a useful edge after costs and robustness checks.

NO: the evidence does not support a robust edge.

INCONCLUSIVE: data, implementation, statistical power, or reproducibility prevents a trustworthy conclusion.

Never convert INCONCLUSIVE into YES.

## Anti-loop policy

No blind reruns.
No test-peeking.
No parameter shopping after test exposure.
No universe changes because of poor results.
No cherry-picking.
No strategy modifications inside an experiment after final-test exposure.

Research infrastructure may be repaired, but the research question and frozen evaluation contract must remain unchanged.

## Experiment boundary

This document governs Experiment 2 only. Experiment 1 remains closed with a substantive replication result of NO and an original-source caveat documented separately.

Before final testing, this protocol must be converted into a versioned frozen protocol commit and the exact candidate set must be recorded.