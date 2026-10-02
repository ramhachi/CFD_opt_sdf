# #44 W3-C/W4-C source preparation (not a registered round)

Status: source and registrar preparation only. The parent has frozen the
composite Candidate C identity in
`docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json` with
sidecar SHA-256 `516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`.
That freeze binds source and algorithm identity only; it does not qualify
physical behavior or authorize a T4 run. This preparation does not register
criteria or launch any solver.

## Preserved evaluation contracts

The W3 copy retains the actual v17 primal contract: one physical-profile
fixture, T4/J1.12.6/WaterLily 1.8.0 backend, exact-window force reporting,
pressure-plus-viscous closure, stationarity check, source checks and thresholds
from `docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json` (SHA-256
`00af9ed92111b48a69d0eebebfa143db7e23c7caee322bb88cdb6ac36ff2e608`). W4
retains the v17 case order `flow_16`, `flow_24`, `flow_32`,
`domain_xplus1m_16`, each case's flow mapping, [80,120] window, stationarity
and force gates, and T4/J1.12.6/WaterLily 1.8.0 backend from
`docs/evidence/kaggle_w4_v17_sensitivity_criteria_2026_09.json` (SHA-256
`5eceb62c17e347679cdadc88c68266e7fe00b392da40a8029ed3544a002e0f01`). The
kernel-level `evaluate_gates` functions remain AST-identical to the v17
versions. Draft builders assert unchanged numerical measurement, backend,
profile and (for W4) the full four-case matrix.

New C-specific host entry points call the existing v17 numerical verifiers
while checking C kernel/dataset identity, immutable operator identity, runner
outcome, exact Kaggle versions, terminal status and dataset inventory. W4-C
requires an exact host-verified W3-C PASS and state identity; a v17 W3 result
cannot satisfy that dependency. The criteria builders print unregistered
drafts only and do not write criteria or sidecars.

## Composite operator and source bindings

The jobs load the pinned `WaterLilyNormalFloorBody.jl` and
`CandidateCWaterLilyBody.jl`. The frozen composite identity is
`candidate_c_moment_blend+normal_floor_0.25` with Candidate C transition width
`1.1444091796875e-4` solver units. The normal-floor candidate preserves each
case's flow origin and spacing. The simulation body is the outer Candidate C
wrapper around the candidate and moving ground, so Candidate C's `measure!`
specialization applies to the complete union. Force integration uses the
outer Candidate C wrapper around the normal-floor candidate alone, excluding
ground force. Ground plane and velocity remain `z=0` and `u_x=+1` solver units.

The device SDF owner remains held by the existing `OwnedV16Run` and existing
`GC.@preserve` scopes. The composed body's T4-time `isbitstype` guard is only a
CUDA argument-shape precondition. All six qualification flags remain literal
false: `shape_update_allowed`, `fd_oracle`, `field_gradient`, `reverse`,
`optimizer`, and `topology`.

The C kernel identities are
`ramhachi888/cfd-opt-sdf-w3-v17-candidate-c` and
`ramhachi888/cfd-opt-sdf-w4-v17-candidate-c`. Dataset identities are
`ramhachi888/cfd-opt-sdf-v17-candidate-c` and
`ramhachi888/cfd-opt-sdf-v17-w4-candidate-c`. The preparers and runners use the
shared fail-closed `cfd_sdf.candidate_c_identity` helper, not a duplicate
operator definition.

The draft builders refresh source hashes against current bytes and leave the
historical v17 criteria untouched. This records existing W3 source-hash drift
explicitly instead of implying the old registered source set matches the
current tree. Parent review must materialize and register immutable W3-C
criteria before computation. W4-C registration must bind the actual
host-verified W3-C result. Final criteria must bind each C job, runner,
metadata, dataset preparer and C host verifier; frozen identity helper and
record; the imported legacy host evaluator and the identity helper's
`criteria_supersession.py` dependency; Candidate C and normal-floor bodies;
canonical v17 state; project and manifest; and inherited evaluator sources.
Host verification also enforces Kaggle metadata's GPU-enabled T4 machine shape
and internet setting.

## Validation class and limits

Focused tests check isolated Kaggle IDs, C composition and owner lifetime,
unchanged W3/W4 gate evaluators and W4 matrix. Python compilation and Julia
source parsing are static/capability checks. No WaterLily `Simulation`, solver
step, Kaggle submission or GPU calculation is performed by this preparation.
It does not qualify thin-plate or moving-ground physical behavior, fluid mass
conservation, stationarity or production use. Those remain separate evidence
requirements under #44.

Validation run on the prepared source tree:

- `.venv/bin/python -m pytest -q tests/test_candidate_c_w3_w4_source_prep.py tests/test_candidate_c_identity.py`: 11 passed.
- `.venv/bin/python -m compileall src tests`: passed.
- `.venv/bin/python -m pytest -q --tb=no`: 37 failed, 1323 passed, 5 skipped. The sorted failure IDs exactly match `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`): 0 new failures, 0 resolved failures. Full log: `docs/evidence/candidate_c_w3_w4_source_prep_2026_10/pytest.log` (SHA-256 `8b3ae3e878b5bd0ad08a98c8e90f768f4510dad400a984548f028eb26ef61630`).
- `julia --startup-file=no -e 'for p in ARGS; Meta.parseall(read(p, String)); println("PARSE_OK ", p); end' scripts/waterlily_w3_v17_candidate_c_job.jl scripts/waterlily_w4_v17_candidate_c_job.jl`: both files parsed.
- `git diff --check`: passed after source edits.
