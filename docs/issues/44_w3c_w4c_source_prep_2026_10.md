# #44 W3-C/W4-C source preparation (not a registered round)

Status: source preparation only. This note does not preregister criteria, qualify
Candidate C, or authorize a T4 run. Final W3-C/W4-C rounds remain blocked on the
#44 operator/fixture review and parent approval of immutable criteria.

## Preserved evaluation contracts

The copies retain the current W3 v17 primal evaluator and the W4 v17 sensitivity
evaluator. W3 uses the existing single physical-profile primal fixture, its
T4/J1.12.6/WaterLily 1.8.0 backend identity, exact-window force reporting,
pressure-plus-viscous closure, stationarity check, source checks, and thresholds
from `docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json` (SHA-256
`00af9ed92111b48a69d0eebebfa143db7e23c7caee322bb88cdb6ac36ff2e608`). W4
retains the v17 case order `flow_16`, `flow_24`, `flow_32`,
`domain_xplus1m_16`, each case's current flow mapping, [80,120] window,
stationarity and force gates, and T4/J1.12.6/WaterLily 1.8.0 backend from
`docs/evidence/kaggle_w4_v17_sensitivity_criteria_2026_09.json` (SHA-256
`5eceb62c17e347679cdadc88c68266e7fe00b392da40a8029ed3544a002e0f01`). No
numerical gate or case definition was edited in these copies. The W3/W4 host
verifiers and shared kernel-level evaluators are reused by criteria input
identity, not copied or changed here.

## Draft operator and object lifetime identity

The job copies load the existing `WaterLilyNormalFloorBody.jl` and
`CandidateCWaterLilyBody.jl` implementations. Their intended immutable operator
identity is the composite `candidate_c_moment_blend+normal_floor_0.25` with the
existing Candidate C transition width `1.1444091796875e-4` in solver units.
The normal-floor candidate keeps the registered case's flow origin and spacing.
The simulation body is the outer Candidate C wrapper around the candidate plus
the existing moving ground, so the Candidate C `measure!` specialization is
used for the complete union. Its candidate-only force integration body is the
outer Candidate C wrapper around the normal-floor candidate alone, preserving
the existing W3/W4 exclusion of the ground from reported candidate force.
Ground plane and velocity remain `z=0` and `u_x=+1` solver units.

The device SDF owner remains held by the existing `OwnedV16Run` and existing
`GC.@preserve` scopes around solver/measurement execution. The copies add a
T4-time `isbitstype` guard on the composed body; it is a CUDA argument-shape
precondition only. The registered smoke, CUDA visibility, runtime and memory
checks remain those of the copied v17 runners.

## Isolated future identities

The draft kernel metadata uses `ramhachi888/cfd-opt-sdf-w3-v17-candidate-c`
and `ramhachi888/cfd-opt-sdf-w4-v17-candidate-c`; dataset metadata uses
`ramhachi888/cfd-opt-sdf-v17-candidate-c` and
`ramhachi888/cfd-opt-sdf-v17-w4-candidate-c`. The preparers and runners reject
any criteria whose state label, dataset, composite operator, or outer body
composition does not match those draft identities. Their defaults deliberately
point at criteria files that do not exist yet, so the drafts cannot launch a
solver from the current checkout.

An eventual criteria registrar must bind the exact new job, runner, metadata,
dataset-preparer, Candidate C source, normal-floor source, canonical v17 state,
project/manifest, existing evaluator and host verifier hashes. W4 must depend on
the host-verified W3-C result under its own preregistered dependency. This file
does not establish that binding or change any qualification flag.

## Validation class and limits

The source-preparation tests check isolated identities, Candidate C composition,
owner lifetime and the unchanged W4 case/time matrix. Python syntax and Julia
source parsing are static/capability checks. No WaterLily `Simulation`, solver
step, Kaggle submission, or GPU calculation is performed by this preparation.
It does not qualify long-thin-plate or moving-ground physical behavior, fluid
mass conservation, stationarity, or production use. Those remain separate
evidence requirements under #44.
