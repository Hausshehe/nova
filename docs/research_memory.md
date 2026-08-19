# Nova Research Memory

Nova's research memory is backed by `trading_research.memory.ExperienceStore` (SQLite).

The memory is evidence storage, not a trading authority.

## Memory rules

1. Completed experiments are immutable. Re-recording the same experiment with identical evidence is idempotent; different evidence under the same experiment ID is rejected.
2. Each experiment stores a canonical record hash, hypothesis fingerprint, and dataset SHA-256 when the dataset path is available.
3. Stored experiment records are integrity-checked before retrieval.
4. Hypothesis novelty is determined from the validated hypothesis fingerprint, not its display name.
5. A rejected hypothesis on the same evidence must not be endlessly re-tuned. A genuinely new hypothesis or an independent validation dataset is required.
6. Strategy lifecycle state is separate from research evidence. A research backtest may update research state for CANDIDATE strategies but cannot silently approve, retire, or block an already authorized strategy.
7. Trade rows may update because an OPEN trade legitimately becomes a closed outcome; execution authorization is outside the memory layer.
8. Memory may inform reasoning, but stored experience never overrides causality, deterministic gates, permissions, or safety policy.

## What memory should capture

For every meaningful experiment or trade lifecycle event, preserve:

- what was hypothesized;
- which strategy version was used;
- what dataset and period were used;
- what costs and validation protocol were used;
- what happened;
- why it happened or failed when known;
- what should not be repeated;
- what remains uncertain.

The purpose is to make Nova accumulate usable experience without accumulating hidden state, accidental parameter tuning, or unverified beliefs.
