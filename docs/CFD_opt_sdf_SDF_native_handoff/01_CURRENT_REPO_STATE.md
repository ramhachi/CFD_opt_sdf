# Current repository state snapshot

Date: 2026-09-26

Repository:
`https://github.com/ramhachi/CFD_opt_sdf.git`

Branch:
`feat/p0-openfoam-closed-loop`

Verified HEAD:
`ebdd01f293636b2fc736885a1032d466e6632e9a`

Commit message:
`Register Stage S reduced-basis FD v2 contract and pass S0R/S1R`

Parent:
`dfe0952b3999b9443bd71c667d586cb6bbb8cdce`

## Current meaning

The repository has already advanced beyond the P21/domain-convergence commit. The K=16 reduced-basis Stage S v2 contract has been registered and solver-free S0R/S1R has passed.

Therefore the migration must **not** be written as if S0R/S1R still need to be performed. Instead:

- preserve the result as diagnostic/reference evidence;
- do not launch S2;
- mark the B-spline reduced-basis path as superseded for production optimization;
- branch into an SDF-native architecture.

## Preserve unchanged

The following are valuable scientific assets and should remain append-only/reproducible:

- Stage T density/filter/projection/RAMP/Brinkman lineage and Path-B evidence;
- v16 candidate and extraction lineage;
- repaired Stage S entry qualification;
- P21 moving-ground/freestream physical profile;
- expanded-domain v2 reference case;
- v2-v3 domain-convergence witness;
- force normalization and physical-profile hashes;
- Stage V body-fitted OpenFOAM verification infrastructure;
- immutable manifests, checkpoint identity, evidence hashes;
- continuous-adjoint failure diagnostics;
- K=16 reduced-basis S0R/S1R geometry/morpher evidence.

## Key verified repository modules

Existing SDF code:
`src/cfd_sdf/sdf.py`
currently primarily converts geometry/STL to signed-distance fields and supporting geometry arrays. It is not yet the canonical optimizer design state.

Existing design state:
`src/cfd_sdf/design_state.py`
currently contains `DensityDesignState`; retain it for Stage T reproducibility and introduce a separate canonical `SDFDesignState`.

Existing reduced-basis path:
`src/cfd_sdf/stage_s_reduced_basis.py`
explicitly defines K=16 smooth B-spline/control-point modes and centered-FD architecture. Freeze this path as reference.

Core architecture to retain/refactor:
- `problem_spec.py`
- `problem_spec_compiler.py`
- `canonical_objective.py`
- `nonlinear_acceptance.py`
- `extraction_qualification.py`
- `independent_verification.py`
- `cross_fidelity_ranking.py`
- `stage_v_physical_profile.py`

Legacy/reproduction-only paths:
- `design_transform.py`
- `stage_t_loop.py`
- `openfoam_oracle.py`
- `projected_restoration.py`
- `robust_fields.py`

Freeze as Stage-S diagnostic/reference:
- `stage_s_reduced_basis.py`
- `stage_s_surface_fd.py`
- `stage_s_adjoint_case.py`
- `stage_s_adjoint_qualification.py`
- `stage_s_geometry_jacobian.py`
- `stage_s_perturbation.py`

## Current gates

Keep these false/pending at the architecture fork:

- `shape_update_allowed = false`
- `sdf_gradient_qualified = false`
- `waterlily_reverse_cpu_qualified = false`
- `waterlily_reverse_cuda_qualified = false`
- `topology_birth_qualified = false`

No existing evidence should be rewritten to make the new architecture appear retroactively qualified.
