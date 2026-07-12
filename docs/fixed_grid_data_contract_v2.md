# Fixed-Grid Primal And Sensitivity Data Contract v2

Status: v2 schema, readers, and semantic validation implemented; solver writers
and G2 case-compiler integration pending. **Implementation required.**

This document defines the JSON summary layer that binds fixed-grid primal
values and cellwise gradient arrays to the generic problem contract in
`problem_contract_v2.md`. The v1 field/grid rules in
`fixed_grid_data_contract.md` remain authoritative for existing v1 VTI
artifacts until v2 writers are integrated.

The implemented canonical readers and validators are in
`src/cfd_sdf/fixed_grid_artifacts.py`.

## Common Problem Binding

Both v2 summary kinds require:

| Field | Rule |
| --- | --- |
| `schema_version` | Must be `2`. |
| `kind` | `fixed_grid_primal_summary` or `fixed_grid_sensitivity_summary`. |
| `problem_id` | Must equal the loaded problem specification ID. |
| `problem_spec_sha256` | Exactly 64 lower-case hexadecimal characters and, during semantic validation, equal to the canonical problem hash. |
| `execution_ready` | Boolean equal to the derived problem-spec value; it is not solver-convergence evidence. |
| `flow_case_ids` | Non-empty, unique list of declared flow-case IDs covered by the summary. |
| `status` | Producer-defined non-empty status text. |

The canonical Python value is
`ProblemBinding(problem_id, problem_spec_sha256, execution_ready)`.

## Primal Summary v2

Responses are keyed by both operating point and response ID. Objectives and
constraints are already aggregate values and do not carry a flow-case field.

```json
{
  "schema_version": 2,
  "kind": "fixed_grid_primal_summary",
  "problem_id": "generic_external_aero",
  "problem_spec_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "execution_ready": true,
  "flow_case_ids": ["straight", "yawed"],
  "status": "converged",
  "response_values": [
    {
      "flow_case_id": "straight",
      "response_id": "rotated_force",
      "value": 12.4,
      "units": "N",
      "status": "converged",
      "source": "solver.force"
    },
    {
      "flow_case_id": "yawed",
      "response_id": "pitch_moment",
      "value": -0.04,
      "units": "N_m",
      "status": "converged",
      "source": "solver.moment"
    }
  ],
  "objective_values": [
    {
      "objective_id": "multipoint_objective",
      "value": 0.205,
      "units": "1",
      "status": "evaluated",
      "source": "weighted_responses"
    }
  ],
  "constraint_values": [
    {
      "scope": "aggregate",
      "constraint_id": "pitch_limit",
      "value": -0.04,
      "units": "N_m",
      "status": "evaluated",
      "source": "weighted_responses"
    },
    {
      "scope": "topology",
      "constraint_id": "solid_connectivity_nominal",
      "value": 0.0,
      "units": "1",
      "status": "evaluated",
      "source": "virtual_diffusion"
    }
  ]
}
```

`response_values` and `objective_values` must be non-empty.
`constraint_values` may be empty. Every quantity carries `value` (finite or
null), `units`, `status`, and `source`.

The canonical keys are:

- `ResponseKey(flow_case_id, response_id)` for flow-dependent values;
- the objective ID string for objective values; and
- `ConstraintKey(scope, constraint_id)` for constraints, where scope is
  `aggregate` or `topology`.

The scoped constraint key is intentional: an aggregate YAML constraint and a
policy-derived topology constraint may have the same textual ID without
colliding in the artifact namespace.

## Sensitivity Summary v2

Each binding maps one semantic derivative target to one array in the associated
fixed-grid sensitivity field artifact.

```json
{
  "schema_version": 2,
  "kind": "fixed_grid_sensitivity_summary",
  "problem_id": "generic_external_aero",
  "problem_spec_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "execution_ready": true,
  "flow_case_ids": ["straight", "yawed"],
  "status": "extracted",
  "gradient_bindings": [
    {
      "target_kind": "response",
      "flow_case_id": "straight",
      "response_id": "rotated_force",
      "scope": "flow",
      "design_variable_id": "rho",
      "array_name": "d_rotated_force_d_rho",
      "units": "N",
      "status": "extracted",
      "source": "solver.topology_sensitivity"
    },
    {
      "target_kind": "objective",
      "objective_id": "multipoint_objective",
      "scope": "aggregate",
      "design_variable_id": "rho",
      "array_name": "d_multipoint_objective_d_rho",
      "units": "1",
      "status": "derived",
      "source": "weighted_response_gradients"
    },
    {
      "target_kind": "constraint",
      "constraint_id": "pitch_limit",
      "scope": "aggregate",
      "design_variable_id": "rho",
      "array_name": "d_pitch_limit_d_rho",
      "units": "1",
      "status": "derived",
      "source": "weighted_response_gradients"
    },
    {
      "target_kind": "constraint",
      "constraint_id": "solid_connectivity_nominal",
      "scope": "topology",
      "design_variable_id": "rho",
      "array_name": "d_solid_connectivity_nominal_d_rho",
      "units": "1",
      "status": "evaluated",
      "source": "virtual_diffusion"
    }
  ]
}
```

`gradient_bindings` must be non-empty. The `GradientBinding` rules are:

| `target_kind` | Required semantic selector | Required scope | Forbidden selectors |
| --- | --- | --- | --- |
| `response` | `flow_case_id` and `response_id` | `flow` | `objective_id`, `constraint_id` |
| `objective` | `objective_id` | `aggregate` | `flow_case_id`, `response_id`, `constraint_id` |
| `constraint` | `constraint_id` | `aggregate` or `topology` | `flow_case_id`, `response_id`, `objective_id` |

Every binding also requires `design_variable_id`, unique `array_name`,
`units`, `status`, and `source`. Response flow cases must appear in the
summary's top-level `flow_case_ids`. Duplicate semantic derivative keys and
duplicate array names are rejected.

An objective or aggregate-constraint derivative may combine responses from
several flow cases; that is why it has aggregate scope and no single
`flow_case_id`. A topology derivative is independent of a flow response and
uses topology scope.

## v1 Non-Destructive Reader

`read_fixed_grid_primal_summary` and
`read_fixed_grid_sensitivity_summary` dispatch on `schema_version`. For v1,
they normalize the historical drag/downforce/objective/efficiency fields and
`d_*` metadata into the canonical Python structures without rewriting the
source JSON.

The normalized v1 binding is `legacy_front_wing`, has no problem hash, uses
`legacy_default` as its flow case, and is never execution-ready. Semantic
validation permits a v1 artifact only against a problem specification that was
itself produced by the legacy migration reader. This keeps the existing
capability evidence readable without presenting it as a native generic v2
artifact.

## Semantic Validation Against The Problem

Parsing establishes JSON shape and local uniqueness. Call one of the following
after loading the corresponding problem specification:

```python
validate_primal_summary_against_problem_spec(summary, spec)
validate_sensitivity_summary_against_problem_spec(summary, spec)
```

These functions verify:

- v1/native-v2 compatibility;
- exact `problem_id`, canonical hash, and `execution_ready` binding;
- every top-level flow case against `flow_cases[]`;
- every `ResponseKey` against the response's declared flow case;
- objective IDs against `objectives[]`;
- aggregate constraint IDs against YAML `constraints[]`; and
- topology constraint IDs against the deterministic IDs derived from
  `topology_policy`.

Passing semantic validation proves namespace consistency, not numerical
correctness, field-array presence, mesh compatibility, solver convergence, or
gradient accuracy. Existing field/grid checks remain necessary, and v2 solver
writers plus G2 compiler integration are still **implementation required**.
