# #45 X2: OpenFOAM grid-phase probe (registered, not yet run)

Evidence class: `openfoam_stage_v_gridphase_probe_diagnostic_uncertified_geometry`. Status: **registered and
tested locally; not submitted to Kaggle.** No solver result exists. All six qualification flags remain false.
Plan: `45_next_steps_plan_2026_10_04.md` (X2). Inputs: X1 baseline STL (sha256 `1d0f2578...ac3`, 681,504 triangles).

## What is measured

The registered baseline Stage V STL is rigidly translated by 0.5, 1, 2, 4, 8 mm (both signs) along each of z, y, x
against the fixed OpenFOAM background mesh; every case regenerates the mesh from scratch with the unchanged Round 5
case template (`snappyHexMeshDict` surface level (2 3), 25-50 mm surface cells) and the reproduced OpenCFD v2512 /
Ubuntu Jammy environment. 32 cases: baseline, a baseline repeat (determinism), and 30 translations ordered by
priority (1, 2, 0.5, 4, 8 mm; z, y, x).

Recorded per case: STL hash; per-stage wall time, CPU time, sampled peak RSS; checkMesh cells/concave/failed
checks; snappyHexMesh cells per refinement level; simpleFoam iterations and residuals; drag and downforce in N
(last-25% window mean, std, drift, last value; N = coefficient x 0.32); gzipped logs and force history. A failing
stage is recorded and later cases still run; cases are never retried; no new case launches after 9 h of the 12 h limit.

## Interpretation rules (fixed before the run)

- No axis is assumed null: x changes inlet/outlet/wake distance, z changes ground clearance, y is only approximately
  symmetric. Each axis is split into a smooth part (quadratic least squares) and a residual and reported separately,
  with odd/even parts, consecutive-shift jumps and the baseline-repeat difference
  (`scripts/analyze_xfid_gridphase_x2.py`). Floor candidates are reported; none is adopted here (X3 registers floors).
- The D1/D2 realized displacement is median ~0.9 mm, p95 ~3.2 mm (X1 report). If a sub-2-mm shift moves the force
  by D1/D2-comparable amounts or more, the formal XFID design must change (larger epsilon, D0 as the main direction,
  or finer surface level) and that is brought to the user.
- The 0.68 M-triangle STL versus 2,684 triangles in the reproduced v16 fixture is an untested cost risk; the cost
  columns answer it.

## Pre-run validation (no OpenFOAM available locally)

`tests/test_xfid_gridphase_x2.py` (7 passed): parsers reproduce the retained Round 5 logs (42,619 cells, 2,969
concave, 584 iterations, drag 0.37426349 N and downforce 0.24225913 N); deterministic STL translation; the whole
runner control flow with stub OpenFOAM binaries (success, stage failure continues, deadline marks NOT_RUN);
analysis recovers a planted quadratic. The real snappyHexMesh log format and the real timings are untested.

## Registered artifacts

`docs/evidence/xfid_gridphase_x2_2026_10_04/x2_criteria.json` (+ `.sha256`), runner bound to that hash,
`scripts/prepare_kaggle_xfid_gridphase_x2.py` (stages the private dataset `ramhachi888/cfd-opt-sdf-xfid-x2-inputs`
under `work/`, not committed).
