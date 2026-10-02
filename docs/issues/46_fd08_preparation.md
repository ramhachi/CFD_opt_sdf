# FD-08 preparation (2026-10-02)

## Scope and dependency

This is solver-free preparation only. Issue #44 has not frozen the production
operator yet. FD-08 must use the composite Candidate C moment blend plus
`normal_floor=0.25` body, on the same backend, flow_24, time window and v17
canonical state. No solver, calibration, epsilon selection, uncertainty fit,
formal criteria registration or qualification run was performed here. The
FD-06 upstream noise observation is intentionally not used as a Candidate C
resolution floor.

After #44 freezes the operator, calibration must determine Candidate C's own
micro-response scale. Only then can its epsilon ladder, independently measured
absolute response resolution floor and uncertainty model be frozen and
registered. Formal evidence must come from 33 new qualification runs, with
run IDs disjoint from calibration. The 5% relative plateau condition,
resolution floor and sign consistency are independent gates. A response at or
below the frozen resolution floor is `UNRESOLVED`, never `PASS`.

## Preparation change

Added `src/cfd_sdf/candidate_c_identity.py` and expanded
`src/cfd_sdf/fd08_contract.py`. The identity loader fails closed until the
append-only #44 contract and matching sidecar exist, then checks the exact
composite body identity, pinned Julia source paths and hashes, wrapper
parameters, and all six literal-false qualification flags. A verified source
identity is not physical qualification.

The preflight checks caller-supplied, disjoint calibration/formal run IDs;
exactly three baseline rows and a complete 3-direction × 5-epsilon × 2-sign
inventory; Kaggle T4 as the caller-declared formal backend; `flow_24`,
`[80,120] tU/L`, and canonical v17 state/Float32 phi bindings; and requested
versus actual in-memory Float32 perturbation values, including changed-node
and magnitude summaries. These checks do not verify Kaggle's runtime identity,
the source/runner inventory, artifact file hashes, or that named runs actually
executed as new solver runs. A renamed historical artifact cannot count as a
fresh execution. The design checker records `fresh_solver_execution_verified`
and `formal_qualification` as false. It writes no criteria and selects no
directions, epsilon ladder, uncertainty model, or resolution floor. The verdict
helper only checks a supplied summary; a strictly positive independently
measured resolution floor, the 5% relative plateau term, and sign consistency
remain separate.

## Verification

- Focused: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_fd08_contract.py` — **5 passed**.
- Full compile: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall -q src tests` — **passed**.
- Full suite: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` — **36 failed, 1231 passed, 5 skipped**. Compared sorted failure IDs with baseline JSON SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`: **0 new IDs, 1 baseline ID resolved** (`test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`).
- `git diff --check` — passed.
- The first suite invocation without local ignored fixtures had 38 failures; one extra was `test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity`, which could not load the worktree-local v17 NPZ. I created an isolated ignored fixture directory with copies of the existing v17 NPZ/raw inputs and the referenced smoke ProblemSpec YAML, then reran. Logs: [`work/fd08_preparation/full_pytest_before_local_fixture.log`](../../work/fd08_preparation/full_pytest_before_local_fixture.log), SHA-256 `8b3b2ccae3c9175dc3ea8a365db9f04b70f6dac0a5061d43214bafbef8ec1ff1`; [`work/fd08_preparation/full_pytest_with_local_fixtures.log`](../../work/fd08_preparation/full_pytest_with_local_fixtures.log), SHA-256 `b3b958bb8e3da682736e10812875bcc5b0141e2a5bb7f8dbbc83f9f5794027c5`.
- Evidence class: contract/readiness validation only; no CFD, calibration,
  formal FD, gradient, physical-force, or qualification evidence.

## Artifacts

- `src/cfd_sdf/fd08_contract.py`: SHA-256 `ea4e5481e5f9afa9aecf4ad390bbdac313aa8e510f21cb4f21a19708489b1ebc`.
- `tests/test_fd08_contract.py`: SHA-256 `5f8d05d42af48e7fccffb4c396caa7d7bf2cf9c1a379c5a73f3d73b382f6b714`.
- Full-suite logs are under ignored `work/fd08_preparation/`; hashes are listed above. Criteria, measurement and solver artifacts were not created.
- Commit SHA is reported after push.

## Parent review checkpoint, 2026-10-02

The hashes above describe the worker's initial preparation snapshot. Parent
commit `c69c6fe` added the repository-local `src` import bootstrap to the test,
so the shared editable environment cannot accidentally test another worktree.
The current test SHA-256 is
`dfd94dcf431dbad571d2bbb468e78dd64eb7acfa9e845221970c3c14cdd8dc14`.
The contract module hash is unchanged. The literal focused pytest command
passed all five tests; compileall passed. Integration used `merge --no-ff`.

The one formerly failing baseline test became runnable because its ignored
ProblemSpec fixture was copied into this worker's local `work/` directory.
That failure-ID removal is fixture availability, not a source bug repair.
No calibration, immutable formal criteria, or fresh 33-run qualification set
has been created. This remains preparation evidence only.

## Registration and evidence bindings audited after integration

