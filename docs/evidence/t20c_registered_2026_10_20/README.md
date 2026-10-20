# T2-0c registered study (#57): verdict **T20C_MORPH_NO_GO**

Registration status: `REGISTERED_FROZEN` (`docs/t20c_registration_2026_10_20.md`, SHA-256 3e41e05f...4582, unchanged since freeze 1; freeze 2 in `freeze.json`,
SHA-256 01f40cab...060d, source commit 6d11badf). Evidence class: descriptive numerical evidence for one 2D section (Tyrrell 026 single element, Re_c 4.6e5,
moving ground, OpenFOAM v2512 SA wall functions on Kaggle CPU). All qualification flags stay false; `shape_update_allowed=false`. Thresholds were set after
T2-0a and T2-0b were visible (`verdict.json`: `thresholds_set_after_exploratory_visible` and `thresholds_set_after_t20b_visible` true).

## Record (commands, results, artifacts)

| item | value |
| --- | --- |
| source commit (frozen) | 6d11badfabfda86a4c4934ecbbb6537884195449 |
| kernel R | `ramhachi888/cfd-opt-sdf-t20c-remesh` v1, runner SHA-256 3984c1c2...81b0, Intel Xeon 2.20 GHz, 4 vCPU, 5.3 h; 82/82 COMPLETED; `kernel_remesh_run1/` (artifact manifest f3563eed...e6da, cases.tar c8e289b2...120d, 1855 files verified) |
| kernel M | `ramhachi888/cfd-opt-sdf-t20c-morph` v1, runner 3a3992f7...daee, AMD EPYC 7B12, 4 vCPU, 3.3 h; 93/93 COMPLETED; `kernel_morph_run1/` (manifest ee7f21b5...eb6e, tar 40d45adb...9982, 2097 files) |
| kernel S | `ramhachi888/cfd-opt-sdf-t20c-shape` v1, runner dfc5efc6...10b7, Intel Xeon 2.20 GHz, 3.75 h; 96/96 COMPLETED; `kernel_shape_run1/` (manifest 039c806e...1ade, tar 31453aac...cf62, 2139 files) |
| submissions | one each (2026-10-20T17:43Z), no resubmission, no amendment; development smoke 3 (`smoke/attempt1-3`, `freeze.json`) |
| download | each kernel's output (8 files) into a fresh empty directory; cases.tar checked against DONE, extracted with tarfile's `data` filter, every artifact-manifest entry present with matching SHA-256; copied here without `mesh.msh.gz` (274 files, SHA-256 in each `EXCLUDED_MESH_SHA256.txt`) |
| analysis | `.venv/bin/python scripts/analyze_t20c.py --remesh docs/evidence/t20c_registered_2026_10_20/kernel_remesh_run1/t20c --morph .../kernel_morph_run1/t20c --shape .../kernel_shape_run1/t20c --out docs/evidence/t20c_registered_2026_10_20` run once -> `analysis.md`, `verdict.json` (committed unchanged); analyzer SHA-256 c01020d4... equal to freeze 2 |
| integrity | `SHA256SUMS` (repo-root paths) split per directory because the checker passes every path to one `git ls-files` call (14935 entries exceed the argument limit): the top-level `SHA256SUMS` lists the top files and the six sub-manifests (`kernel_*_run1/SHA256SUMS`, `smoke/attempt*/SHA256SUMS`); all seven checked with `scripts/check_sha256sums_tracked.py` |
| regression (freeze 2) | full pytest in a fresh worktree at 99362391: 0 failed, 2957 passed, 73 skipped; `tests/test_t20c.py` at 6d11badf: 25 passed |
| case classes | VALID 245, UNSTEADY 14, SOLVER_FAIL 12, MECHANICAL_FAIL 0 (every morph passed the inverted-cell, fixed-node, airfoil-weight, contour and polyMesh-topology checks) |

## Gates (fine30 against xfine30; numbers from `verdict.json`, d per deg)

