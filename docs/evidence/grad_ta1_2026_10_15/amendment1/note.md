# GRAD-TA1 amendment 1: analyzer tau identity check (post hoc, disclosed)

## Official registered result (unchanged, kept)

The frozen analyzer `scripts/analyze_grad_ta1.py` (SHA-256 pinned in `prerun_freeze.json`), run unchanged, one `--write` then `--check`, gives **GRAD_TA1_INCOMPLETE**
with the single problem `run is not QuickTie(1f-5) with Dual width 1`
(`../grad_ta1_analysis.json`, sidecar `.sha256`). This stays the official verdict. The amendment does not replace or relabel it.

## Defect

Frozen line (`artifact_problems`): `index.get("tau") != float(TAU)` with `TAU = 1e-5`. The kernel's tau is a Float32 (`QuickTie{Float32}`) and the index
records its Float64 widening, `9.999999747378752e-06 = Float64(Float32(1f-5))`, which is `!= 1e-5` in Float64. The check could never pass for a Float32 tau, regardless of
the run. It is an integrity-check transcription bug (a Float32 value compared as if recorded at Float64), not a property of the data. The kernel itself recorded
`TA1_RESULT BLOCKED` independently (`kernel_output/grad_ta1/measurement.log`; `g2_run_index.json` status BLOCKED), and every other frozen integrity check passed (the
INCOMPLETE verdict had exactly this one problem).

## Exact change

New file `scripts/analyze_grad_ta1_amendment1.py` imports the frozen analyzer and replaces only that comparison:
the frozen `artifact_problems` runs unchanged; if it reports the tau problem, the problem is dropped only when
`np.float32(index["tau"]) == np.float32(1e-5) and index["dual_width"] == 1`. Everything else (pins, T4, lambda types, preflight, plain run,
BLOCKED handling, verdict rules, gates) is the frozen code. Two non-behavioural additions: `load_freeze` pins the frozen analyzer's bytes instead of its own (this file is
not in the freeze), and the report carries an `amendment` label key. Test `tests/test_grad_ta1_amendment1.py`: a Float32-tau input is INCOMPLETE under the frozen analyzer and, under the
amendment, equals exactly the report the frozen analyzer gives when tau matches (plain and BLOCKED variants); tau 1e-4, 2e-5, missing, and width 2 are still INCOMPLETE.

## Disclosure

Written after the kernel output was retrieved and the frozen analyzer's INCOMPLETE was seen (post hoc). The BLOCKED outcome was visible in the kernel output before this change.
No freeze of this analyzer was made (unlike LOWDIM-03 amendment 1); no measurement rerun, no resubmission. `--write` executions of the amendment: 1, then `--check` once
(`check_output.txt`, exit 0). Amendment verdict: **GRAD_TA1_BLOCKED** (`grad_ta1_analysis_amendment1.json`). It is not the registered verdict; it is evidence-scoped to this contract:
four directions at flow_24 canonical v17, Re 80, QuickTie(1f-5) tie-averaged forward AD. No gradient, FD-oracle, optimizer or selected-delta claim; six flags false.

## Descriptive facts (not verdict inputs; from `kernel_output/grad_ta1/`)

Preflight (20 steps): pass; primal u and p bit-equal (QuickTie-Dual vs quick-Dual); tangents finite; `tangent_arms_identical` false, max |difference| u 0.318 (relative 1.27%), p 0.341, so QuickTie
changed the tangent. Lambda types recorded `typeof(quick)` (plain) and `WaterLily.QuickTie{Float32}` (all four Dual runs). Runtime: Julia 1.12.6, CUDA.jl 6.3.1, WaterLily 1.8.0, ForwardDiff 1.4.5, Tesla T4 (two listed).

Runs: plain COMPLETE 8740 steps, total 138.9 s (loop 106.6 s), peak VRAM 82.9 MB. Dual runs stopped at step 700 (t_u_l 9.54), BLOCKED: D0 total 33.0 s (ran first), D1 14.9 s, D2 14.9 s, P1 14.8 s; peak VRAM D0 308.9 MB, others 256.7 MB; wall limit 1110.9 s (8x plain), not reached.

Watchdog (every 100 steps; u / p max |tangent|, argmax u cell as `i;j;k;component`):

