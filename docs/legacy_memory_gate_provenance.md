# Legacy memory-gate provenance

Historical experiment records created before `dataset_sha256` was included in the JSON payload may still be evaluated when their recorded dataset path is available. The path is hashed only as a backward-compatibility fallback.

If neither an immutable stored fingerprint nor a readable legacy dataset path is available, the memory gate fails closed as `EVIDENCE_UNAVAILABLE` rather than assuming independent evidence.
