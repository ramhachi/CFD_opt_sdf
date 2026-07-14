# Agent Delegation Policy

The configured Codex model for this workspace is `gpt-5.6-sol`.  For every
decision that materially affects physical correctness, numerical validation,
OpenFOAM semantics, artifact provenance, public contracts, or the roadmap,
the lead agent must first delegate a bounded review to a sub-agent task named
`sol_<topic>`.

The lead agent must provide the review agent with the competing options and
available evidence, then use its conclusion before implementing the decision.
Routine mechanical edits, test execution, and already-decided implementation
work do not require a separate review.

When a `sol_` review changes a prior assumption, preserve the failed evidence,
update the roadmap or decision record as appropriate, and do not hide the
failure by changing signs, thresholds, or acceptance criteria.
