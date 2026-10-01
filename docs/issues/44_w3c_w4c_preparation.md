# #44 W3-C/W4-C source preparation audit (2026-10-02)

Status: **blocked preparation note; no criteria round registered, no Kaggle
submission, and no qualification claim**. This records source-level wiring for a
future C-operator round while preserving the registered W3/W4 measurement and
judgement contracts. It is not evidence that the production operator is
qualified.

## Frozen comparison basis inspected

The checked-in W3 v17 criteria is round 1,
`registered_not_run`, immutable and register-before-computation. Its raw SHA-256
is `00af9ed92111b48a69d0eebebfa143db7e23c7caee322bb88cdb6ac36ff2e608`.
It retains the single T4 / Julia 1.12.6 / WaterLily 1.8.0 / CUDA.jl 6.3.1
backend; the exact `[80,120] tU/L` force window, 8-step sampling, Float32,
pressure-plus-viscous component closure, host recomputation, runtime/VRAM gates,
and 0.02 two-half-window stationarity criterion; and W3 gates T0–T10. The
existing v16 force-value comparison is diagnostic only, and drag/downforce
sign or magnitude is not a gate. The semantic clarification is a separate
append-only artifact (SHA-256
`0f4faa60a269a4377124295b6cd4a02c45510755cb6a45d81ee4ff9f5ba41ed7`); neither
artifact was modified.

W4 v17's criteria aliases
`docs/evidence/kaggle_w4_v17_criteria.json` and
`docs/evidence/kaggle_w4_v17_sensitivity_criteria_2026_09.json` are byte-identical
(SHA-256 `5eceb62c17e347679cdadc88c68266e7fe00b392da40a8029ed3544a002e0f01`).
They are immutable round 1, preregistered and unrun. The ordered matrix remains
`flow_16` (100x48x36, h=0.05 m), `flow_24` (150x72x54, h=1/30 m), `flow_32`
(200x96x72, h=0.025 m), and `domain_xplus1m_16` (120x48x36, h=0.05 m). W4
retains the exact same T4/Julia/WaterLily/CUDA backend, `[80,120] tU/L` window,
80 burn-in, 8-step samples, 4-sample minimum, component-force closure, 0.02
half-window drift, 1800 s per-case and 5400 s aggregate limits, and all
integrity/stationarity gates T0–T10. The W3 flow16 comparison remains
report-only; it is not a repeatability gate. W4 does not qualify physical-profile
equivalence, absolute downforce, grid/domain convergence, gradients, reverse,
optimization, topology, or shape updates.

The W3 `flags` and W4 `evidence_scope` qualification values inspected are
false. This preparation adds no criterion, result, or qualification flag. The
only admissible future operator identity is the **composite** Candidate C
moment blend wrapped around `normal_floor=0.25`; Candidate C without the floor
and the floor without Candidate C are both wrong identities. The checked source
hashes are `CandidateCWaterLilyBody.jl`
`2a4b056a1a4a23dc5699ad340faed8ad35bfab4c103302169a93150feedd04c6` and
`WaterLilyNormalFloorBody.jl`
`6686585c205eb07508979b3fdba8bf7aab28c0b29a0d021606a2a1280d031ecf`.
Candidate C itself enforces `normal_floor=0.25` and transition width
`1.1444091796875e-4` solver cells. The pinned `WaterLilyBody.jl` is untouched.

## Exact Kaggle source surgery identified

No wrapper or solver job was changed in this preparation. When the W2 fixture
gates and operator contract allow a new round, the minimum source changes are:

1. **Package the two existing body source files** in each W3/W4 self-contained
   Kaggle source tree and hash-bind them in the new source inventory. Include
   `WaterLilyNormalFloorBody.jl` in the `CFDSDFWaterLily` module before
   `CandidateCWaterLilyBody.jl`; both must be loaded after the GridSDF body and
   WaterLily dependency. Do not modify or copy over the historical pinned body.
2. In `scripts/waterlily_w3_v16_primal_job.jl`, retain the existing canonical
   GridSDF CPU identity checks and device round-trip. Replace only the body
   construction at `run_w3_primal()` (currently the call to
   `v16_physical_profile_bodies`) with a normal-floor candidate made from that
   same `device_grid`, the registered physical-map origin/spacing, and
   `normal_floor=0.25`; create `candidate = CandidateCWaterLilyBody(floor_body)`
   for force integration, keep the current moving ground, and form the solver
   body with the **outer** `CandidateCWaterLilyBody(floor_body, ground)` wrapper.
   Do not form `CandidateCWaterLilyBody(floor_body) + ground`: WaterLily would
   dispatch `measure!` on the outer `SetBody`, bypassing Candidate C's
   specialized moment fill. The required outer wrapper applies that blend to
   the whole candidate-plus-ground union; the force integration body remains
   candidate-only. Keep simulation,
   forces, output fields, T0–T10, and W3 criterion semantics otherwise
   unchanged. The W3 job currently computes `pressure_force` and
   `viscous_force` on `bodies.candidate`; keep that candidate-only integration.
