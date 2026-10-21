# T2-0d registered study (#57): verdict **T20D_NO_GO** (DATA `FAIL_INPUT`, DIFF `FAIL_VALUE`, cost `NOT_AFFORDABLE`)

Registration status: `REGISTERED_FROZEN` (`docs/t20d_registration_2026_10_21.md`, SHA-256 3f1b0ec1...79bb, unchanged since freeze 1; freeze 2 in `freeze.json`,
SHA-256 8f956a05...bfa, source commit 7a57fcc9). Evidence class: descriptive numerical evidence for one 2D section (Tyrrell 026 single element, Re_c 4.6e5, moving
ground, OpenFOAM v2512 SA wall functions on Kaggle CPU). All qualification flags stay false; `shape_update_allowed=false`. Thresholds were set after T2-0a, T2-0b
and T2-0c were visible (`verdict.json`: `thresholds_set_after_*_visible` true). The last registered T2-0 study.

## Record (commands, results, artifacts)

| item | value |
| --- | --- |
| source commit (frozen) | 7a57fcc995de3e443fd85265d710b786e4c804d9 (analyzer SHA-256 123bb71a...7424 = freeze 2) |
| kernels (one submission each, version 1, Kaggle CPU 4 vCPU) | XP1 Intel Xeon 2.20 GHz, 23/23 COMPLETED, 6.0 h; XP2 AMD EPYC 7B12, 17/17, 3.1 h; XO1 Intel, 23/23, 6.5 h; XO2 Intel, 19/19, 3.9 h; F1 AMD, 36/36, 2.5 h; F2 Intel, 23/23, 2.7 h (F2 waited for a free slot: "Maximum batch CPU session count of 5", pushed 14:27Z); submitted 2026-10-21T11:56Z |
| outputs | `kernel_<k>_run1/`: kernel log, DONE, manifests, records; `cases.tar` checked against DONE and extracted with tarfile's `data` filter, every artifact-manifest entry verified (1965 files); full pimpleFoam logs of the U-type runs excluded with SHA-256 in `EXCLUDED_U_LOGS_SHA256.txt` (registration section 9); every run keeps `case_result.json`, `coefficient.dat.gz`, the log tail and the dictionaries |
| completeness (before the analysis) | `completeness.json`: no lost run (S0 63 valid, S1 9 valid, U-type 58 valid / 5 invalid): no resubmission, no amendment |
| analysis | `.venv/bin/python scripts/analyze_t20d.py --xp1 docs/evidence/t20d_registered_2026_10_21/kernel_xp1_run1/t20d ... --f2 .../kernel_f2_run1/t20d --out docs/evidence/t20d_registered_2026_10_21` run once -> `analysis.md`, `verdict.json` (committed unchanged) |
| development smoke | 2 attempts (`smoke/attempt1`, `smoke/attempt2`), both FINISHED_SMOKE with no force value in the output (`freeze.json`) |
| reviews | one plan review (3 angles, 40 findings; registration section 10), one source review (13 findings, 2 blockers fixed before freeze 2) |
| regression (freeze 2) | full pytest in a fresh worktree at 9be42da3: 3058 passed, 73 skipped, 0 failed; `tests/test_t20d.py` at 7a57fcc9: 30 passed |
| later reading | `note_2026_10_22_after_analysis.md` (dated; not part of the verdict) |
| integrity | `SHA256SUMS` (repo-root paths) split per directory; all checked with `scripts/check_sha256sums_tracked.py` |

## Q1 (registered labels): the non-settling is a steady-solver convergence failure of this model, not a URANS unsteadiness

| condition | label | URANS (dt 1e-5 s) | S0 (SIMPLEC 0.9) | S1 (SIMPLE 0.3/0.7) | m_U | Cl_S0 (pseudo-mean) |
| --- | --- | --- | --- | --- | --- | --- |
| x09 -1 | STEADY_URANS_ONLY | settled | not converged | not converged | 1.1873 | 1.2365 |
| x09 0 | STEADY_URANS_ONLY (second start from S1: 1.25865) | settled | not converged | not converged | 1.2586 | 1.3367 |
| x09 +1 | INDETERMINATE (U and Udt2 NONSTATIONARY) | drifting | not converged | not converged | - | 1.4911 |
| x134 0 | STEADY_URANS_ONLY (second start: 1.30846) | settled | not converged | not converged | 1.3085 | 1.3263 |
| x134 +1 | STEADY_URANS_ONLY | settled | not converged | not converged | 1.3766 | 1.4605 |
| f09 +1 | INDETERMINATE (U and Udt2 NONSTATIONARY) | drifting | not converged | not converged | - | 1.3966 |
| x224 0 (control) | CONTROL_OK | settled | converged | converged | 1.2765 | 1.2714 |
| x134 -1 (control) | CONTROL_NOT_OK (S0 offset 0.52 % > 0.5 %) | settled | converged | converged | 1.2234 | 1.2170 |
| f09 0 (control) | CONTROL_NOT_OK (S1 drifted, not converged) | settled | converged | not converged | 1.3173 | 1.3055 |

`Q1_FORM_134` and `Q1_FORM_09`: `INDETERMINATE` (a control not OK; two targets indeterminate). Every valid URANS run of the study (58 of 63) is `VALID_SETTLED`;
none is periodic. The 5 invalid ones (x09 +1 and f09 +1 in U and Udt2, the 5 T_c dt/2 run at x09 0) drift monotonically with decaying amplitude: a slow transient
that the registered window does not cover. Where S0 does not converge (11 geometries), its pseudo-mean is 1.4-6.2 % above the settled URANS value; where S0 converges (38), the URANS value
is 0.25-0.91 % (median 0.52 %) above it (the PIMPLE and SIMPLEC steady limits differ). Time step: dt vs 2 dt agree within 0.13-0.21 % wherever valid (GTd, GT134
pass); dt/2 at x134 0 moves Cl by the same +0.18 % as dt does from 2 dt (observed order about 0: the settled value keeps a dt-dependent formulation term of
about 0.2 % per halving; the derivative changes by 0.5 % between dt and 2 dt).

