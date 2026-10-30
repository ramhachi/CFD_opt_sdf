# GRID-01 (#26): cross-grid STEP-01 secants and constrained 4D proposal

Status: pre-measurement contract, solver-free source work only

Date: 2026-10-09

Integration parent: `32e64715dc20a9ac2dd78e3c011bcb48f311b98e`

Branch: `exp/issue26-grid01-cross-grid-secant-2026-10-09`

## Objective and evidence scope

Measure the existing four STEP-01 basis directions on `flow_32` using the same
canonical `phi` and the exact centered `+/-2.5 mm` states already registered on
`flow_24`. Compare the two sets of finite-step secants for downforce and drag.
From those recorded numeric values, calculate the pre-specified main and
sensitivity cross-grid constrained proposals, plus each grid's constrained
reference optimum.

This is bounded finite-step characterization. It is not a gradient
qualification, grid-convergence or GCI study, physical-downforce result,
optimizer acceptance, or OPT-01 result. The proposal is a hypothesis from a
linear finite-step secant model. Only an actual primal evaluation with its
registered reverse control can establish whether a proposed step is useful.

## Registered runs and immutable inputs

- One private Kaggle T4 kernel, slug and title `cfd-opt-sdf-grid01-a`, timeout
  `10800` seconds.
- The nonempty visible GPU inventory must contain only Tesla T4 devices. Select
  physical index `0` with `CUDA_DEVICE_ORDER=PCI_BUS_ID` and
  `CUDA_VISIBLE_DEVICES=0`; the nine summaries must report that selected UUID,
  so exactly one GPU is used even when the worker exposes multiple T4s.
- Exactly nine states, in this order: `step01__baseline`, then each of
  `D0_interface_offset`, `D1_filtered_seed11`, `D2_filtered_seed2026`, and
  `P1_upstream_lobe` at `+2.5 mm` and `-2.5 mm`.
- Each perturbed state is taken from the STEP-01 inventory by exact
  `phi`-Fortran, `phi`-C, state, and NPZ SHA-256. The runner regenerates the
  `phi` bytes with the unchanged `step01_states.perturb` operation order and
  fails closed on a byte or changed-node mismatch.
- The four raw directions, baseline raw `phi`, STEP-01 state inventory,
  `step01_analysis.json`, flow_32 job, Julia source tree, T4 project and
  manifest are hash-bound. FLOW24 values are copied from the immutable
  `step01_analysis.json` rows at `step_mm=2.5`; they are not recomputed or
  overwritten.
- The first and only baseline run must produce a force CSV byte-identical to
  the retained W4 v17 round-2 `flow_32.forces.csv`. If it differs, the runner
  stops before running a perturbed state.
- Reuse `scripts/waterlily_lowdim02_flow32_job.jl` unchanged and retain its
  endpoint-clipped, time-weighted `[80,120] tU/L` force measurement. Host
  recomputation uses `FLOW32_CASE` and
  `analyze_lowdim02a.flow32_criteria`; do not feed it the flow_24 force scale.
  The flow_32 conversion uses `flow_spacing_m=0.025 m` and
  `rho*U^2*dx^2=6.25e-4 N` per solver-force unit.
- All nine states must have finite fields and forces, `t_end_reached >= 120`,
  one Julia thread, the exact state hashes and registered margin, a complete
  per-state marker and CSV, and a verified manifest. All visible devices in
  the GPU record must be Tesla T4s; physical index `0` is selected by UUID.
  `DONE` is required and `ERROR.txt` is forbidden.
- The solver-free geometry record uses the existing LOWDIM-01 gates with the
  exact key set `clearance`, `masks_and_support_preserved`,
  `cell_components_equal_baseline`, `smoothed_volume_band`, and
  `eikonal_median_within_limit`. These are reported as geometry descriptors;
  they do not qualify geometry or change the secant verdict.

## Finite-step quantities and resolution

For response `q` and direction `i`, with `s=0.0025 m`, record

```text
g_q,i = (R_q,i(+s) - R_q,i(-s)) / (2s)              [N/m]
even_q,i = (R_q,i(+s) + R_q,i(-s) - 2 R_q,0) / 2   [N]
eta_even = |R(+s) + R(-s) - 2R(0)| / |R(+s)-R(-s)|
```

