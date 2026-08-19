# Nova Trading Research — Final Frozen Hypothesis

## Hypothesis family 5: opening-gap continuation

This is the final hypothesis family permitted by the current finite campaign.

### Fixed rule

At each completed daily bar `t`:

- if `open[t] > close[t-1]`, request LONG;
- the shared causal backtester executes the request at `open[t+1]`;
- the position is held for exactly the next trading session and exits when the following bar opens.

There is no gap-size threshold, lookback search, regime filter, parameter sweep, AI selection, or execution modification.

### Why this family is materially different

The signal is based on the opening discontinuity between consecutive daily sessions. Previous campaign families used multi-horizon directional returns, rolling mean-reversion, Donchian price breakouts, and a Friday calendar effect. This hypothesis tests a different observable: the daily open-to-prior-close repricing event.

### Frozen evaluation

Dataset:

`data/research/eurusd_daily.csv`

SHA-256:

`e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`

Costs:

- 1 bps fee per side
- 1 bps slippage per side
- 4 bps total round-trip

Protocol:

- chronological train / validation / test split;
- existing research gates;
- one historical evaluation;
- no changes after seeing results.

### Decision rule

Use the existing deterministic gate and campaign policy exactly as implemented. A result that is merely positive or best-of-campaign is not sufficient for promotion.

If the hypothesis fails, the current EURUSD campaign ends.
