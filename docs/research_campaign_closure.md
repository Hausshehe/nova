# Executable Research Campaign Closure

The current EURUSD daily research campaign is closed after five frozen hypothesis families.

Dataset SHA-256:

`e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`

The closure guard is checked before AI proposal generation. A closed campaign
cannot spend another proposal or backtest on the same evidence source.

A restart requires a materially new evidence source or an explicitly materially
new market question. This invariant exists to prevent endless strategy mining
and parameter-tuning loops.
