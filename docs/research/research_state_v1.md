# Nova Research State v1

Nova's research memory must represent beliefs and uncertainty, not merely transcripts.

## State model

```text
ResearchState
├── question
├── scope
│   ├── asset
│   ├── timeframe
│   ├── data_boundaries
│   └── budget
├── mechanisms[]
│   ├── id
│   ├── claim
│   ├── causal_story
│   ├── predictions[]
│   ├── supporting_evidence[]
│   ├── contradicting_evidence[]
│   ├── tested_formulations[]
│   ├── surviving_formulations[]
│   ├── confidence
│   └── status
├── experiments[]
│   ├── id
│   ├── mechanism_ids[]
│   ├── question
│   ├── predicted_outcomes[]
│   ├── preregistration
│   ├── result
│   ├── interpretation
│   └── information_gained
├── constraints[]
├── forbidden_repetitions[]
├── confirmation_status
└── next_decision
```

## Non-negotiable semantics

- A failed implementation is not automatically a failed mechanism.
- Repeated independent failures should reduce confidence and research priority.
- A parameter variant is not a new mechanism merely because its name differs.
- Evidence from confirmation data cannot become development evidence.
- Confidence must move in response to evidence; unchanged confidence after contradictory evidence is a research-state failure.
- Every experiment must state what uncertainty it is intended to reduce.
- The state must preserve negative results so Nova cannot accidentally rediscover dead branches.

## Architectural consequence

The research brain should eventually consume and emit `ResearchState` transitions. A conversation transcript may be retained for auditability, but it must not be the canonical research memory.