The existing v17 FD-05 record is a protected historical reference, not the
future FD-08 criteria. Its criteria file SHA-256 is
`9cd5e3e35ac779ed937f4516421d82fbd40820dec2ae556817a4ff3ab007918e`
(criteria identity `f9ee9cb265f928aade278b3027f90212292a8c01ac0719a7fd8e7799d387f12f`). It identifies the canonical state file
`sdf_design_state.npz` (SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`),
canonical Fortran-order float32 phi bytes (SHA-256
`e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`),
and v17 state identity `02f48f64…`. Its historical flow is `flow_24`, with
the exact endpoint-clipped trapezoidal physical-time mean over `[80,120]`
`tU/L`; the primary outputs are drag and downforce in N, with direction
derivatives in N/m. This window and state are the required comparison
bindings for FD-08, subject to re-verification against the actual new input
inventory and operator-frozen registration.

The former 33-run registration contained three baseline repetitions
(`baseline_A/B/C`) plus `3 directions × 5 historical epsilons × 2 signs`.
Its direction IDs were `D0_interface_offset`, `D1_filtered_seed11`, and
`D2_filtered_seed2026`; its old epsilon values were 0.5, 1, 2.5, 5, and
10 mm. Those directions, values, perturbation files, hashes, and results are
protected history. The fact that they total 33 does not authorize their
reuse for Candidate C. FD-08 must create its own complete fresh qualification
inventory after calibration. It must explicitly define baseline repetition
count and a rectangular direction × epsilon × sign map whose run IDs total
exactly 33. If the frozen calibration-selected ladder and chosen directions
do not fit that total, the formal campaign must not be registered as 33 by
silently dropping cells or reusing calibration runs.

The old registered runtime reference was Kaggle T4, Julia 1.12.6,
WaterLily 1.8.0, KernelAbstractions, CUDA.jl 6.3.1 and CUDA runtime 12.8.0.
Those values describe historical W3/W4 evidence. The new run must save and
hash its own runtime identity; it cannot claim identity by copying these
reference values. The source identity must include the frozen composite
operator (Candidate C moment blend **and** `normal_floor=0.25` body), the
actual WaterLily job/runner, and criteria/host verifier hashes.

For every calibration and formal run, the future registrar/runner record
must bind the direction bytes and both the requested epsilon and the actual
float32 perturbed phi file hash. It must calculate a nonzero change from the
canonical float32 phi (including changed-node count and an explicit magnitude
summary) so a nominal epsilon that rounds away cannot be accepted. Each run
must preserve the raw force-history artifact and its hash, the source/runtime
identity and hashes, exact-window host recomputation, and primary force in N.
The existing host force pipeline uses force-on-body wrappers; these first
negate WaterLily's unmodified API reaction force, then project
`drag=+Fx_body` and `downforce=-Fz_body`. The criteria's solver-force values
are scaled by `rho*U^2*dx^2` to N (for the reference flow, `1/900 N` per
solver-force unit). Any new evidence must name raw API forces, body-force
components, projections, solver scaling, and physical N as distinct values
to prevent a second sign flip.

The preparation helpers validate supplied contracts and inventories; they do
not create criteria, runner inputs, calibration measurements, or saved
runtime/force records. Reuse the existing FD runner, dataset manifest and host
recomputation path for execution artifacts. Calibration must use Candidate C
measurements, not the upstream FD-06
3–4.5e-4 N diagnostic. Its own response-resolution floor must be recorded as
an independent absolute N term, alongside the unchanged 5% relative plateau
term and sign consistency. A response at/below that independently frozen
floor is `UNRESOLVED`, not `PASS`. Calibration and formal run namespaces and
all artifact paths must be disjoint; calibration evidence is never reused in
the formal verdict.

No immutable FD-08 criteria, numeric epsilon ladder, resolution floor,
uncertainty model, measurement artifact, or qualification result was created
by this audit. The #44 composite operator contract remains unfrozen.

The preceding paragraph preserves the state at the original preparation
checkpoint. The following addendum supersedes it only for the operator identity
freeze and registrar/preflight implementation status.

## Registrar/preflight preparation addendum (2026-10-02)

The shared #44 identity record is now present on the integration branch. The
loader passed against that record and its Julia source files: identity
`candidate_c_moment_blend+normal_floor_0.25`, contract SHA-256
`516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`, six
qualification flags literal `false`, and `physical_qualification=false`. The
new preflight reuses the immutable sidecar/JSON loader from
`criteria_supersession.py`; it does not change or register criteria.

Verification on the issue worktree:

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_candidate_c_identity.py tests/test_fd08_contract.py` — **13 passed**.
- `.venv/bin/python -m compileall src tests` — **passed**.
- `.venv/bin/python -m pytest -q` — **36 failed, 1294 passed, 5 skipped**. The failure-ID set was compared with `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`): **0 new IDs; 1 baseline ID resolved**, `tests/test_canonical_objective.py::test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`.
- `git diff --check` — **passed**.

Evidence class is immutable contract identity and local preflight validation.
No solver, calibration, immutable FD-08 criteria, formal run inventory
registration, or qualification measurement was started. The 33-row design
checker accepts measured, caller-supplied epsilon values and remains a
validator; the resolution floor remains unset until independent Candidate C
calibration. Its run IDs and caller-declared T4 metadata do not establish fresh
solver executions or actual device/runtime identity; those remain requirements
for the future Kaggle runner and host verifier.