3. In `scripts/waterlily_w4_v16_sensitivity_job.jl`, make the analogous body
   construction inside `run_case()` *for each registered flow case*: use that
   case's flow origin/spacing for the NormalFloor GridSDF body, wrap the
   candidate alone for pressure/viscous force integration, and use an outer
   `CandidateCWaterLilyBody(floor_body, ground)` for `Simulation.body`. As in
   W3, do not union a C-wrapped candidate with an unwrapped ground: that would
   bypass C's `measure!` specialization. The C moment blend therefore also
   sees the moving-ground faces in the solver union, while force integration
   stays on the candidate alone, matching the existing force scope. Do not alter
   `EXPECTED_CASE_IDS`, `w4_cases`, grid dimensions, physical boxes, case order,
   measurement loops, summaries, or any W4 runner/verifier gate.
4. W3/W4 dataset preparers and package inventories must include the same two
   module sources and reject wrong hashes before solver startup. New result
   identity fields must bind the composite operator, the fixed floor and blend
   width, and exact body-source hashes. W4's prerequisite must bind to the exact
   host-verified **W3-C result**, not the old generic W3 v17 result. That is
   artifact identity rebinding, not a changed measurement/judgement contract.

The C wrapper must borrow the device GridSDF through the same `GC.@preserve`
ownership lifetime as the current `OwnedV16Run` path. It must not capture or
copy a `CuArray` into the body. Before any future GPU dispatch, a CPU-only
construction check should confirm that both the candidate-only force body and
the outer composite simulation body have the expected Candidate C / normal
floor identity and are GPU-kernel-compatible; that check is capability evidence
only and does not replace the W2 or W3/W4 solver gates.

The present registered W3 source inventory pins the current W3 job at
`0ee33573045a4ba89504679c209a35bd7b51cc93b8c15496e159edf3f2e1cf98`, while
the current file hashes to
`4e619ec69b6c3b42bb200c5fd4bfa1958e1750f0e54e4fb8494b0963c6e81b5d`; the
W3 kernel runner remains at its pinned hash
`b511ed4b357040dcda431bef971d2484c9f9e3ce9cbb87f3b15794ee9c7b0eb2`. The
registered W4 job and runner hashes still match their current source
(`970386e3cee20f811fe91499696c1a24b7b9a6f8bf4887fb32b17dfd4a3c50d1` and
`0474a9a63cd5bd2e3c5a9bf93d43db8f41ddcb2c29aa971999682102816f7174`). The
existing W3 v17 job's dynamic completion marker and the W3/W4 host-verifier
source drift are source-inventory differences. They must be disclosed and
rebound to exact reviewed source in any *new* criteria; they do not authorize
silently claiming an operator-identity-only round or changing evaluator
semantics.

## Blocking qualification inputs

The parent execution report states that the W2a sphere is currently running in
another worktree. Its outcome is not imported here. A long-thin-plate GridSDF
case, moving-ground behavior, and mass/force closure remain outstanding. Those
are blockers to freezing the production operator; a native analytic body is
only a reference/control and does not satisfy the sampled-GridSDF-through-C
requirement. No CPU or GPU solver run was performed for this preparation.

All six requested qualification flags remain false: `shape_update_allowed`,
`fd_oracle`, `field_gradient`, `reverse`, `optimizer`, and `topology`.

## Evidence record

- Evidence class: source/contract audit only; no solver or physical
  qualification evidence.
- Checked-out base: integration commit `7022298e01b43291cb6bca2404f3a38e58b0a3cc`.
- Commands: inspected the immutable W3/W4 JSON and sidecars, their source
  inventories, W3/W4 runner/job body-construction call sites, and Candidate C /
  normal-floor source and test. No criteria, result, body, evaluator, or Kaggle
  source file was edited.
- The criteria and source hashes above identify the exact bytes inspected.
- Focused verification: `julia --project=julia/CFDSDFWaterLily
  julia/CFDSDFWaterLily/test/test_candidate_c_body.jl` passed 17/17;
  `julia --project=julia/CFDSDFWaterLily
  julia/CFDSDFWaterLily/test/test_normal_floor.jl` passed its six named checks;
  `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python
  -m pytest -q tests/test_kaggle_w4.py tests/test_candidate_c_w2a_plan.py`
  passed 32/32.
- `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python
  -m compileall src tests` exited 0. Full `pytest -q` at this worktree produced
  38 failures, 1258 passed, 5 skipped; the failures included one additional
  missing ignored fixture, the canonical v17 state used by
  `test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity`. I
  copied only that existing fixture into this worktree's ignored `work/` from
  the parent issue-44 worktree and verified its raw SHA-256 values against W3/W4
  criteria (`canonical_v17_phi_f4_fortran.raw`:
  `e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`;
  `sdf_design_state.npz`:
  `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`). The
  extra test then passed in isolation (1/1). The other 37 full-suite failure
  IDs exactly match the recorded baseline list at
  `work/four_track_2026_10_02/baseline_failure_ids.json` (SHA-256
  `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`); the
  full suite was not repeated after restoring this fixture. `git diff --check`
  exited 0.
- No Kaggle submission, solver execution, or physical qualification was
  performed.
