# #45 XFID formal part A: OpenFOAM-side registration (blind hold)

Status: **registered before any formal case runs.** Criteria `docs/evidence/xfid_gridphase_x3_2026_10_04/formal/x3_criteria.json`
(SHA-256 `c2523b23...acbc`, bound into `infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py`; the calibration runner
is untouched). Evidence class `xfid_formal_openfoam_side_ensemble_uncertified_geometry`. All six qualification flags remain false.

## What is registered

- **Cases (224):** the 7 X1 Stage V states (baseline; D0/D1/D2 at -/+5 mm; STL hashes bound to
  `xfid45_stage_v_input_2026_10_04/result.json`, re-verified when the dataset is built) x 32 rigid shifts (Halton indices 17-32,
  16 exact mirror pairs, per-axis 0.5-4 mm, all components non-zero), the same 32 shifts for every state. Calibration used indices
  1-16, so shift vectors are disjoint (checked). Pair-major order keeps a partial run balanced; 9 h launch deadline, 12 h limit.
- **Contrast and rule (OpenFOAM side):** S = (mean R(+) - mean R(-))/2 over matched phases for D0/D1/D2 x drag/downforce, in N;
  SE from the pooled residual after a jointly fitted linear translation term; resolved iff |S| > 3 SE and |S| > 3 sigma_cal/8
  (strict; sigma_cal from the X3 calibration: drag 1.05e-4 N, downforce 5.94e-4 N).
- **Verdict (both solvers):** six required comparisons (sign of S per direction and response). AGREE = all resolved in both and
  signs agree; DISAGREE = any one resolved in both with opposite signs (the only outcome that stops Track C); otherwise UNRESOLVED.
  Ordering among perturbed states and baseline-subtracted differences are reported, not required.
- **Blind hold:** the formal OpenFOAM data are downloaded and hash-verified but not analyzed (`scripts/analyze_xfid_formal_openfoam.py`
  refuses without `--unblind`) until part B (WaterLily-C: Candidate C identity/runtime/source, the 7 perturbed phi hashes, its
  deterministic floor, source-bound verifier) is immutably registered; part B may not change any rule here.
- **Scope of any verdict:** uncertified geometry, reduced-laminar Re = 80 profile, v17 flow_24 on the WaterLily side; no grid-independence,
  high-Re or full-vehicle claim.

## Pre-run validation

`tests/test_xfid_gridphase_x3.py` (5 passed): shift mirrors/range/determinism; 3-axis translation; calibration analysis; the whole runner
with stub OpenFOAM; formal analysis recovers planted contrasts and the AGREE/DISAGREE/UNRESOLVED rules. The runner code is the
calibration runner (which completed 32/32 on Kaggle) with only the registered criteria hash changed.
