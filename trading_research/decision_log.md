# Nova Trading Research — Experiment Contract

## Objective

Determine whether Nova can become an evidence-first trading research system before investing time in autonomous execution or a larger trading architecture.

The first question is strictly:

> Can the system research a market, formulate a falsifiable hypothesis, test it, analyze the results, reject bad ideas, and identify candidates that survive predefined validation gates?

A failure at this stage is a valid outcome. We stop early rather than expanding the system around an unproven premise.

## Non-negotiable rules

1. No real-money trading during the research gate.
2. Every hypothesis must have explicit, deterministic rules and a falsifier.
3. Every backtest must separate development/training data from validation data.
4. A strategy is never accepted from in-sample results alone.
5. The research system must be able to reject its own ideas.
6. No parameter tweaking after seeing validation/test results unless the experiment is explicitly marked as a new hypothesis.
7. Every experiment records its inputs, code/version, data range, metrics, and decision.
8. A failed experiment gets one documented follow-up hypothesis at most before the idea is paused or rejected.
9. No open-ended retry loops. Every diagnostic has a bounded attempt count or time budget.
10. The AI is allowed to propose hypotheses; deterministic code decides whether the evidence passes the current gate.

## Gates

### Gate 0 — Environment

Prove that the chosen Windows/MT5 environment can:

- access historical OHLC/tick data;
- identify symbols/timeframes;
- run a deterministic Python test;
- save experiment artifacts locally.

**Stop condition:** if the environment cannot be established without paid infrastructure, redesign the environment before building further.

### Gate 1 — Research representation

Prove that Nova can convert a natural-language market idea into a structured `Hypothesis` with:

- thesis;
- symbol;
- timeframe;
- explicit entry/exit rules;
- expected edge;
- falsifier.

**Stop condition:** if hypotheses remain too vague to backtest deterministically, improve the representation before adding more intelligence.

### Gate 2 — Deterministic testing

Prove that the same hypothesis + same data produces the same result.

Required metrics include at minimum:

- trade count;
- net return;
- profit factor;
- expectancy;
- win rate;
- maximum drawdown.

**Stop condition:** if results are not reproducible, do not add AI research loops.

### Gate 3 — Scientific rejection

Prove that weak strategies are automatically rejected by fixed gates.

The system must be able to output `REJECT` with concrete reasons rather than rationalizing poor results.

**Stop condition:** if the AI cannot reliably accept/reject based on evidence, keep the system deterministic and do not grant it autonomous strategy authority.

### Gate 4 — Out-of-sample survival

A candidate must pass unseen validation data without changing its rules after seeing the validation results.

**Stop condition:** if the edge disappears out of sample, reject the hypothesis and record the reason.

### Gate 5 — Robustness

Only after Gate 4 succeeds do we test robustness to:

- different market periods;
- transaction costs/spread assumptions;
- reasonable parameter perturbations;
- alternative symbols or regimes where the thesis claims generality.

**Stop condition:** if performance depends on a narrow parameter or period, reject or narrow the hypothesis.

### Gate 6 — Demo execution

Only a research candidate that survives the earlier gates may reach MT5 demo execution.

No real-money execution is part of the first research project.

## Decision vocabulary

- **REJECT:** evidence failed a gate; do not keep tuning the same idea.
- **INCONCLUSIVE:** evidence is insufficient; define one bounded follow-up experiment.
- **PROMISING:** candidate passed the current gate; proceed only to the next predefined gate.

## Anti-loop record

Every investigation uses:

```text
Problem
Hypothesis about cause
Single bounded experiment
Expected result
Observed result
Decision
Next gate
```

If the observed result does not distinguish between hypotheses, design a better diagnostic instead of modifying production code blindly.

## Current status

**Phase:** Gate 0 planning.

**Do not build autonomous trading yet.**

The next implementation target is the deterministic research harness and a minimal data contract that can run without an MT5 connection. MT5 connectivity is a separate Gate 0 adapter.