| step | D0 u / p | D1 u / p | D2 u / p | P1 u / p | argmax u (D0 / D1 / D2 / P1) |
|---:|---|---|---|---|---|
| 100 | 265 / 194 | 47.7 / 32.6 | 12.1 / 13.1 | 74.8 / 55.0 | 87;45;36;3 / 87;45;36;3 / 59;45;24;1 / 87;45;36;3 |
| 200 | 21.1 / 27.9 | 20.1 / 26.4 | 12.1 / 13.0 | 6.03 / 5.30 | 59;48;21;1 / 59;34;21;1 / 59;45;24;1 / 68;40;27;1 |
| 300 | 21.0 / 27.7 | 28.3 / 26.3 | 12.1 / 12.9 | 19.1 / 13.9 | 59;48;21;1 / 69;17;18;3 / 59;45;24;1 / 69;17;18;3 |
| 400 | 9.71e6 / 6.34e6 | 1.99e6 / 1.30e6 | 7.25e5 / 4.74e5 | 4.54e5 / 2.96e5 | 92;32;5;3 (all four) |
| 500 | 1.51e12 / 1.03e12 | 3.13e11 / 2.13e11 | 1.13e11 / 7.67e10 | 7.10e10 / 4.83e10 | 105;52;10;2 (all four) |
| 600 | 2.39e21 / 1.48e21 | 4.94e20 / 3.06e20 | 1.78e20 / 1.10e20 | 1.12e20 / 6.95e19 | 105;54;9;2 (all four) |
| 700 | 1.11e33 / 7.49e32 | 2.30e32 / 1.55e32 | 8.30e31 / 5.59e31 | 5.22e31 / 3.52e31 | 105;54;9;2 (all four) |

Onset (first logged step after 200 with max |tangent| > 10x its step-200 value, u and p alike): **step 400 for all four directions** (the log is every 100 steps, so the onset lies in (300, 400]).
BLOCKED step (above 1e30): **700** for all four; argmax cell u `105;54;9;2`, p `105;54;9` for all four. Growth per 100 steps (decades): 5.19-5.21 (400-500), 9.16-9.20 (500-600), 11.67-11.70 (600-700),
identical across the four directions to two decimals (so about 0.12 decades/step by 600-700), which is the same for all four although the step-200 amplitudes differ by a factor of 3.5.

## Location of cell (105,54,9) and comparison with G2/DIAG1

Mapping (flow_24: spacing 0.8/24 = 1/30 m, origin (-2.5, -1.2, -0.9) m, dims 150x72x54, `x = origin + spacing*(I - 1.5)`, the convention of `localization.json` in DIAG1;
`julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl`): (105,54,9) -> **(0.950, 0.550, -0.650) m**. Domain [-2.5, 2.5] x [-1.2, 1.2] x [-0.9, 0.9] m. Not at a boundary: 1.55 m from the outlet, 0.65 m from the +y side,
**0.25 m (7.5 cells) above the moving ground** (ground plane at solver z = 0, i.e. the domain z-min face; `V16MovingGroundBody(0, 1)`). Body: the baseline phi<0 nodes
(`cal_baseline_01.phi_f4_fortran.raw`, lattice 121x65x49, h 0.025, origin (-1,-0.8,-0.6)) span x [-0.600, 0.550], y [-0.425, 0.425], z [-0.250, 0.250] m. Per-axis gap from the cell to that box: x 0.40 m
(downstream of the rear), y 0.125 m (outside the half-width), z 0.40 m (below); Euclidean distance 0.58 m. The cell is also 0.05 m below the SDF lattice (z-min -0.6 m). So it is in the lower near-ground wake region behind the body, off the centreline, not near the body surface or a domain wall corner.
Earlier argmax cells (flow_24 metres): step 400 (92;32;5) = (0.517, -0.183, -0.783) m (0.12 m above the ground, x at the body box's rear face, 0.53 m below it), step 500 (105;52;10) = (0.95, 0.483, -0.617) m, i.e. the peak
moved from the aft near-ground region to (105;54;9) and stayed there.

G2 / DIAG1 (same D0 direction, plain `quick` forward AD, flow_24): first non-finite tangent at step 1196 at cell (24;61;40) = (-1.75, 0.783, 0.383) m
(`docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/first_bad.json`, `localization.json`, `diag1_analysis.json`), a far-field upstream, +y, high-z region 1.15 m ahead of the body (per-axis gap
x 1.15, y 0.358, z 0.133 m); DIAG4 control B0 onset: box max > 1 at step 838 in the x-min/y-min/z-max far-field corner
(`docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09/note.md`). Comparison: TA1 QuickTie blows up in a different place (downstream, near-ground, wake, vs upstream far-field corner)
and earlier (logged onset in (300, 400], 1e30 at step 700, vs 838 and 1196), with a similar per-step growth rate at the end (DIAG1 fit slope 0.0975 decades/step; TA1 0.117 decades/step at steps 600-700).
These are facts about where the largest tangent sits at logged steps; they do not identify a mechanism.
