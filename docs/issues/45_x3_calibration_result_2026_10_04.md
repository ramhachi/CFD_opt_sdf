# #45 X3 calibration result: 32-phase baseline ensemble (host-verified)

Evidence class: `openfoam_stage_v_gridphase_calibration_uncertified_geometry`. Measurement only: **not an XFID response; no
floor is adopted (the formal registration adopts floors); all six qualification flags remain false.** Design and registration:
`45_x3_design_2026_10_04.md`, `docs/evidence/xfid_gridphase_x3_2026_10_04/calibration/x3_criteria.json`
(SHA-256 `ea66bb60...d8ac3`). Evidence: `.../calibration_result/`.

## Run

Kernel `ramhachi888/cfd-opt-sdf-xfid-gridphase-x3` v1, Ubuntu 24.04.5 (Noble), 0.65 h; 32/32 cases COMPLETED (16 mirror pairs of
registered rigid shifts, 0.5-4 mm per axis, all components non-zero); 229-file manifest re-hashed on the host, 0 mismatches;
runner SHA equals the committed runner.

## Result (analysis fixed before the run: `scripts/analyze_xfid_gridphase_x3_calibration.py`)

| response | ensemble mean | phase noise sigma_e (28 dof) | SE of 32-mean | split-half observed / predicted | 1/sqrt(M) accepted |
|---|---:|---:|---:|---:|---|
| drag | 0.376517 N | 1.05e-4 N (0.028%) | 1.85e-5 N | 1.16 | yes (band 0.5-2.0) |
| downforce | 0.244202 N | 5.94e-4 N (0.243%) | 1.05e-4 N | 1.21 | yes (band 0.5-2.0) |

- Linear translation terms (fitted, mirror pairs cancel them in an ensemble mean): drag -1.3e-5 / -6.2e-6 / -6.3e-5 N/mm (x/y/z),
  downforce -2.4e-5 / -4.2e-5 / -9.3e-5 N/mm.
- **The unshifted X2 baseline is an outlier:** drag 0.374269 vs ensemble mean 0.376517 (-2.2e-3 N), downforce 0.242241 vs 0.244202
  (-2.0e-3 N), i.e. 0.6-0.8%, consistent with the symmetric-phase jump seen in X2. Baseline-subtracted differences against a single
  unshifted run are therefore unreliable; contrasts must be built from ensembles at matched phases.
- For a contrast S = (R+ - R-)/2 with each state a 32-phase mean, the implied standard error is sigma_e/8: drag 1.3e-5 N,
  downforce 7.4e-5 N (assuming the same phase noise for perturbed states; the formal data measures its own).

## What this does and does not support

Supported: single-state grid-phase noise is about 0.24% (downforce) and 0.03% (drag) of the force; the registered 1/sqrt(M)
averaging check passed for both responses; ensembles of 32 phases bring the centered-secant standard error to about 7e-5 N
(downforce) and 1e-5 N (drag).
Scale check against FD-06 (WaterLily upstream+floor, **not** Candidate C; design scale only): |S| at epsilon = 5 mm of 5.0e-4, 4.9e-4
(D1, D2 downforce) would be about 6.7 and 6.6 standard errors; the other four contrasts are 26-66. With the 3x rule, D1/D2 downforce
would stay resolved only if OpenFOAM's physical response is at least about 45% of WaterLily's; below that they are UNRESOLVED.
Not supported: any XFID verdict, any claim about OpenFOAM's physical response size (unmeasured), geometry certification, or a flag change.
