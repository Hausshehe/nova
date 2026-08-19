# Nova Trading Research — Independent Evidence Protocol

## Purpose

A promising historical result is not enough to justify MT5 work. The same frozen hypothesis must survive evidence that was not used to discover or select it.

## Dataset provenance

Every independent dataset must have a manifest containing:

- source name and source URL;
- instrument and timeframe;
- exact file SHA-256;
- row count;
- first and last timestamps;
- retrieval timestamp.

The manifest is frozen before evaluation. A byte change invalidates the manifest.

## Independence rule

A validation dataset is independent only when the research memory gate classifies it as `INDEPENDENT_VALIDATION` rather than `DUPLICATE_EVIDENCE`.

A different file name is not enough. Dataset content is identified by SHA-256.

## Evaluation rule

The hypothesis, strategy version, costs, and success criteria remain unchanged from the initial experiment. Independent validation may not modify them.

The same deterministic experiment runner is reused so that only the evidence source changes.

## Current candidate evidence source

Initial campaign:

`data/research/eurusd_daily.csv`

An external validation source may be used after its manifest is frozen. Dukascopy's Historical Data Export provides historical Forex data in CSV form, including EUR/USD and daily timeframes. See the project research notes for the exact source used in a future validation run.
