# Research Memory Gate

Before Nova spends compute on a hypothesis, the evidence gate compares the proposal with durable experiment memory.

## Dispositions

`NEW_HYPOTHESIS` means no prior experiment exists for the hypothesis fingerprint.

`DUPLICATE_EVIDENCE` means the same hypothesis fingerprint was already evaluated on the same dataset bytes. The proposal is blocked; tuning the same evidence again is not considered new research.

`INDEPENDENT_VALIDATION` means the hypothesis has prior evidence, but the supplied dataset is different. This is allowed only as an explicit validation experiment, not as a license to retune against the original test result.

## Safety rules

The gate hashes dataset bytes rather than trusting filenames. If old evidence is unavailable, the gate does not assume it matches current evidence.

The gate has no authority over execution and does not classify a strategy as profitable. It only answers whether the evidence reuse pattern is permitted by the research process.
