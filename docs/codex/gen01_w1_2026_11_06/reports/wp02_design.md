# WP2 FORCE-00 design

## Current continuation: Amendment 3 (2026-11-07)

Start from clean HEAD `afac79ed`. The owner's Amendment 3 and the review-worktree
FORCE-00 spec Amendment 1 supersede the historical design below. Claude still
owns commit/push/PR #84. All changes stay outside the pinned `src/` tree and
registered jobs/evidence. CPU records go in `wp02_validation/amendment3/`;
the production FORCE-00 evidence root stays absent.

Before implementation, the Opus review and CPU probe were read. The work is split
between gate/tests, numerical validation, and the copied job/CPU regression,
with registration/U1/U2 integration and final verification by the parent.
OpenCode MCP is absent and CLI discovery failed (protected log, then
`Provider not found: opencode-go` with temporary XDG data); these are infrastructure
failures, so native workers are used without paid API fallback.

Required changes and contracts:

- C5's absent exact sigma is descriptive only. Missing C1-C4 inputs, including
  missing reference artifacts/keys, prevent the exclusive gate write and return
  a nonzero CLI status. F3 joins the C1 byte regression, so its absent runs are
  now a C1 blocker independently of C5.
- `scripts/force00_boxes.py` measures phase-zero parent Candidate-C Float32
  moments via the CPU uniform runner, derives one largest domain-inset box
  per grid excluding the moving ground, verifies at least five cells of parent
  moment-support clearance, and exclusively writes `docs/harness/force00_boxes.json`.
  The schema is `force00_boxes_v1`, with parent state/raw SHA and `grids[grid]`
  containing lower/upper bounds, flow dimensions, support bounds and margins.
  Every phase and both F3 states use those registered bounds. Explicit box
  overrides require a CPU-test flag and actual Array backend.
- No implicit `box=nothing` region remains. Box validation additionally requires
  stored normal-face mu0 to be exactly one, independently of sampled SDF quality.
- Job `force00_source_sha256` maps the three repository paths for Force00,
  the job and dispatcher to their hashes. U1 `source_sha256` contains those
  same paths plus the box registry/generator. The gate requires exact agreement.
- The W2a physical radius comes from the pinned Simulation.jl constant through
  uniform inputs, not a second numeric literal in the gate. C4 uses 15 percent
  with 1e-9 relative tolerance, preserving the 10-percent diagnostic.
- Add an exact linear-pressure summation-by-parts magnitude check, and a
  descriptive solved D16/Re100 cylinder check across three nested boxes.
  Variant timing/VRAM explicitly includes extra readout overhead and is not
  comparable with registered jobs. Header/usage/DONE name FORCE-00.

Validation: TDD on gate/registry tests, CPU Julia selftest, original-vs-copy
flow16 byte regression, then two new source-bound U1/U2 runs with byte identity
and closure <=1e-12. Run compileall, pin checks, exact job-diff readback and
`pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` to completion.
Compare failure IDs against owner-provided base e3dcdf61 (3482 pass/74 skip/0 fail).
No environment replacement, GPU run, gate write, freeze or adoption is performed.
DONE requires the complete CPU acceptance set; the project's #293 absolute-force
gap and GPU kernel compilation remain unknown until F1-F3.

## Current decision: Amendment 2 (2026-11-06)

Continue the existing uncommitted work at HEAD `21d1e8e7` on
`feat/gen01-w1-02-force00`. Amendment 2 supersedes the prior placement,
publication and baseline instructions. Claude on the host owns commit,
push and PR #84 updates. No Git publication, temporary checkout, API blobs,
GPU execution, registration, qualification change or roadmap change is part
of this continuation.

The team read W1's README first, the five AGENTS authority documents in
full (including all 7,782 lines of phase_plan), STATE, branching, GEN-01
rev 3.1, FORCE-00 rev 0, research facts, the specified body/quadrature code,
pinned WaterLily 1.8.0 code, W2a and registered UNC/FID/SCREEN inputs.
The current user's amendments determine implementation scope. Phase_plan
remains the roadmap/status/order authority and the problem register the
issue ledger; frozen campaign conclusions are unchanged.

## Placement and preserved contracts

The whole `julia/CFDSDFWaterLily/src/` directory is pinned by
`campaign_build.BASE_PINS` and historical freezes. Both `Forces.jl` and the
module also have whole-file SHA pins. Restore the complete src tree to
`e3dcdf61`, with no new src file or include. Apply the supplied tree-pin
patch with its proposed `force00/` path changed to **`gen01/Force00.jl`**.
Four new entrypoints explicitly opt in with `Base.include`; uniform and
regression provenance refer to this same new file. Add the three-line
gen01 README. Future FORCE-00 campaign freezes must explicitly pin the
new gen01 source; do not modify historical manifests or conftest.

