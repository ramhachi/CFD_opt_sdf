# #45 XFID-01 formal verdict: UNRESOLVED

Evidence class: `xfid_formal_cross_fidelity_uncertified_geometry`. Rules: part A formal criteria (`xfid_gridphase_x3_2026_10_04/formal/x3_criteria.json`,
SHA-256 `c2523b23...acbc`) applied unchanged by `scripts/xfid_final_verdict.py` (hash bound in part B criteria `39974802...775b`).
All six qualification flags remain false. **Scope: uncertified geometry (X1 practical gate), Re = 80 reduced-laminar profile, WaterLily-C
flow_24 / v17 on one side and OpenFOAM v2512 Stage V (25-50 mm surface cells) on the other; no grid-independence, high-Re or full-vehicle claim.**

## Procedure followed

Part A (OpenFOAM, 224 cases, 2.62 h, Ubuntu 24.04) and part B (Candidate C on T4, 8 states, 28 min) were registered before their runs; both outputs
were hash-verified (1,573 and 49 files, 0 mismatches) and committed before analysis; part A was held blind until part B was registered and
finished; then `analyze_xfid_formal_openfoam.py --unblind` and the verdict script were run once. No rule, threshold or case was changed after seeing data.

## Result (six required sign contrasts; S = (R(+5 mm) - R(-5 mm))/2 in N)

| contrast | OpenFOAM S | 3 SE (floor 3 sigma_cal/8) | resolved | WaterLily-C S | signs |
|---|---:|---:|---|---:|---|
| D0 downforce | +3.87e-3 | 2.2e-4 | yes | +3.81e-3 | agree |
| D0 drag | -4.76e-3 | 7.5e-5 | yes | -6.5e-4 | agree |
| D1 downforce | +1.16e-4 | 2.2e-4 | **no** | -4.9e-4 | (not compared) |
| D1 drag | -5.0e-5 | 7.5e-5 | **no** | -3.4e-4 | (not compared) |
| D2 downforce | -4.2e-4 | 2.2e-4 | yes | -4.9e-4 | agree |
| D2 drag | -4.1e-4 | 7.5e-5 | yes | -8.5e-4 | agree |

**Verdict: UNRESOLVED.** Four of six contrasts are resolved in both solvers and all four agree in sign; no resolved contrast disagrees, so by the
registered rule nothing stops Track C and nothing is declared AGREE. WaterLily-C is deterministic (baseline repeat bit-identical) so its floor is 1e-8 N;
the two unresolved contrasts are both D1 and unresolved on the OpenFOAM side only. The D1 downforce signs differ, but the OpenFOAM value is only about half of its
3 SE floor, so it is **not** a disagreement and must not be read as one.

## Observations (not part of the verdict)

- OpenFOAM phase noise matches the calibration: pooled residual std 5.8e-4 N (downforce) and 2.0e-4 N (drag) versus calibration sigma_e 5.9e-4 / 1.05e-4 N;
  SE of S is 7.2e-5 / 2.5e-5 N with 32 matched phases (183 residual dof).
- Magnitudes: D0 downforce agrees within 2% (3.87e-3 vs 3.81e-3 N) and D2 downforce within about 13%; drag magnitudes differ more (D0 drag about 7x larger in
  OpenFOAM, D2 drag about 2x smaller). Magnitude agreement was not required and is not claimed.
- To resolve the two D1 contrasts at their current estimated size the standard error would have to fall to about |S|/3: roughly 72 matched phases for D1 drag and 110
  for D1 downforce (1/sqrt(M) scaling from the calibrated model, point estimates are themselves noisy). That is a new registered round (or a larger epsilon),
  not a reanalysis; adding phases after seeing this result must be preregistered.

## Not claimed

No AGREE, no DISAGREE, no Candidate C or OpenFOAM qualification, no gradient/FD/optimizer/topology/shape-update change, no statement about D1 beyond "unresolved".
