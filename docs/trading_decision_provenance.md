# Trading Decision Provenance

Nova's trading experience must preserve what it knew when a trading decision was made.

Each immutable decision record captures:

- strategy and strategy version;
- symbol and timeframe;
- BUY / SELL / HOLD / REJECT decision;
- human-readable rationale;
- hypothesis and dataset fingerprints;
- experiment IDs used as evidence;
- market-state snapshot;
- risk snapshot;
- exact trading-memory context shown to the decision process;
- hash of that memory context;
- approval status.

The record is provenance only. It does not authorize orders and does not modify
promotion or safety gates.

A later trade outcome must be linked separately so Nova can compare:

`decision -> approval -> execution -> outcome -> lesson`

Decision records are immutable. Reusing a decision ID with different provenance
is rejected.
