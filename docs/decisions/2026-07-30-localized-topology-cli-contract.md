# Localized topology evaluation CLI contract

Date: 2026-07-30

## Decision

Expose the immutable localized-reference topology check only as:

```text
cfd-sdf evaluate-localized-reference-topology PROJECT_YAML REFERENCE_BUNDLE OUTPUT_DIR
```

The command passes no injected resource probes or policy/tuning controls to
the evaluator.  On a completed physical outcome it writes exactly one
sorted-key JSON object to stdout with kind
`localized_reference_topology_evaluation`, the fixed report path, status, and
reasons.  `success` exits zero; an atomically published physical `rejected`
outcome exits one.  Invalid/tampered inputs, pre-existing outputs, resource
refusals, and evaluator I/O or backend failures do not emit the outcome JSON
and do not create an outcome report.

## Rationale

The topology policy, 0.5 discrete threshold, six-face neighbourhood, and
resource floor are hash-bound evaluator/bundle contract values.  CLI switches
would let a caller change a qualification result without changing the bound
evidence.  A separate outcome JSON permits automation to distinguish a valid
physical rejection from an invalid evaluation attempt.

## Considered options

1. Expose threshold, resource, and policy controls in the command. Rejected:
   this weakens immutable evidence provenance.
2. Return exit zero for both physical outcomes. Rejected: shell automation
   could overlook a policy rejection.
3. Use the three positional inputs, evaluator production defaults, a
   machine-readable outcome, and exit one only for published rejection.
   Selected.

## Evidence

`sol_topology_cli_contract` reviewed the alternatives and selected
option 3 on 2026-07-30.  The existing evaluator tests demonstrate atomic
publication for rejected states and no publication for bad input or insufficient
resources in `tests/test_localized_reference_topology.py`; the CLI tests bind
the command-level stdout, exit, and no-tuning contract.
