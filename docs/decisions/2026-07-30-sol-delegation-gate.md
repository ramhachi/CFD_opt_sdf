# Sol review gate for material technical decisions

Date: 2026-07-30

## Decision

Use an operational Sol review gate for material technical decisions.  The
lead delegates a bounded `sol_<topic>` review before selecting an approach
that can affect physical correctness, numerical validation, OpenFOAM
semantics, artifact provenance, public contracts, acceptance criteria, or the
roadmap.

Routine mechanical work and implementation of an already-recorded decision
remain exempt, so the gate does not turn every edit into a blocking review.

## Rationale

The earlier policy specified the affected areas but did not make the trigger,
review inputs, or decision-record requirement explicit.  The strengthened
policy makes the delegation auditable while retaining short-lived implementation
workflows.

## Considered options

1. Keep the previous high-level wording. Rejected: the meaning of a difficult
   decision and the evidence record remain ambiguous.
2. Require a Sol review for every edit. Rejected: it slows mechanical changes
   without improving the validity of already-decided implementation work.
3. Add explicit triggers, required review inputs, and a decision-record rule.
   Selected.

## Evidence

`sol_delegation_policy` reviewed the three options on 2026-07-30 and
recommended option 3. The review found it preserves the existing requirement
for material physical and numerical decisions while avoiding unnecessary
review overhead.