Move every CPU record from `docs/evidence/force00_2026_11/` to
`reports/wp02_validation/`, preserving the original attempt data and
separating current source-bound captures in `final/`. The production
FORCE-00 evidence directory must not exist. Remove the applied tree-pin
proposal, the previously applied preserve-pins proposal, and the obsolete
whole-working-tree binary patch. Record exact moves and commit targets.

## Numerical interfaces

- `nds_telescoping(sim)` returns the stored-moment forward differences,
  promoting each mu0 operand to Float64 before subtraction. It neither
  measures an SDF nor changes the flow. Its raw field includes the normal
  domain-BC jumps; the integral helpers exclude those artificial jumps.
- `pressure_force_nds`, `viscous_force_nds` and `force_on_body_nds` reuse
  the existing outward-reaction and negative body-force conventions.
- `control_volume_terms(sim, box)` and `control_volume_force(sim, box)`
  handle 2D/3D, interpolate staggered u and p to box faces, average the
  neighboring WaterLily.S tensors, and use cell-centered `(u-u0)/dt_previous`
  with `Delta_t[end-1]`. All reductions accumulate in Float64.
- A box is a tuple of inclusive pressure-cell UnitRanges. Faces are at
  `first(range)-2` and `last(range)-1` in solver coordinates, at least two
  cells inside the domain and four sampled SDF cells from scene bodies.
  `validate_force_box` also requires complete nonempty candidate support.
- `force_readouts(sim, box; body=sim.body, validate_box=true)` returns
  `(cur, nds, cv)` body-force vectors and restores legacy flow.f scratch
  even on failure. Candidate-plus-ground jobs pass `body=candidate`.
  GPU-compatible kernels use existing WaterLily.@loop/backend reductions;
  GPU compilation and execution remain unverified in this CPU-only task.

## Jobs, geometry and gate

Copy the registered flow32 job without modifying it. Preserve its first
13 CSV columns, cadence, endpoint-clipped window, force signs and phases;
append cur/nds/cv times five force/projection columns and accept/record an
explicit `FORCE00_CV_BOX`. A separate optional launcher changes only the
case inventory and predicate for F1's flow24. CPU regression executes the
actual parsed production measurement functions using identical flow16
inputs, shortened test windows, cadence1 and CPU telemetry.

U1/U2 reuse the existing v18 loader, raw phi, GridSDF/Candidate-C bodies,
SHA-verified 32 FID shifts and existing Halton generator for eight extra
z-only phases. U2 uses the W2a analytic sphere at R=8/16/32, with its physical
radius preserved and empty far field cropped. Serialize sorted JSON without
timestamps or output-path content and refuse existing outputs.

The gate reads only explicitly selected-root inputs and listed artifacts;
no recursive discovery or fallback to CPU reports. Check hashes, identities,
complete eight-step histories, endpoint/summary agreement and registered
window means before C1-C5. C1 compares the original CSV prefix as bytes.
C4 adopts the user-confirmed 15% band and reports the 10% diagnostic.
Missing exact UNC camber_m19.7 sigma_d stays INCOMPLETE, without a proxy.
C5's numerical comparison is descriptive. Among complete passing readouts,
prefer CV, otherwise nds, otherwise NONE. `gate.json` is exclusive/write-once.
The canonical gate is not run while F1-F3 are absent.

Reference discrepancies are explicit: F1 combines U01 smoke k0, formal
half and U2 k1..k6; F2 k13/14 come from f32a, k15/16 from f32b. These are
verified existing references, not fabricated additional rows or new phases.

## Validation and independent review

Use the original existing `.venv`, without substitutions or installs.
Check focused Python gate/input tests and W2a/directory pins, CPU Julia
selftest, two byte-identical U1/U2 runs, small CPU production-job regression,
compileall and diff whitespace. Finish only the result full pytest with
`--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` and a reporting-only
JUnit output. The user supplied the completed host baseline at `e3dcdf61`:
3482 passed, 74 skipped, zero failures. Record both failure-node sets,
commands, durations, hashes and evidence classes; do not reuse interrupted
historical runs as the baseline. Julia process timings include JIT; a few
seconds is not a cold-start requirement under the amendments.

OpenCode Go MCP is absent; CLI discovery failed on its protected log path
and isolated-XDG discovery returned `Provider not found: opencode-go`.
Native read-only reviewers split gate/input, numerical source and
roadmap/pin review. The root applies the scoped relocation and checks
actual diffs/outputs. No paid direct model API is used. Record review
findings independently from run results.

WP2 is DONE only after all CPU acceptance checks and the failure-set
comparison pass. GPU F1-F3, the #293 7-9% gap on this project's parent,
parent phase SD and readout adoption remain unknown until user execution.
