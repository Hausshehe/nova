# Nova Research Capability Benchmark v1

## Purpose

Measure whether Nova is becoming better at **finding an edge if one exists**, rather than merely producing more strategy candidates.

ChatGPT remains the independent external assessor. This benchmark measures Nova's research decisions before outcome evidence is revealed.

## Core principle

A good researcher reduces uncertainty efficiently. A profitable backtest is only one possible downstream consequence and is not itself the capability target.

## Blind decision packet

For each scenario Nova receives only:

- research question
- asset/timeframe
- permitted data boundaries
- transaction-cost assumptions
- prior research state and dispositions
- experiment budget
- confirmation-data boundary

Nova must decide what to investigate **before seeing the result of the proposed experiment**.

## Required output

1. Problem interpretation
2. Important assumptions
3. Plausible competing mechanisms
4. Rejected mechanisms and why
5. Key confounders
6. Primary discriminating experiment
7. Alternative experiments
8. Expected information from each outcome
9. Falsification criteria
10. Exploration budget and stopping rule
11. Confirmation boundary
12. Predicted next state for each major outcome
13. Next action

## Scoring

### Objective checks

- future/confirmation leakage
- repeated experiment violations
- budget violations
- post-result selection rules
- invalid causal claims
- missing cost assumptions
- missing falsifier
- missing stopping rule
- failure to incorporate prior dispositions

### Research-quality assessment

Score each 0-4:

- Problem understanding
- Assumption skepticism
- Mechanism diversity
- Mechanism plausibility
- Experiment discrimination
- Information value
- Causal validity
- Falsification discipline
- Failure learning
- Anti-overfitting discipline
- Uncertainty awareness
- Economic realism
- Stopping judgment

Maximum: 52.

## Important distinction

Agreement with ChatGPT is **not** the score. ChatGPT supplies an independent reference assessment and identifies important omissions or errors. Nova should be rewarded for justified research decisions, including justified disagreement with the reference.

## Progression

A later version should contain:

- synthetic problems with known mechanisms
- historical market problems with blinded outcomes
- adversarial scenarios designed to tempt indicator shopping
- failure-recovery scenarios
- budget-constrained experiment selection
- research-state consistency tests

Nova should improve on this benchmark after architectural changes. A higher score without preserved confirmation discipline is not an improvement.
