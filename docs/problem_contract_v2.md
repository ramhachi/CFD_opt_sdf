# Generic Aerodynamic Optimization Problem Contract v2

Status: implemented contract layer (G1)

This document defines the solver-independent input contract for optimizing an
external-aerodynamic object whose topology may change. The front wing is one
complex integration benchmark for this contract; it is not the contract's
coordinate system, response model, or geometry definition.

The implemented parser and canonicalizer are in `src/cfd_sdf/problem_spec.py`.
The complete example is `examples/generic_problem_v2/project.yaml`.

## Scope

Version 2 covers a rigid, single-material design on an explicitly declared
coordinate frame, one or more flow cases, STL geometry roles, named responses,
weighted objectives and constraints, and typed topology policies. The current
executable profile is a uniform Cartesian grid.

The contract parser does not itself compile or run a solver case, inspect STL
mesh quality, prove feature resolution, or prove target-physics accuracy. The
G2 compiler consumes this contract; G2 runtime qualification and the G3--G4
gates remain separate as defined in `phase_plan.md`.

## Authoritative YAML Fields

Unknown root keys are rejected. Identifiers use lower-case snake case and must
match `^[a-z][a-z0-9_]{0,63}$`.

| Field | Meaning and v2 rule |
| --- | --- |
| `schema_version` | Must be `2`; missing or `1` selects the legacy migration reader. |
| `problem_id` | Stable ID used to bind all downstream artifacts. |
| `units` | Must declare the SI base units `length: m`, `time: s`, and `mass: kg`. |
| `coordinate_frame` | `id`, `origin_m`, and an orthonormal right-handed `basis` containing unit vectors `x`, `y`, and `z`. |
| `grid` | `kind`, positive `voxel_size_m`, and non-negative `padding_m`. Optional `domain_bounds_m.lower`/`upper` declare an explicit canonical Cartesian transfer domain; each finite extent must be positive and an integer multiple of `voxel_size_m` (relative tolerance `1e-10`, absolute tolerance `1e-12 m`). `uniform_cartesian` is executable in v2; `octree_amr` is reserved in the contract but is not execution-ready. |
| `reference_values` | Optional mapping with positive `area_m2`, positive `length_m`, and `moment_center_m`. All three are required for `execution_ready: true`. |
| `geometry_regions[]` | Portable relative STL paths with `id`, typed `role`, and `file`. |
| `flow_cases[]` | One or more named flow cases with a nonzero freestream vector, fluid properties, optional turbulence declaration, boundary-condition mapping, motion-profile mapping, and optional typed `convergence_criteria`. |
| `responses[]` | One or more named flow-dependent quantities. Each response binds exactly one `flow_case_id`. |
| `objectives[]` | One or more named weighted response aggregates with `sense: minimize` or `maximize`. |
| `constraints[]` | Zero or more named weighted response aggregates with `relation: <=`, `>=`, or `==` and a finite `limit`. |
| `topology_policy` | Root groups, solid and void connectivity modes, optional manufacturing lengths, and optional erosion radius. |

`grid` may carry future kind-specific options. Turbulence, boundary-condition,
motion-profile, and response `options` mappings intentionally preserve
solver-independent extension data. G2 must reject an option that its selected
solver profile cannot compile instead of silently ignoring it.

### Flow convergence criteria

When `flow_cases[].convergence_criteria` is omitted, canonicalization writes
the conservative defaults below. Partial mappings inherit the same defaults;
unknown keys are rejected. Residuals and normalized ratios are dimensionless.

| Field | Default | Validation and gate meaning |
| --- | ---: | --- |
| `primal_final_residual_max` | `1e-6` | Positive and at most 1; every final primal field residual must satisfy it. |
| `normalized_mass_imbalance_max` | `1e-4` | Between 0 and 1; the absolute final normalized imbalance must satisfy it. |
| `response_stationarity_window` | `20` | Integer from 2 to 100000; every response must provide this many trailing samples. |
| `response_relative_range_max` | `1e-3` | Between 0 and 1; `(max-min)/max(abs(values))` over the trailing window must satisfy it, with an all-zero window defined as zero. |
| `adjoint_final_residual_max` | `1e-6` | Positive and at most 1; every final adjoint field residual for every flow response must satisfy it. |

The G2 convergence evaluator is fail-closed. A solver end marker is required,
but convergence text alone is never sufficient: missing, non-finite, or
undersized numerical histories produce `fail`. A flow with no evidence is
`not_evaluated`; neither state is qualified. Multipoint qualification passes
only when every flow case passes.

## STL Geometry Roles

All geometry inputs remain STL-only in v2. A path must be relative to the YAML
file and end in `.stl`.

| Role | Contract meaning |
| --- | --- |
| `fixed_solid` | Non-design solid retained throughout optimization. |
| `initial_design` | Initial material/surface used to seed the design variable. |
| `design_domain` | Region in which topology is allowed to change. At least one is required for `execution_ready: true`. |
| `forbidden_region` | Region from which optimized material must be excluded. |
| `root` | Mount/contact region that may be collected into a named topology root group. |

The parser validates role names, paths, and references. Watertightness,
orientation, self-intersections, degeneracy, unit plausibility, and actual
mask resolution are G3 mesh-preflight responsibilities.

## Typed Topology Policy

`solid_connectivity` and `void_connectivity` share the same typed modes:

| Mode | Required/forbidden fields |
| --- | --- |
| `disabled` | No root groups or component bound; `evaluate_eroded` must be false. |
| `single_component` | No root groups; `max_components` is absent or `1`. |
| `root_connected` | Requires one or more `required_root_group_ids`. |
| `required_root_groups` | Requires one or more `required_root_group_ids`. |
| `bounded_component_count` | Requires a positive `max_components`. |

