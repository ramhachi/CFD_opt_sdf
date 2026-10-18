# T2-0b registered feasibility record (#57): verdict **T20B_NO_GO**

Registration status: `REGISTERED_FROZEN` (`docs/t20b_registration_2026_10_19.md`, SHA-256 fa06aa4e...0595, unchanged since freeze 1; freeze 2 in `freeze.json`).
Evidence class: descriptive numerical and capability evidence for one 2D section (Tyrrell 026 single element, Re_c 4.6e5, moving ground, OpenFOAM v2512 on
Kaggle CPU). All qualification flags stay false; `shape_update_allowed=false`. Thresholds were set after T2-0a was visible (`verdict.json`:
`thresholds_set_after_exploratory_visible: true`).

## Record (commands, results, artifacts)

| item | value |
| --- | --- |
| source commit (frozen) | 941e8a766376cb8c87cda9a344ee1f6350f9bb95 |
| kernel W | `ramhachi888/cfd-opt-sdf-t20b-wf` v1, runner SHA-256 b10aea0d...2602, Intel Xeon 2.20 GHz, 4 vCPU; 60/60 COMPLETED, 0 continued; `kernel_wf_run1/` (artifact manifest d3b7dda1...973b, 1382 files verified after download) |
| kernel L | `ramhachi888/cfd-opt-sdf-t20b-lm` v1, runner SHA-256 01889630...03b4; 4/4 COMPLETED; `kernel_lm_run1/` (manifest e8435166...254d, 160 files verified) |
| submissions | one each, no resubmission, no amendment; development smoke 3 (`smoke/attempt1-3`, `freeze.json`) |
| analysis | `.venv/bin/python scripts/analyze_t20b.py --wf docs/evidence/t20b_registered_2026_10_19/kernel_wf_run1/t20b --lm docs/evidence/t20b_registered_2026_10_19/kernel_lm_run1/t20b --out docs/evidence/t20b_registered_2026_10_19` run once -> `analysis.md`, `verdict.json` (committed unchanged) |
| not archived | `mesh.msh.gz` of every case (41 MB; SHA-256 in each `EXCLUDED_MESH_SHA256.txt`; also recorded in each case manifest), and the smoke attempt 1-2 `*.gz` logs (hashes in `EXCLUDED_GZ_SHA256.txt`, see `freeze.json`) |
| integrity | `SHA256SUMS` (repo-root paths), checked with `scripts/check_sha256sums_tracked.py` |
| local validation | `pytest -q tests/test_t20b.py` 22 passed; `tests/test_t20a_kernel.py tests/test_t20_case.py` 73 passed; full `pytest -q` 2884 passed, 50 failed (the pre-existing missing-`work/` fixture failures noted in STATE.md, none in T2-0 tests); `compileall src tests` ok |

## Gates (sa-wf candidate, med30 primary; numbers from `verdict.json`)

| gate | result | numbers |
| --- | --- | --- |
| G2 data level | **FAIL** | mean \|e\| 4.24 % at nominal (< 5 %), 5.45 % with the +0.15 deg incidence shift (> 5 %); peak fails: Cl(0.179) = 1.412 > Cl(0.134) = 1.396 (1.2 % above, tolerance 0.5 %); rise breaks after h/c 0.179 |
| G2d data differences | PASS | relative increment error 0.288 (<= 0.30) |
| G3a mesh level | PASS (predicted fail) | max \|Cl_fine30/Cl_med30 - 1\| = 4.46 % (h/c 0.179) |
| G3b mesh, incidence derivative | **FAIL** | d per deg med30/fine30: 0.130/0.124 (0.224), 0.068/0.078 (0.134) pass; 0.055/0.082 (0.09) fails (difference 0.026 > max(0.020, 0.010)); expected sign at 0.224 holds |
| G3c mesh, ride-height differences | PASS | 0.236 (<= 0.25) |
| G4 model (SST vs SA) | PASS | d 0.132 vs 0.130 (0.224), 0.068 vs 0.068 (0.134) |
| G5 cost | PASS (non-discriminating) | median 0.24 min, max 0.26 min to the Cl plateau incl. meshing (capped 5000-iteration wall 5.5 min median) |
| G6 small step | **FAIL** | 0.224: d(0.25) 0.131 vs d(1) 0.130, sigma_mesh 0.0023, resolved; 0.134: d(0.25) 0.065 vs 0.068 consistent, but sigma_mesh 0.0048 and the +-0.25 deg change 0.0327 < 5 sqrt(2) sigma = 0.0341, not resolved |

## Labels and descriptive results (never change the verdict)

