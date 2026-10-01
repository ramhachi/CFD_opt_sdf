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