| gate | 0.224 | 0.134 | 0.09 |
| --- | --- | --- | --- |
| G6m small step (morph) | PASS: d(0.25) 0.1318 vs d(1) 0.1302, sigma_eff 0.00043, dCl(+-0.25) 0.066 resolved | **FAIL (noise)**: d(0.25) 0.0626 vs d(1) 0.0631 agree in value, but sigma_eff 0.0021 (cubic fit) makes the comparison UNRESOLVED | (not a gate) |
| G3bm fine30 vs xfine30 | PASS: 0.1302 vs 0.1202 (allowed 0.0326), sign ok | **FAIL**: xfine30 inputs UNSTEADY (0, +0.25, +0.5, +1 deg) | **FAIL**: xfine30 inputs SOLVER_FAIL/UNSTEADY, fine30 +1 deg UNSTEADY |
| G7m fine30 morph vs remesh | PASS: 0.1302 vs 0.1238 | PASS: 0.0631 vs 0.0779 (allowed 0.0258: the bias it cannot exclude) | **FAIL**: +1 deg UNSTEADY in both methods |
| G7m xfine30 morph vs remesh | PASS: 0.1202 vs 0.1236 | **FAIL**: UNSTEADY inputs | **FAIL**: SOLVER_FAIL inputs |
| G8m baseline realisation | PASS: s = 1 0.1302 vs B' 0.1280, s = 0.25 0.1318 vs 0.1268 | **FAIL**: s = 1 0.0631 vs B' 0.0856 (allowed 0.0214, resolved), s = 0.25 UNRESOLVED | **FAIL**: +1 deg UNSTEADY (B and B') |

Verdict **T20C_MORPH_NO_GO** (the attached scope fails at 0.134). Next action (registration section 6, first matching row): **row 5**, "steady RANS does not
settle at that (mesh, h, alpha): an unsteady/solver-convergence study there; no mesh-dependence or morph conclusion". Per-gate rows: 5 for every gate with an
UNSTEADY/SOLVER_FAIL input, 8 for G6m@0.134 (noise), 7 for G8m@0.134 (a resolved baseline-realisation disagreement).

## Labels and descriptive results (never change the verdict)

- **Noise.** Remeshed vs morphed sigma_eff (cubic fit, iterative floor): fine30 0.224 0.0104 vs 0.00043 (24x), med30 0.224 0.0026 vs 0.00028, med30 0.134
  0.0054 vs 0.00040 (14x), fine30 0.134 0.0120 vs 0.0021 (5.6x), med30 0.09 0.0035 vs 0.0015, xfine30 0.224 0.0041 vs 0.00052; pooled (geometric mean of the
  6 computable pairs) 8.2x. The smallest resolved incidence (relative to the scan's smoothness only) is 0.009 deg morphed vs 0.24 deg remeshed on fine30 at 0.224.
  Remeshing alone does not fix T2-0b's failures: every computable G6R and G3bR label fails (fine30's remeshed sigma is larger than med30's).
- **med30 (T2-0b's primary mesh) by the same rules (`MED30`: full false, attached false):** G6m passes at 0.224 and 0.134 (d(0.25) 0.0474 vs d(1) 0.0529
  at 0.134, the case T2-0b failed), G7m passes at all three heights, G8m fails at 0.134 (s = 0.25: 0.047 vs B' 0.066, resolved) and at 0.09 (UNRESOLVED), G3bm
  fails at 0.134/0.09 through the UNSTEADY/SOLVER_FAIL xfine30 inputs. Morphing removes the remeshing jumps, but near the downforce peak the morphed derivative
  carries the base mesh's realisation error (B vs B' at h/c 0.134: 26-29 % of the larger derivative on med30 at s = 0.25 and fine30 at s = 1); at 0.224 B and B'
  agree within 0.5-4 %.
- **Steadiness.** 26 cases do not satisfy a steady RANS reading: on xfine30 every h/c 0.09 case (SOLVER_FAIL: no Cl plateau after the continuation to 15000
  iterations, raw tail Cl std 2.7-5.4 %, except -1 deg UNSTEADY) and h/c 0.134 at 0, +0.25, +0.5, +1 deg (UNSTEADY, 0.7-2.0 %) in both methods, while h/c 0.134
  at negative incidences is steady (raw tail std about 1e-5, the remeshed -0.5 deg 0.49 %); on fine30 only +1 deg at 0.09 (1.9 %, as in T2-0b, in all three morph variants and the remesh). The T2-0b G3b failure at
  0.09 rested on such a case (registration section 2).
- **Mesh series (Q2).** Computable only at h/c 0.224: Cl 1.345 / 1.308 / 1.271 (med30 / fine30 / xfine30) `DIVERGENT` (equal steps), d_M 0.128 / 0.130 / 0.120
  `DIVERGENT`, d_R `NOT_RESOLVED`. `PEAK` and the fine30/xfine30 G2-by-level labels are not computable (UNSTEADY/SOLVER_FAIL inputs). med30 reproduces T2-0b's G2
  failure (mean |e| 4.24 %, 5.45 % shifted, peak at 0.179). Descriptive 0-deg sweep, experiment / coa30 / med30 / fine30 / xfine30: h/c 0.671 0.903 / 0.944 / 0.948 /
  0.937 / 0.921; 0.448 1.009 / 1.063 / 1.065 / 1.047 / 1.027; 0.313 1.145 / 1.211 / 1.211 / 1.195 / 1.161; 0.224 1.286 / 1.360 / 1.345 / 1.308 / 1.271; 0.179 1.361 /
  1.368 / 1.412 / 1.349 / 1.310; 0.134 1.385 / 1.339 / 1.396 / 1.400 / 1.326 (UNSTEADY); 0.09 1.370 / 1.296 / 1.312 / 1.305 / 1.337 (no plateau).
- **Shapes (Q3, descriptive).** `SHAPE_NOT_RESOLVED`: camber and flap at 0.224 and 0.134 are resolved, linear (d(0.25) vs d(0.5)), agree between med30 and
  fine30 and with the remeshed shapes on fine30 (a weak test: the remeshed reference carries sigma_R); heave (ride height +-0.25/0.5 mm) is not resolved at 0.134
  and 0.09, camber not on fine30 at 0.134 and on med30 at 0.09; fine30 at 0.09 is not computable (UNSTEADY input). d per mm at 0.224 (med30 / fine30): camber
  0.054 / 0.046, flap 0.082 / 0.074, heave -0.007 / -0.006.
- **Replication.** `NOT_BITWISE` against T2-0b: 36 of 41 shared remeshed geometries have the identical mesh SHA-256, largest |dCl/Cl| 3.0e-6 (gmsh writes renumbered
  variants run to run; freeze.json `predictions_note`). `CROSS_KERNEL_DIFFERENT`: 12 of 14 baselines with identical mesh SHA-256, 14 of 14 identical Cl (kernel M ran
  on AMD EPYC 7B12, R and S on Intel Xeon).
- **Cost.** Median time to the Cl plateau incl. meshing 0.16 / 0.26 / 0.58 min (coa30 / med30 / fine30); xfine30 50.3-52.7k cells, about 21 min per 5000
  iterations, 62 min with the continuation. A morph adds about 1 s.

## Conclusion (separate from the record)

The registered verdict is **T20C_MORPH_NO_GO**, and the pre-agreed next action is row 5: the steady SA wall-function RANS does not settle on the finest level
at the separated height (0.09) and at the downforce peak (0.134, incidence >= 0), so neither a mesh-dependence nor a morph conclusion is drawn there; an
unsteady/solver-convergence study at those conditions comes first. Where the flow is steady (h/c 0.224) the morph-based evaluator passes every gate:
noise down 24x, +-0.25 deg resolved, derivative within the band between fine30 and xfine30, between two baseline realisations and against the geometry-identical
remeshed cases. At 0.134 the morph removes T2-0b's remeshing jumps (G6m passes on med30) but the derivative still depends on the base mesh realisation by about
26-29 %. For #66 item 1 nothing changes (still NO-GO under T2-0b's G2); this study makes no G2 routing decision (the peak label is not computable), so the T2-0b G2
action stays the default. No claim is made beyond the 2D section scope (registration section 7).
