# Agent Delegation Policy

The configured Codex model for this workspace is `gpt-5.6-sol`.

Before choosing an approach for a decision that may materially affect physical
correctness, numerical validation, OpenFOAM semantics, artifact provenance,
public contracts, acceptance criteria, or the roadmap, the lead agent must
delegate a bounded review to a sub-agent task named `sol_<topic>`.

This gate applies in particular when:

- multiple technically credible approaches exist;
- an assumption, threshold, discretization, boundary condition, sign
  convention, or acceptance criterion is being introduced or changed;
- a result is being interpreted as validation, qualification, or evidence for
  the roadmap; or
- a prior design decision may need revision.

The review request must state:

1. the decision to make;
2. the competing options;
3. the available evidence and known limitations;
4. the proposed acceptance criterion; and
5. the decision deadline or implementation scope.

The lead agent must consider the conclusion before implementation and record
the selected option and rationale in `docs/decisions/YYYY-MM-DD-<topic>.md`
when the decision changes a prior assumption, public contract, acceptance
criterion, or roadmap. The record must link or name the supporting evidence.

Routine mechanical edits, test execution, formatting, documentation wording
that does not change meaning, and implementation of an already-recorded
decision do not require a separate Sol review.

When a `sol_` review changes a prior assumption, preserve the failed evidence,
update the applicable decision record and roadmap, and do not hide the failure
by changing signs, thresholds, or acceptance criteria.