- Cl, sa-wf, delta alpha 0 (experiment / coa30 / med30 / fine30 / sst-wf med30): h/c 0.671 0.903/0.944/0.948/0.937/0.968; 0.448 1.009/1.063/1.065/1.047/1.092;
  0.313 1.145/1.211/1.211/1.195/1.252; 0.224 1.286/1.360/1.345/1.308/1.405; 0.179 1.361/1.368/1.412/1.349/1.479; 0.134 1.385/1.339/1.396/1.400/1.435;
  0.09 1.370/1.296/1.312/1.306/1.221.
- G2 robustness `MARGINAL`; `G2_DISJOINT_OK` (mean \|e\| 4.73 % at h/c 0.313 and 0.179); fine30 mean \|e\| 2.90 % with the peak at 0.134, coa30 4.39 % with the peak at 0.179;
  `agreement_mesh_specific` false.
- Replication: the 5 shared med30 heights equal T2-0a to all printed digits (max relative difference 0.0); the med30 h/c 0.224 mesh SHA-256 is identical in T2-0a,
  kernel W and kernel L (ac121835...af09). gmsh/OpenFOAM were bit-deterministic on Kaggle for an identical geometry, so the **negative control |dCl| = 0 measures
  determinism, not noise**; the noise that matters for differences is the remeshing jump at a new incidence (sigma_mesh 0.0023 at 0.224 and 0.0048 at 0.134, i.e.
  0.17 % and 0.35 % of Cl; smallest resolved incidence change 0.05 deg and 0.20 deg).
- Incidence scans (Cl at -1, -0.5, -0.25, 0, +0.25, +0.5, +1 deg): 0.224: 1.198, 1.274, 1.314, 1.345, 1.380, 1.405, 1.458; 0.134: 1.312, 1.362, 1.372, 1.396, 1.405, 1.427, 1.449.
- Model spread: SST minus SA at med30 runs from +2.0 % (0.671) to -7.0 % (0.09) of the SA value; SST d at 0.09 = 0.030 per deg vs SA 0.055 (descriptive height).
- LM (kernel L, wr2, 2000 SST + 12000 LM iterations): `LM_DATA_AGREES`: cycle-mean Cl 1.325 / 1.519 / 1.392 at h/c 0.224 / 0.134 / 0.09 (mean \|e\| 4.77 %, peak at
  0.134), half-window differences 0.2-0.4 %, but a limit cycle with Cl std 0.009 / 0.128 / 0.131 (0.6 %, 8.4 %, 9.4 % of the mean); about 3.5 h per case (25 min SST + 181-186 min LM, about 130k cells).
  Single mesh; not an in-loop evaluator at this cost.
- Adjoint: `ADJ_FAILED`. The kernel-L primal restarted in adjointOptimisationFoam converged (final initial residuals p 9.9e-6, U 3-5e-6, nuTilda 1.5e-6;
  `ADJ_PRIMAL_UNCONVERGED` false); the frozen-turbulence adjoint (adjointLaminar, wall functions, this dictionary set) ran 1322 iterations and stopped with SIGFPE in
  GAMG while solving pa (returncode -8, 63 s); no derivative file, so no projection. This describes this implementation only.
- DAFoam: `DAFOAM_NOT_ATTEMPTED` (registration section 5).
- Cost and size: median capped wall 3.7 / 5.5 / 10.4 min and 8.6k / 14.5k / 26.4k cells for coa30 / med30 / fine30; Cl settles in about 100-150 iterations, so the time to the
  plateau including meshing is about 15 s on med30. y+ on the airfoil (wall-function cases): averages 25-33, maximum 69 (the minimum, near the stagnation point
  and the sharp TE, is below 11 in 60 of the 61 registered wall-function cases, 8.5-10.4 for sst-wf; the exception is coa30 h/c 0.671 at 12.7; flagged per case in `analysis.md`).
- Cd (no experimental Cd): sa-wf med30 0.021-0.062 from h/c 0.671 to 0.09, 18-35 % below Genua's Med30SA as in T2-0a.

## Conclusion (separate from the record)

The registered verdict is **T20B_NO_GO**: for this 2D section, the SA wall-function evaluator on the registered primary mesh does not meet the frozen rules.
Three gates fail: the data level (the downforce maximum lands at h/c 0.179 instead of 0.134, and the 5 % mean error is exceeded once the 0.15 deg incidence
ambiguity is applied), the incidence derivative at the separated height h/c 0.09 differs by 32 % between med30 and fine30, and at h/c 0.134 a +-0.25 deg change is not
resolved above the remeshing noise. Model form (SST vs SA derivatives), ride-height differences, mesh level and cost pass. Per the pre-agreed table this NO-GO
has two next actions: G2 -> a wall-resolved or transition (LM) evaluator study or a different validation case before any high-Re evaluator; G3b/G6 -> a
mesh-family/remeshing-noise study (fixed-topology morphing instead of remeshing) before reuse. For #66 item 1 a registered go/no-go now exists and it is NO-GO,
so the high-Re evaluator cannot be adopted on this basis. No claim is made beyond the 2D section scope (registration section 7).
