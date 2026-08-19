# Bounded Research Planning Preflight

`research_planning.py` converts the read-only experience brief into a conservative planning state.

It does not run experiments, change hypotheses, change research gates, select strategies, promote strategies, or authorize trading.

## Planning rules

- No prior evidence: a proposal may proceed to the normal novelty and deterministic research gates.
- Same dataset already used: do not repeat the evaluation or tune the hypothesis around the old result.
- Prior evidence without independent validation: require materially new evidence before claiming independent support.
- Independent validation already exists: review the existing lineage and gates before generating more work.
- Research budget exhausted: stop proposal generation.

An empty memory state is not positive evidence. The planner is advisory; deterministic gates remain authoritative.
