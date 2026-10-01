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

Added `src/cfd_sdf/fd08_contract.py` and its focused tests. The helper rejects
duplicate or overlapping calibration/formal run IDs and requires exactly 33
fresh qualification IDs. Its verdict helper keeps resolution, the existing
5% plateau term and sign consistency separate; it does not select an epsilon,
estimate a floor, or register campaign criteria.

This helper validates a supplied gate summary, not the full campaign evidence.
The eventual registrar/runner must still bind the frozen operator and backend,
criteria/source hashes and freeze lineage, and require the complete registered
direction-by-epsilon coverage across its 33 run identities. It requires at
least three plateau observations before producing any response verdict.

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