The denominator for `eta_even` is reported as unresolved when it is exactly
zero; otherwise the raw ratio is retained. A component is resolved only when
`abs(R(+s)-R(-s)) > 3e-5 N` (strict inequality). The `3e-5 N` value is ten
times the nominal flow_24 `sigma0`; it is not a flow_32 noise measurement.
Keep every finite numeric secant, including unresolved ones, and mark it
`resolved=false`. Never substitute zero for a missing or unresolved component,
and never assign an interpreted sign to it. Direction-by-direction sign
preservation is reported only when both grid components are resolved.

For each response, report the four raw components on each grid, per-component
ratio and relative difference where defined, resolved-sign status, coefficient
space cosine, and the flow_32/flow_24 L2 norm ratio. The cosine and norm ratio
use the four recorded numeric components and are explicitly labelled raw
finite-step comparisons; they do not promote unresolved component signs.

The measurement record is `GRID01_SECANT_RECORDED` only when all identity,
input, state, geometry-schema, finite-value, baseline, runtime, output-manifest,
and completeness checks pass. Otherwise it is `GRID01_SECANT_INCOMPLETE`.
Neither status is a physical or grid-acceptance judgement.

## Solver-free proposal contract

Let `c` be the four-dimensional coefficient vector in basis order
`(D0,D1,D2,P1)` with `||c||_2 <= 1`. Let `g_L^24`, `g_L^32`, `g_D^24`, and
`g_D^32` be the four recorded coefficient secant vectors.

Main problem:

```text
maximize t
subject to t <= g_L^24 . c
           t <= g_L^32 . c
           g_D^24 . c <= 0
           g_D^32 . c <= 0
           ||c||_2 <= 1
```

Sensitivity problem, with
`epsilon = 3e-5/(2*0.0025) = 6e-3 N/m` applied to every coefficient:

```text
maximize t
subject to g_L^24 . c - epsilon*||c||_1 >= t
           g_L^32 . c - epsilon*||c||_1 >= t
           g_D^24 . c + epsilon*||c||_1 <= 0
           g_D^32 . c + epsilon*||c||_1 <= 0
           ||c||_2 <= 1
```

Also report, for each grid separately, its main and sensitivity constrained
optimum, its retention relative to `||g_L||_2`, and the LOWDIM-01 proposal's
per-grid raw first-order drag slope and `1.25 mm` prediction.

### Deterministic convex solver and proof checks

Use `float64-exhaustive-orthant-active-set-cone-projection-v1`; no iterative
nonlinear or approximate-cone optimizer is used. The main problem is split by
which of the two lift constraints is active at the minimum. The sensitivity
problem is additionally split into all `2^4=16` coefficient sign orthants,
where each L1 term is linear. Each resulting branch has the form
`maximize q.c` subject to homogeneous linear inequalities `B c <= 0` and
`||c||_2 <= 1`.

Normalize each nonzero constraint normal, enumerate every linearly independent
active set of at most four normals, solve
`(B_A B_A^T) lambda = B_A q`, and set
`p=q-B_A^T lambda`. A valid branch certificate requires primal feasibility,
nonnegative multipliers, stationarity, complementarity, and the matching
primal/dual objective. For `p != 0`, `c=p/||p||_2` and the dual norm bound is
`||p||_2`; for `p=0`, use `c=0`. Exhaustive active-grid/orthant branch
certificates establish the global optimum by taking the largest verified
branch bound.

Freeze the numerical tolerances as follows: rank `1e-12`, primal feasibility
`1e-9`, dual feasibility `1e-9`, KKT residual and primal/dual gap `1e-8`, all
in float64. Treat `t* <= 1e-8 N/m` as not numerically positive. The analyzer
independently checks every branch's primal/dual certificate and the global
branch maximum; a failed certificate makes the analysis incomplete.

For every reported proposal `c`, derive the spatial normalization from the
actual four direction arrays using the existing
`lowdim01_states.coefficient_direction` operation:
`v=sum_i c_i d_i`, `m=max(abs(v))`, and applied basis coefficients per metre
of max-`|delta phi|` step are `c_i/m`. The `1.25 mm` prediction is
`(g.c)*(0.00125/m)` N, not `(g.c)*0.00125` N. Report raw and L1-robust lower
bounds separately. This calculation is repeated for each main, sensitivity,
and grid-only optimum; no stored LOWDIM-01 `m` is reused for a different `c`.

