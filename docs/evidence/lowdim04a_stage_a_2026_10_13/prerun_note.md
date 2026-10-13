# LOWDIM-04A Stage A preregistration (#51)

Date: 2026-10-13 Asia/Tokyo. Issue: [#51](https://github.com/ramhachi/CFD_opt_sdf/issues/51). Plan: `docs/lowdim04_plan_2026_10_13.md`.
Integration parent: `0cd66887…` (the LOWDIM-04 plan merge, descending from the P22-v2 registration `6d8cc96`).
Evidence class: bounded two-grid local model evidence at the accepted LOWDIM-03 parent. Stage A only; the stage stops after recording.

## Authority, disclosure, reviewers

The user's own words (session, 2026-10-13), recorded on #51: 「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」 They authorize the restart under this
preregistration, the replacement of the issue's v1 sharp-volume rule by the P22-v2 integer count (#55; the v1 smooth gradient is reused only as a report) and Kaggle
submissions of the frozen kernels. They waive no freeze, hash, review or fail-closed rule. All reviews are Claude subagents, not human reviewers.

**Non-blind.** The author has seen STEP-01, LOWDIM-01/02A, GRID-01 and LOWDIM-03 results, the P22/SRCMAP records, exploratory fits of the retained ladder and the volume figures of the
nine geometries. The verdict is therefore not a blind validation. Reviewers receive frozen sources and paths, never excerpts of the new run.

## Question and scope

For each of `flow_24` and `flow_32`: the accepted LOWDIM-03 parent (baseline v17 + 1.25 mm along the fixed robust direction; state `81d24fe4…`, Fortran-order phi SHA `b02dc49c…`) plus the
eight centered perturbations D0/D1/D2/P1 x -/+ 1.25 mm of that parent: nine states per grid, 18 runs, two Kaggle T4 kernels. Centered secants only, fixed basis, no reinitialization,
no repeats (the solver reruns byte-identically; this is reproducibility, not insensitivity). The parent is run, not inherited, so that a changed environment shows as a parent mismatch.

## Frozen identity

`inventory.json` (derived by `scripts/build_lowdim04a_inputs.py`, re-derivable with `--check`) fixes, for every state, four named hashes: `phi_fortran_order_sha256`, `phi_c_order_sha256`,
`state_sha256`, `npz_sha256`. Consumers are pinned to one field each: the Kaggle runner and the device round trip use the **Fortran-order** hash; the P22-v2 evaluator and the v2 reference use the
**C-order** bytes of the phi artifact. Perturbations are built with the production `construct_state` and asserted byte-equal to `step01_states.perturb`; the realized float32
`maximum_pointwise_change_m` (about 1.25000002 mm, not exactly 1.25 mm) is frozen per state. The eight perturbation hashes equal the recorded LOWDIM-04A blocker hashes.

## Parent gate

The fresh parent run on each grid must be byte-identical to the retained LOWDIM-03 `prop__s1.25mm` force CSV
(`docs/evidence/lowdim03_dual_grid_primal_2026_10_10/failed_attempt1/kernel_output/lowdim03_{a,b}/states/lowdim03__prop__s1.25mm/flow_{24,32}.forces.csv`; the integrity failure recorded in that
directory was analyzer-only, Amendment 1). The runner checks it right after the first state and stops before any perturbation if it differs; the analyzer checks it again. A mismatch is
`LOWDIM04A_INCOMPLETE`: no analysis is written, no repair, no resubmission.

## Pre-CFD checks (done in the inventory, on the exact bytes)

- The five existing LOWDIM geometry gates for every state, with the base frozen as the canonical v17 baseline (the parent row carries its recorded LOWDIM-03 gates). A failure would be a pre-freeze
  blocker; there is no in-run "geometry unsupported" branch.
- Hard count `N_phi = 8272` for every state, by the production evaluator (`volume_semantics_v2.hard_count_residual`). Invariance statement (arithmetic, about the retained Float32 phi on the v17
  lattice only): a state within max-norm radius `r` of the parent cannot change any cell centre sign if `r + rounding < min |centre|`. Parent: minimum `|centre|` 2.406 mm (count equal), minimum fluid centre
  3.226 mm (count cannot increase); perturbations move by about 1.25 mm; margin about 1.156 mm after the Float32 rounding allowance (`2*gamma7*max|phi| + half ulp`, microns). A runtime count mismatch is INCOMPLETE.
- Descriptive volumes per state: smoothed `V_eps`, the continuum zero-set volume `V_cont` (exact in z, 48x48 samples per mixed cell) and their changes against the parent (recorded D0 states: about
  -3.4% to +4.2% of `V_cont`, -2.8% to +2.8% of `V_eps`; D1/D2 near zero; P1 about +-1.2% to 1.7%). The smoothed-volume band (10%) is the existing gate.
  **Frozen sentence:** volume feasibility here means the lattice count N <= 8272, exactly satisfied by construction; it constrains no physical or sub-voxel volume.

## Model, subproblem, verdict

- Secants `g = [R(+s) - R(-s)] / (2 s)`, `s = 1.25 mm`, per grid and force (`lowdim04a_contract.secant_sample`; GRID-01's 2.5 mm constant is not reused: a naive reuse would halve every secant).
  Odd and even parts are reported (descriptive, not used in the solve). A secant is **resolved** if `|R(+) - R(-)| > 3e-5 N`; flow_32 drag below it is "unresolved, active at zero within the nominal floor";
  the floor is about 1 sigma of the retained flow_32 response jitter, not a 3 sigma rule.
- Subproblem: the certified exhaustive cone solver `solve_cone_family` (reused unchanged) on the 2x4 lift and drag matrices: maximize the minimum lift subject to nonpositive drag on both grids, with
  `||c||_2 <= 1`; main and L1-robust families (`epsilon = 3e-5 / (2 s) = 0.012 N/m`), plus the four single-grid references, each with its KKT verification. The spatial direction is rescaled by its actual max-norm
  `m = max|sum c_i d_i|` so that `max|d phi| = 1.25 mm`; predicted gains are in newtons at that step (`3e-5 N` floor, `m` from the actual arrays). A max-norm LP cross-check is not part of Stage A.
- Verdict: `LOCAL_FEASIBLE_CONE_FOUND` only if **both** the main and the L1-robust problems pass (`t*` above 1e-8 and the predicted 1.25 mm downforce at least 3e-5 N on both grids; the robust lower bound
  gates the robust family); otherwise `LOCAL_FEASIBLE_CONE_NOT_FOUND` (a zero solution is NOT_FOUND). Unresolved components never make the analysis INCOMPLETE; their number and identity are reported.
  `LOWDIM04A_INCOMPLETE`: any integrity failure, one grid incomplete, a non-finite run, a failed parent gate or a hash mismatch; nothing partial is written.
- Reported for every outcome: all eight component comparisons, response-vector cosines and norm ratios against GRID-01 (baseline, +-2.5 mm), the cosine to the prior robust direction, the first-order volume
  projection of each solution (D0 coefficient included), `t*`, coefficients, certificates.

## Claims

May say, for this parent, fixed basis, two grids, Re 80 and +-1.25 mm only: the responses were measured; the secant values; under the stated linear model and normalization a vector with the stated `t*`
exists or not; the comparison with GRID-01. May not say: that downforce improves (the linear model overpredicted by about 40% at the previous step), drag nonincrease, feasibility without "lattice count only", grid
convergence, that #26 is resolved, optimizer or second-iteration progress. Parent, trust region and second iteration are experiment labels, not an algorithm. All qualification flags false,
`selected_delta=null`, `shape_update_allowed=false`, reinitialization none. **No Stage B is authorized by this verdict**; the next action needs its own preregistration.

## Runtime and process

Kernels `ramhachi888/cfd-opt-sdf-lowdim04a-a` (flow_24, about 176 s per state) and `-b` (flow_32, about 408 s per state); per-state timeout 900 s, aggregate solver cap 8100 s (nine states, as the
nine-state GRID-01 kernels), kernel timeout 10800 s, one T4, one Julia thread. New code only under `scripts/` and `tests/` (nothing under `src/cfd_sdf` or `julia/`); the freeze binds every imported
project file by hash (found by importing, not by a glob) and the source commit by its git tree id; the source commit is pushed to a remote branch (the runner fetches it). Evidence logs are
trackable through a narrow `.gitignore` negation for this directory; every `SHA256SUMS` entry must exist and be tracked.
Pre-freeze (no GPU): tests of the contract, the inventory, the runner's state generation and plan checks (all nine states regenerated in both byte orders), and `check_kernel` replayed over the real
retained LOWDIM-03 output with only the expected hashes swapped (plus negatives: parent bytes, Fortran/C swap, missing DONE, post-manifest edit). Then independent adversarial review of the final
bytes, an authenticated Kaggle identity check, the freeze, submission of both kernels, `--check` then exactly one `--write`, independent post-run review, validation against the 48 known failures, record, stop.

## Known limitations

Reviewers are subagents. The registration is non-blind. The nominal floors are not a flow_32 noise measurement. The lemma and radii cover the Float32 phi artifact only. LOWDIM-03's own `--check` no longer
passes from a clean checkout (git-ignored logs; its source-closure glob now sees `volume_semantics_v2.py`); that is recorded, not repaired. The exploratory curvature fits and continuum-volume bounds quoted in the
plan are not inputs to this stage.
