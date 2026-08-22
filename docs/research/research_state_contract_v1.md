# Nova Research State Contract v1

Nova's research memory must represent the state of knowledge, not just a conversation transcript.

## Required top-level state

```json
{
  "research_question": "...",
  "scope": {"asset": "...", "timeframe": "...", "data_boundaries": "..."},
  "mechanisms": [],
  "evidence": [],
  "research_space": {},
  "uncertainties": [],
  "current_decision": {},
  "budget": {},
  "confirmation_protection": {}
}
```

## Mechanism record

Each mechanism must have:

- `id`: stable identifier
- `statement`: mechanism being investigated
- `predictions`: observable predictions that distinguish it
- `status`: `unseen | active | weakened | rejected | candidate | confirmed`
- `confidence`: bounded qualitative confidence plus rationale
- `supporting_evidence`: evidence IDs
- `contradicting_evidence`: evidence IDs
- `tested_formulations`: formulation IDs
- `remaining_uncertainty`: explicit unresolved questions

## Evidence record

Each result must preserve:

- `id`
- `experiment_id`
- `data_role`: `development | confirmation | replication`
- `result`
- `uncertainty`
- `cost_assumptions`
- `interpretation`
- `limitations`
- `what_it_changes`

## Research-space memory

The state must track:

- tested experiment families
- tested formulations and parameter regions
- rejected mechanisms
- prohibited repeat tests
- unresolved competing explanations
- unused research directions
- remaining exploration and confirmation budget

A parameter change inside the same mechanism is not automatically a new mechanism.

## Decision update rule

Every completed experiment must answer:

1. What belief changed?
2. Which mechanism became stronger or weaker?
3. Which research paths are now prohibited or lower priority?
4. What uncertainty remains?
5. What is the next experiment, and what decision would its outcomes produce?
6. Why is that experiment worth its research cost?

If no material belief changes, Nova should normally reject further variations unless a genuinely different mechanism or a clearly justified measurement correction is introduced.

## Confirmation protection

Confirmation data is an evidentiary boundary, not merely another dataset. Once a formulation is exposed to confirmation results, those results may update the final assessment but must not be used to redesign the formulation and claim the same test as confirmation.