Each `root_groups[].region_ids` entry must reference a geometry region whose
role is `root`. If either connectivity policy sets `evaluate_eroded: true`, a
positive `erosion_radius_m` is required.

The following stable topology constraint IDs are derived from the policy in
this order:

1. `solid_connectivity_nominal`, plus `solid_connectivity_eroded` when enabled.
2. `void_connectivity_nominal`, plus `void_connectivity_eroded` when enabled.
3. `minimum_solid_width` when `minimum_solid_width_m` is set.
4. `minimum_void_width` when `minimum_void_width_m` is set.
5. `minimum_gap` when `minimum_gap_m` is set.

These IDs use `scope: topology` in fixed-grid artifacts. They are not members
of the YAML `constraints[]` collection, whose IDs use `scope: aggregate`.

## Flow Cases And Motion

Every flow case declares:

- `id` and `freestream_velocity_mps` in the declared coordinate frame;
- `fluid.model`, positive `density_kg_m3`, and positive
  `dynamic_viscosity_pa_s`;
- optional `turbulence.model` plus solver-independent options;
- optional `boundary_conditions` mapping;
- zero or more named `motion_profiles`, each represented by a mapping.

This is a declarative interface. The G2 compiler and manifest translate the
currently supported subset. Translation motion and moving-wall profiles are
implemented. Rotating-wall motion and unsupported response/solver options must
fail explicitly until their compiler paths are implemented.

## Response Kinds

The v2 response registry has exactly five built-in kinds:

| Kind | Required response fields |
| --- | --- |
| `force` | `flow_case_id` and a nonzero `direction`. |
| `moment` | `flow_case_id` and a nonzero `direction`; the problem-level moment centre supplies the reference point. |
| `pressure_loss` | `options.from_boundary_id` and `options.to_boundary_id`, which must differ. |
| `flow_rate` | `options.boundary_id`. |
| `plugin` | `options.plugin_id`; other plugin options are preserved. |

Directions are allowed only for force and moment. Every response is addressed
downstream by `ResponseKey(flow_case_id, response_id)`, so the same physical
idea at two operating points remains unambiguous.

## Weighted Objectives And Constraints

Each term is a triple `(coefficient, flow_case_id, response_id)`. The response
must belong to that flow case, and at least one coefficient in an aggregate
must be nonzero.

For objective `j`, the declared aggregate is

```text
J_j = sum_k coefficient_k * response(flow_case_id_k, response_id_k)
```

and `sense` states whether it is minimized or maximized. An aggregate
constraint uses the same sum and applies the declared `relation` to `limit`.
Writers and solver compilers must preserve physically compatible units or
explicit nondimensionalization; the G1 parser validates references and finite
coefficients but does not perform dimensional analysis.

Objective values and gradients use the objective ID with aggregate scope.
YAML constraint values and gradients use
`ConstraintKey(scope="aggregate", constraint_id=...)`. Policy-derived
topology constraints use the same key type with `scope="topology"`.

## `execution_ready` And G3 Mesh Preflight

`execution_ready` is derived metadata, not a user-authored YAML switch. A
native v2 specification receives `true` only when:

- `grid.kind` is `uniform_cartesian`;
- area, length, and moment centre are all present;
- at least one `design_domain` STL role exists; and
- every flow case has a non-empty boundary-condition mapping and a turbulence
  declaration.

A migrated v1 specification is always false. A true value means the G1
contract contains the minimum declarations supported by the current profile.
It does not mean that referenced files exist, the STL is usable, feature
lengths span enough cells, the requested boundary conditions were compiled,
or a solver will converge.

Those checks belong to G2 case compilation and the G3 geometry/resolution
preflight. A solver writer must not treat `execution_ready: true` as permission
to bypass either gate.

## Canonical Hash And Snapshot

Canonicalization converts the parsed problem to deterministic JSON with
sorted keys, compact separators, SI values, normalized tuples/lists, and no
source path or migration record. SHA-256 of those UTF-8 bytes is
`problem_spec_sha256`. Every v2 primal and sensitivity summary binds both
`problem_id` and this digest.

`write_problem_spec_snapshot` writes:

- `kind: cfd_optimization_problem_spec`;
- `schema_version: 2`;
- the canonical `problem` object;
- `problem_spec_sha256`; and
- migration provenance, notes, and `execution_ready`.

Changing authoritative problem content changes the hash. Moving an unchanged
portable problem directory does not.

## v1 Migration

When `schema_version` is absent or `1`, the reader creates an in-memory v2 view
without rewriting the original YAML. It maps the legacy operating point to
`legacy_default`, creates `drag` and `downforce` force responses, converts the
legacy objective/efficiency expression into weighted aggregates, and maps
recognized STL entries to v2 geometry roles.

The migrated binding uses `problem_id: legacy_front_wing` and remains
`execution_ready: false` because v1 does not fully declare reference values,
boundary conditions, or generic topology policy. Migration preserves access
to existing evidence; it does not upgrade that evidence into a generic v2
solver run.

## CLI Validation

Validate the generic example and write its canonical snapshot and report:

```powershell
.\.venv\Scripts\cfd-sdf.exe validate-problem-spec examples\generic_problem_v2\project.yaml --output-dir examples\generic_problem_v2\contract_output --require-execution-ready
```

The command reports the canonical hash, migration state, execution-ready flag,
geometry-role counts, declared flow/response/objective IDs, aggregate
constraint IDs, and derived topology constraint IDs. It performs contract
validation only; it does not run G2 or G3.

The corresponding fixed-grid artifact namespace is defined in
`fixed_grid_data_contract_v2.md`.