`FEASIBLE_CONE_FOUND` requires both cross-grid `t*` values to exceed
`1e-8 N/m`; the main proposal's raw first-order downforce gain and the
sensitivity proposal's L1-robust lower-bound gain at `1.25 mm` must each be
at least `3e-5 N` on each grid. Raw sensitivity predictions are descriptive,
not its gain gate. This interpretation was fixed during independent review
before any new flow_32 measurement; no numeric threshold or step changed. Any other result is `NO_FEASIBLE_CONE_IN_4D`; report the specific failed
condition. This criterion chooses no CFD state and authorizes no experiment.

## Pre-freeze administrative integrity corrections

The force case, force scale, averaging window, directions, states and all
response thresholds remain unchanged. GRID-01's fresh nine-state runtime
registration uses 900 s per state, an 8100 s aggregate solver-process cap, and
10800 s for the complete kernel including setup and metadata preflight. Both
host process durations and Julia-reported wall times are checked. The inherited
3300/5600/1500 s fields belong to the historical formal campaign, whose artifact
is not modified; they are not GRID-01's execution budget. These corrections
were made before any new flow_32 run, not after viewing force responses.

The missing-slug status endpoints mask absence as permission/403 errors.
Those errors are not absence evidence. Supplementary complete authenticated
owned kernel/dataset listings (39/20 entries, below the CLI's 100-row clamp)
show no slug/title collision, with successful access to existing owned
resources as positive controls. The raw lists, controls and SHA sidecar are
frozen alongside the unchanged original identity-check record. Unknown errors,
missing controls, inconsistent lists, collisions, stale evidence and truncated
lists fail closed.

The unchanged CFD job echoes its configured GPU UUID in its summary; this is
not described as an independent CUDA observation. A metadata-only Julia
preflight independently queries CUDA's visible device count, device names and
UUIDs and default-device UUID under the exact environment preserved for every
job. It must observe only the selected physical-index-zero T4. The UUID API was
checked against the manifest-pinned CUDA/CUDACore 6.3.1 source. No CFD field or
response is computed by this probe, and the reused CFD job bytes are unchanged.

Identity freshness is evaluated at registration/frozen UTC during historical
analysis, not at the later analysis clock. The Python source closure hashes all
members registered at the source commit: changed or missing registered files
fail, while unrelated newly added modules do not mix a future separate GEOM
track into this freeze. Package initializers and all GRID-01 tests are bound.

## Interpretation limits and fixed declarations

- The existing exploratory flow_24 `+/-2.5 mm` values were visible before this
  registration (approximately `g_L=(0.781,-0.108,-0.096,-0.382)` and
  `g_D=(-0.112,-0.068,-0.169,-0.213) N/m`). They are copied from the frozen
  STEP-01 artifact and are not used to change directions, thresholds, or
  decision rules. The flow_32 response has not been measured at registration.
- No flow_32 repeat is included. A byte-identical repeat in #49 was not flow_32
  noise evidence. The registered nominal resolution remains a flow_24-derived
  floor, not a measured flow_32 uncertainty.
- Curvature is reported for context only. It is not fitted to choose a step or
  used to turn this first-order proposal into an accepted update.
- No basis expansion, reinitialization, AD/tangent, line search, delta
  selection, GRAD-03 verdict, FD-08 verdict change, OPT-01 supersession, or
  qualification-flag change is in scope. All six qualification flags remain
  false; `shape_update_allowed=false`.
- #49 remains `STAGE_A_CONSTRAINT_FAIL`; its crosslink and closure are already
  complete. No new experiment issue is created without a user decision. Any
  future #29 work stays on its separate issue branch and does not enter GRID-01.

## Next decision after measurement

If a feasible cone is found, present a separately registered actual-primal
line-search on both grids, including reverse controls and unchanged hard gates.
If no feasible cone is found, present basis expansion as a possible next
question and inspect #29 geometry gates first. Do not execute either branch or
select the flow grid for the first optimization step from GRID-01 alone.
