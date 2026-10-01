# STEP-01 preparation (2026-10-02)

## Scope and dependency

This is solver-free preparation only. The finite-step oracle depends on the
composite Candidate C moment blend plus `normal_floor=0.25` production body
contract from #44, which is not frozen yet. No epsilon, directions, comparison
threshold, run set, or immutable criteria have been selected or registered;
no solver execution occurred.

STEP-01 is a separate finite-step response oracle for steps in the registered
range 0.1–0.5 h. It reports response changes in N and the corresponding
finite secants in N/m. These observations do not qualify a gradient and remain
separate from FD-08. Any later comparison with FD-08 slopes is descriptive and
must not be presented as gradient qualification.

## Preparation change

Added `src/cfd_sdf/step01_contract.py` and focused tests. The helper enforces
the stated step-fraction bounds and computes a force change and finite secant
from explicit N and m inputs. It does not define candidate directions, choose
step values within the range, or register criteria.

## Verification

- Focused: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_step01_contract.py` — **7 passed**.
- Full compile: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall -q src tests` — **passed**.
- Full suite: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` — **36 failed, 1233 passed, 5 skipped**. Compared sorted failure IDs with baseline JSON SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`: **0 new IDs, 1 baseline ID resolved** (`test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`).
- `git diff --check` — passed.
- The first suite invocation without local ignored fixtures had 38 failures; one extra was `test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity`, which could not load the worktree-local v17 NPZ. Rerun used an isolated ignored fixture directory with copies of the existing v17 NPZ/raw inputs and the referenced smoke ProblemSpec YAML. Logs: [`work/step01_preparation/full_pytest_before_local_fixture.log`](../../work/step01_preparation/full_pytest_before_local_fixture.log), SHA-256 `6337eb00883223bb87f20f0dcc0331de64283c3295f40651accb3b8d407d57dd`; [`work/step01_preparation/full_pytest_with_local_fixtures.log`](../../work/step01_preparation/full_pytest_with_local_fixtures.log), SHA-256 `79cbc35719da0a18c0cf818073e75cddb533785b3511e0f79fdd6aa11ffa6d8a`.
- Evidence class: contract/readiness validation only; no CFD, formal secant,
  gradient, physical-force, or qualification evidence.

## Artifacts

- `src/cfd_sdf/step01_contract.py`: SHA-256 `c462b1ad304d31659d86a7e29a8123e266afea1efb6ebdfe2f767bc2b27ca732`.
- `tests/test_step01_contract.py`: SHA-256 `bde3baa2130f3161d40ad9e19dcfa1b88dc7e3a8c71eede45829f1644f124071`.
- Full-suite logs are under ignored `work/step01_preparation/`; hashes are listed above. Criteria, measurement and solver artifacts were not created.
- Commit SHA is reported after push.

## Parent review checkpoint, 2026-10-02

The hashes above describe the worker's initial preparation snapshot. Parent
commit `dd46c6c` added the repository-local `src` import bootstrap to the test,
so the shared editable environment cannot accidentally test another worktree.
The current test SHA-256 is
`95409bef68b1856f23df8c7137b1ad575e2b499c32ca0b90ccff89ae6bc66669`.
The contract module hash is unchanged. The literal focused pytest command
passed all seven tests; compileall passed. Integration used `merge --no-ff`.

The one formerly failing baseline test became runnable because its ignored
ProblemSpec fixture was copied into this worker's local `work/` directory.
That failure-ID removal is fixture availability, not a source bug repair.
No finite-step solver measurements or secant qualification has been performed;
the helper remains separate from the formal local FD oracle.

## Registration and evidence bindings audited after integration

The protected v17 FD-05 criteria are a source of shared physical-input
identity only; they are not STEP-01 criteria. Their file SHA-256 is
`9cd5e3e35ac779ed937f4516421d82fbd40820dec2ae556817a4ff3ab007918e`
(criteria identity `f9ee9cb265f928aade278b3027f90212292a8c01ac0719a7fd8e7799d387f12f`). The referenced canonical state is
`sdf_design_state.npz`, SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`,
with phi raw SHA-256
`e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`.
The registered response case is `flow_24`; physical-force means use the
endpoint-clipped trapezoidal `[80,120] tU/L` window. The new #47 registration
must rebind these exact input files and hashes and use the frozen composite
Candidate C body (moment blend plus `normal_floor=0.25`) on the same backend.
It must record the actual runtime, code and criteria identities instead of
copying the old W3/W4 T4 identity as if it were the new run's observation.

STEP-01 is a separate finite-step secant oracle. For canonical spacing
`h=0.025 m`, the issue's allowed range `0.1–0.5 h` corresponds to 2.5–12.5
mm. The exact step fractions, directions, signs and run inventory remain
unselected until #44 freezes the operator; the range alone is not a complete
immutable registration. At registration time every candidate must have a
distinct run ID and an explicit association to baseline, direction, signed
step, requested displacement and actual perturbed phi artifact. Store the
perturbed phi hash and a measured nonzero float32 change from canonical phi
(changed-node count and magnitude summary), since a requested small step can
round away. Bind each force result to the saved raw force-history path/hash,
frozen source identity, actual runtime identity and host-recomputed exact
window mean in N.

The current FD host pipeline's force sign has two levels. WaterLily API
`pressure_force`/`viscous_force` return the surface reaction; repository
`pressure_force_on_body`/`viscous_force_on_body` negate those arrays to obtain
force on the body. The registered response then projects body force as
`drag=+Fx_body` and `downforce=-Fz_body`, and scales solver-force values by
`rho*U^2*dx^2` to report N (`1/900 N` per solver-force unit in the reference
flow). Future records must keep those raw, body-force, projected and physical
quantities distinct. For signed step `s`, record `R(s)-R(0)` in N and the
finite secant `(R(s)-R(0))/s` in N/m; do not call this a derivative or a
gradient. Any comparison with FD-08 slopes is descriptive and can only be
reported once both separate datasets exist with compatible frozen bindings.

The current helper only validates the stated step-fraction range and
calculates a secant from caller-supplied numbers. It does not validate
operator identity, actual step coverage, input/output hashes, backend, source
force semantics, or saved N-valued force records. Reuse the existing batch
runner and host force recomputation path; keep STEP-01 run/artifact IDs
disjoint from both FD-08 calibration and its 33-run fresh qualification set.
No #46 calibration or qualification record may be reused for #47. The
measurement plan must report its own baseline, plus/minus response changes,
sign stability and finite secants. It must not change any gradient,
optimizer or shape-update qualification flag.

No immutable STEP-01 criteria or run set was created in this preparation.
No CFD/calibration run or numerical verdict was produced; operator freeze in
#44 remains pending.
