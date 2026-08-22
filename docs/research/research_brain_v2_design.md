# Research Brain v2 Design

## Goal

Remove experiment-family assumptions from the researcher layer. Nova must choose among competing mechanisms before selecting an experiment.

## Required reasoning sequence

1. Define the research question precisely.
2. State relevant priors and assumptions.
3. Generate at least two genuinely different mechanisms when the problem permits it.
4. Identify observable predictions that differ across mechanisms.
5. Identify confounders and alternative explanations.
6. Rank experiments by expected information value, feasibility, and research cost.
7. Predeclare falsification and stopping rules.
8. Separate development exploration from confirmation.
9. Update structured research state after every result.

## V2 must not contain

- a hard-coded technical-indicator family
- a hard-coded trading direction
- a hard-coded market mechanism
- a mandatory profitable outcome
- an implicit instruction to keep searching after repeated failures

## V2 must contain

- mechanism genealogy
- experiment genealogy
- explicit uncertainty
- multiple-testing/search-budget accounting
- confirmation firewall
- state transition after failure
- state transition after null results
- state transition after positive results
- explicit stop/reject decision

## Assessment boundary

The model proposes research. Deterministic experiment code produces evidence. The external assessor judges whether the inference is warranted. The researcher must not self-certify an edge.
