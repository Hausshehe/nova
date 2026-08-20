# Nova Experiment 2 — Adaptive Predictive Research Protocol

## Research question

Can a predictive AI model produce a trading signal whose advantage survives realistic costs, chronological walk-forward validation, and a completely untouched final out-of-sample test across a broad market universe?

A result is classified as:

- YES: evidence supports a robust, economically meaningful predictive/trading edge.
- NO: the evidence does not support the hypothesis.
- INCONCLUSIVE: the experiment is compromised by insufficient data, reproducibility, statistical power, or other methodological/infrastructure failure.

A profitable-looking backtest is not sufficient for YES.

## Core anti-leakage rules

1. Features at time t may use only observations available at or before t.
2. Targets may use future observations only after the feature timestamp.
3. Model fitting, feature normalization, threshold selection, and hyperparameter selection must use training/development data only.
4. Validation data may be used for model selection during development, but never for final performance claims.
5. The final test period is locked before model selection and must remain untouched until the protocol's final evaluation step.
6. No random shuffling of time series.
7. No strategy/model changes after inspecting final-test results.
8. Any new hypothesis or model family after test inspection is a new experiment.

## Baseline research design

Historical window: 2010-01-01 through 2025-12-31.

Primary horizons: 1-bar and 4-bar forward returns, subject to sufficient sample size.

Initial feature family: causal price/volatility features from OHLCV only. Cross-market features are a separate controlled extension and must be frozen before evaluation.

Initial model ladder:

1. No-skill / historical-mean baseline.
2. Regularized linear classifier/regressor.
3. Tree-based model if justified by baseline results and frozen before test use.
4. Ensemble/meta-model only after component models pass development gates.

## Walk-forward design

Development uses chronological train/validation windows.

The final test is a contiguous chronological holdout that is not used for model selection. The exact final-test boundary must be recorded in the frozen run manifest before the final run.

Training normalization statistics must be calculated from training rows only.

## Trading conversion

Predictions are converted to trades only through an explicit, deterministic rule fixed before final testing.

Transaction costs must be included before claiming trading performance. The baseline cost assumption is 1 bps fee per side plus 1 bps slippage per side unless a later experiment explicitly freezes a different cost schedule before testing.

## Research gates

A candidate model must first beat a no-skill baseline on out-of-sample predictive metrics during walk-forward validation.

A trading candidate must then survive:

- cost inclusion;
- multiple walk-forward windows;
- minimum trade/sample-size requirements;
- parameter/threshold perturbation checks;
- market/timeframe breadth checks;
- bootstrap or equivalent uncertainty analysis;
- concentration checks;
- final untouched test evaluation.

Models that work only in training are rejected.

Models that depend on a tiny number of trades are rejected.

Models whose advantage disappears after costs are rejected.

Models that are highly sensitive to small parameter changes are rejected.

## Final-test rule

After the final test is executed, STOP.

Do not retune the model, add markets, change costs, change splits, change features, or selectively discard failures based on the final-test outcome.

The final conclusion must be based on the frozen evidence.

## Scope rule

Experiment 2 is independent of the previous rule-based experiment. The previous experiment's NO result does not determine Experiment 2.

Any new model family or materially different data/feature protocol created after final-test inspection is a new experiment.
