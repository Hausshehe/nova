# Nova Trading Research — Frozen Horizon Hypothesis Status

Date: 2026-08-19

## Disposition

The fixed-8-bar hypothesis is **rejected as a current edge candidate**.

The adaptive 2/4/8 horizon configuration is **not promoted**. It remains an exploratory null/near-zero observation only.

No strategy from this audit is approved for paper/demo or live execution.

## Evidence

Dataset: `data/research/eurusd_daily.csv`

- 2400 daily EURUSD bars
- 2012-12-04 through 2022-03-04
- SHA-256 recorded by the audit runner: `e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`
- Evaluation cost: 4 bps

Frozen non-overlapping results:

| Configuration | Mean net return | 95% moving-block bootstrap CI |
|---|---:|---:|
| Naive long 8 | -8.052 bps | [-21.89, 5.07] |
| Naive short 8 | +0.052 bps | [-13.09, 13.81] |
| Adaptive 2/4/8 | +0.890 bps | [-14.75, 17.43] |
| Fixed expert 8 | -10.124 bps | [-25.57, 8.66] |

The original overlapping fixed-8 result of approximately +2.43 bps at 4 bps cost is therefore not considered evidence of a robust edge. Removing overlapping holdings reverses the sign to approximately -10.12 bps.

## Robustness finding

The predeclared bootstrap block-length grid (1, 3, 5, 10, 20) produces confidence intervals that continue to cross zero for the adaptive and baseline configurations, while fixed-8 remains materially negative in sample and never obtains a positive lower confidence bound.

This does **not** establish that the adaptive strategy is profitable. Its observed mean is small and its uncertainty is large.

## Research rule now enforced

Do not:

- tune the 8-bar horizon against this dataset;
- add another confidence threshold to rescue it;
- add another ensemble/regime layer solely because this result is weak;
- use AI to rescue the hypothesis;
- reinterpret overlapping forecast counts as independent trade evidence;
- promote any configuration based on this audit.

## Next research direction

The next hypothesis must be materially different from simply adding complexity around the same horizon/expert family.

A valid next experiment should begin with a new causal hypothesis, a predefined success/failure criterion, and a fresh evaluation protocol. The current 2012–2022 sample should not be repeatedly reused as an optimization target.

The lab's next goal is therefore **hypothesis generation and independent validation design**, not further tuning of the frozen horizon family.

## Interpretation

This result is a successful research outcome: the system prevented a modest overlapping backtest from being mistaken for robust edge and stopped the project from entering another architecture/tuning loop.