## DATA (Q2): `FAIL_INPUT`

| level | G2u | mean abs e (nominal / +0.15 deg) | G2d | peak | noise band n | outcome reason |
| --- | --- | --- | --- | --- | --- | --- |
| fine30 | INDETERMINATE_NOISE | 3.00 % / 4.07 % | 0.363 | at 0.134, margin 0.059 >= n (pass); rise 0.224 -> 0.179 within the band | 0.056 | GTd at f09 +1: FAIL_INPUT (NONSTATIONARY) |
| xfine30 | INDETERMINATE_NOISE | 3.41 % / 3.78 % | 0.267 | at 0.179 by 0.0008 (within the band); rise 0.179 -> 0.134 within the band | 0.056 | GTd at x09 +1: FAIL_INPUT (NONSTATIONARY) |

The realisation noise of a remeshed Cl at h/c 0.134 is large: sigma_real80 = 0.0198 (point 0.0160, 12 same-geometry pairs pooled over both levels, differences up
to 0.044, largest between the fine30 base realisations), so the band 2 sqrt(2) sigma = 0.056 exceeds the digitised curve's own peak margin (0.022):
`PEAK_NONDIAGNOSTIC` on both levels. Both levels `SHIFT_UNVERIFIED` (the 0.09 +1 deg run is invalid). xfine30 lies below fine30 at every height, by 1.7 % at 0.671
up to 7.2 % at 0.134 (4.5 % at 0.09); xfine30 against the curve: +2.3 % at 0.671, -0.7 % at 0.224, -5.6 % at 0.134, -8.1 % at 0.09. **`G2_ACTION`: `UNDECIDED`**
(invalid inputs on both levels): T2-0b's G2 action stays the default until a recorded M4 decision.

## DIFF (Q3, xfine30, h/c 0.134): `FAIL_VALUE` (G3bu, noise)

| gate | result | numbers |
| --- | --- | --- |
| GT134 | PASS | dt vs 2 dt at B, +1, -1 within 0.18-0.20 %; d(1) 0.0766 vs 0.0762 |
| G6u | PASS | sigma_eff 0.00058 (cubic fit; SE 1e-5); d(0.25) 0.0797 vs d(1) 0.0766; dCl(+-0.25 deg) 0.040 resolved (needed 0.0041); smallest resolved incidence 0.022 deg; MDD 0.13 % of Cl |
| G8u | PASS | base B vs B': s = 1 0.0766 vs 0.0833, s = 0.25 0.0797 vs 0.0847 (both within the band) |
| GSu | PASS | camber dCl(+-0.25 mm) 0.0095, flap 0.0298, both resolved, signs as expected |
| G3bu | **FAIL (UNRESOLVED)** | d(1) fine30 0.0665 vs xfine30 0.0766 agree in value, but fine30's base-realisation spread (fine30 B vs B' 0.0665 vs 0.0878: sd 0.015) makes the comparison unresolved |

`SURVIVES_2SIGMA`: the same outcomes. fine30 at 0.134 (F2, labels): G6u and G8u rules fail (sigma 0.0017; base-realisation dependence, as in T2-0c).
Steady S0 scans at h/c 0.179 (labels): xfine30 converged at every incidence and passes the G6m-type rule (sigma 0.00047, d(0.25) 0.102 vs d(1) 0.103); fine30
converged but UNRESOLVED (sigma 0.0018).

## Cost: `NOT_AFFORDABLE`

Evaluation cost of the 15 xfine30 h/c 0.134 URANS runs (generation, S0 and the 16 T_c URANS on one of 4 workers): median 92 min, maximum 134 min, against the
T2-0b bound (median 15 min, maximum 30 min) and R5's 27.5 min. `COST_MIN` (label, not a route): 44 min with S0, 24 min warm-started (6 T_c transient + 1 T_c
window at the 2 dt cost of 3.4 min per T_c), untested as a protocol.

## Conclusion (separate from the record)

The registered verdict is **T20D_NO_GO**: DATA fails on invalid inputs (the URANS at h/c 0.09, +1 deg drifts through the window on both levels) and DIFF fails on
noise (the fine30 comparison is unresolved because fine30's derivative depends on its base mesh). Q1 is answered as far as the controls allow: where T2-0c's steady
solver did not settle, the time-accurate SA-WF solution on the same mesh settles to a steady state (no URANS oscillation anywhere in the study), relaxing SIMPLE does
not converge it, and the steady pseudo-means were biased high by 1.4-6.2 %; the Q1 forms stay INDETERMINATE because two controls miss the 0.5 % agreement band.
On xfine30 at the downforce peak the time-averaged evaluator does resolve +-0.25 deg and +-0.25 mm camber/flap differences, consistently between time steps and
between two base meshes, but at 1.5-2.2 h per evaluation, and its level at 0.134 lies 7 % below fine30 and 5.6 % below the digitised curve, with a realisation noise
that makes the G2 peak test non-diagnostic. Per registration section 6.5: no optimisation evaluator near the peak from T2-0; the G2 route is UNDECIDED (T2-0b's
action remains the default for M4). No claim beyond the 2D section scope (registration section 7).
