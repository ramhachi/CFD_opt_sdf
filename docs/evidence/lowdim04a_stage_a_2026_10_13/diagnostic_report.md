# LOWDIM-04A Stage A: local dual-grid model at the accepted parent

Terminal classification: **LOCAL_FEASIBLE_CONE_FOUND**. Issue: [#51](https://github.com/ramhachi/CFD_opt_sdf/issues/51). Evidence class: bounded two-grid local model at the LOWDIM-03 parent, fixed four-direction basis, Re 80,
+-1.25 mm. CFD runs 18 (two Kaggle T4 kernels, one attempt, no rerun); `selected_delta=null`, `shape_update_allowed=false`, all qualification flags false, reinitialization none.
Freeze `c0532d145f2b6a8813a3ca0372b8bc4148c01944ee0920622cedc8331aa53b43`; source commit `23bbf3c1f8e2a6ee6a3ef36fdaf4e5ce6e1f5dca`; analysis sha256 `414d08677fb263db09e33f9a253d004c505fd4910d1859261ec6ffc5c4fd119d` (written once after one `--check` with zero integrity failures).
The registration is **non-blind** and disclosed that FOUND was near-certain and says little about the actual gain ([prerun note](prerun_note.md)). A FOUND is not a go-ahead.

## Integrity

Both kernels reached DONE with no ERROR; all manifests, per-state identity tables (both byte orders), GPU identity, wall-time budgets and host force recomputations passed. **The fresh parent runs were byte-identical to the retained
LOWDIM-03 s1.25 mm force CSVs on both grids** (parent gate), which is also evidence that the Kaggle T4 environment reproduced the earlier run. All nine states per grid were at the hard count N = 8272 by construction.

## Recorded result (from [analysis](lowdim04a_analysis.json))

Centered secants at the parent, N per m (per unit-max-norm basis direction):

| | D0 | D1 | D2 | P1 |
| --- | ---: | ---: | ---: | ---: |
| flow_24 downforce | +0.320 | -0.166 | -0.135 | -0.129 |
| flow_24 drag | -0.327 | -0.062 | -0.192 | -0.115 |
| flow_32 downforce | +0.749 | +0.052 | -0.151 | -0.398 |
| flow_32 drag | +0.076 | -0.106 | -0.141 | +0.006 (**unresolved**: contrast 1.5e-5 N <= 3e-5 N) |

- One of sixteen components is unresolved. Sign flips between the grids (resolved): downforce D1, drag D0. The grids agree on the downforce vector at the parent (cosine 0.864) and disagree on drag (0.102).
- Against the GRID-01 vectors at the baseline (+-2.5 mm): flow_24 downforce cosine 0.923 but the D0 slope fell from 0.781 to 0.320 N/m after one 1.25 mm step; flow_32 downforce cosine 0.999 (D0 0.936 to 0.749).
- Cone: main `t*` 0.2576 N/m, L1-robust `t*` 0.2006 N/m; single-grid references 0.406/0.384 (flow_24) and 0.781/0.710 (flow_32); every solution KKT-verified. Predicted 1.25 mm downforce gains (linear model): main 2.02e-4 N (flow_24)
  and 5.70e-4 N (flow_32); robust lower bounds 1.55e-4 and 4.88e-4 N; all above the 3e-5 N floor. Normalized step `m` 1.595 (main) and 1.617 (robust); robust basis coefficients about +0.54, 0.00, +0.38, -0.41 mm (D0, D1, D2, P1).
- Cosine to the prior LOWDIM-03 robust direction: 0.903 (robust) in coefficient space, 0.983 spatially (Gram matrix); main 0.870 and 0.978.
- Volume (first order, reported only): the robust solution predicts a **decrease** of the continuum zero-set volume of 2.1% and of the smoothed volume of 1.6% of the parent (D0 coefficient +0.535 mm). The lattice count is 8272 for all states and
  constrains no physical or sub-voxel volume.

## Descriptive, post hoc and unregistered: the even parts

All sixteen even parts are negative (drag as well as downforce); their cause is untested (physical curvature, a baseline near an extremum, or loss of the signed-distance property). They are large: flow_24 downforce D0 -6.9e-4 N (the even part is 1.7 times half the contrast),
P1 -2.0e-4 N; flow_32 D0 -2.6e-4 N. The previous step's even part was 42% of its odd part, which is what was disclosed before the run; here it is 172% (flow_24 D0) and 122% (flow_24 P1), larger than disclosed.
A diagonal-curvature estimate (formula: linear term + sum over the four basis directions of (w_i / 1.25 mm)^2 * even_i, with w the robust \`basis_coefficients_m\` and the even parts from the analysis JSON; cross terms ignored; not a registered model) gives, for the robust solution, flow_24 downforce
+1.9e-5 N (linear +1.7e-4 N) and flow_32 downforce +4.5e-4 N. The flow_24 figure is the difference of two terms of about 1.6e-4 N each, so **its sign and size are not established**; it only shows that the linear gain is not a forecast. (The same estimate gives flow_24 drag -2.7e-4 N;
the flow_32 drag estimate is jitter-level, dominated by the unresolved P1 even part, and is not evidence of drag nonincrease.) The registered next step is an actual-primal ladder (Stage B), which needs its own preregistration.

## What is and is not established

Established, for this parent, fixed basis, two grids, Re 80 and +-1.25 mm: the responses and secants above; under the stated linear model and normalization a cone with the stated `t*` exists; the comparison with GRID-01. Not established:
a gain (the linear model ignores a curvature of the same size as the gain on flow_24), drag nonincrease (flow_32 drag is 0 by the active constraint and its P1 secant is unresolved), volume feasibility beyond the lattice count, grid convergence, #26, #30, optimizer or second-iteration progress,
flow_32 noise (the 3e-5 N floor is nominal). No Stage B is authorized by this verdict.

## Validation

See [validation.json](validation.json) and the [post-run review](independent_review_postrun.md).
