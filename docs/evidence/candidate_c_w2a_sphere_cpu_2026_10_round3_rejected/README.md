# Rejected W2a-C Round 3 pre-execution registration

This directory preserves Round 3 criteria, its source manifest and runner,
Julia job, and initialization-only preflight. It was rejected before any
numerical solver step. Criteria SHA-256:
`eecb4d1291032231f6b283c3aafabaf4b57c25e704c94601dbd710a825c5c540`; source
manifest SHA-256:
`14d0d4da783a07ee8fc7c3d640e6f1097c25fde13ebc4db2b93e3f3839f008ce`.

Review found the all-gates-pass path indexed `criteria["claims_supported"]`,
which does not exist in the registered schema (the key is
`claims_supported_if_all_gates_pass`). It also left `execution.output` and
`provenance.source_manifest` pointed at Round 2. Round 4 corrects those
references and tests the criteria schema lookup. No measurements occurred.
