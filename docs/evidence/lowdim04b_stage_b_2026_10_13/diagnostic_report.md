# LOWDIM-04 Stage B: actual-primal ladder along the Stage A solution

Terminal classification: **LOWDIM04B_ACCEPT**, at the smallest step (0.3125 mm). Issue: [#51](https://github.com/ramhachi/CFD_opt_sdf/issues/51). Evidence class: bounded two-grid actual-primal capability at the accepted LOWDIM-03 parent, one fixed direction
(the Stage A L1-robust cross-grid solution), a four-step ladder with two reverse diagnostics, Re 80. CFD runs 14 (two Kaggle T4 kernels, one attempt, no rerun); `selected_delta=null`, `shape_update_allowed=false`, all qualification flags false, reinitialization none.
Freeze `0cc5a112fd98b81e80b4471afa94ab33b5d9d824f554e5fb76688c7dba3537ed`; source commit `801e7e8eb15890b6b674cf014731cd45822b6a81`; analysis sha256 `ab248289df8c4c26df16ee09ed5807ec201de439e2ddd90ddb6e92978cda2ffc` (one `--check` with zero integrity failures, then one `--write`). Non-blind; the preregistration disclosed that the flow_24 outcome was a toss-up and that flow_32 drag at small steps is at jitter level.

## Integrity

Both kernels DONE with no ERROR; manifests, identity tables (both byte orders), GPU identity, budgets and host force recomputations passed. The fresh parent runs were again byte-identical to the retained LOWDIM-03 s1.25 mm force CSVs on both grids. All seven states per grid are at the lattice count N = 8272.

## Recorded result (from [analysis](lowdim04b_analysis.json)); changes relative to the parent in newtons

| step (mm) | flow_24 downforce | flow_24 drag | flow_32 downforce | flow_32 drag | rule |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0.3125 | +3.566e-5 | -5.71e-5 | +1.148e-4 | -1.15e-5 (small) | **accepted** (worst-grid gain 3.566e-5 N) |
| 0.625 | +2.966e-5 | -1.29e-4 | +2.180e-4 | -3.57e-5 | not accepted (flow_24 gain 0.34 micro-newton below the floor) |
| 0.9375 | +6.4e-7 | -2.13e-4 | +3.144e-4 | -6.33e-5 | not accepted |
| 1.25 | **-5.247e-5** | -3.08e-4 | +4.184e-4 | -7.51e-5 | not accepted (flow_24 loses downforce) |
| reverse -0.625 | -1.54e-4 | +7.4e-5 | -2.73e-4 | -2.05e-5 | diagnostic only |
| reverse -1.25 | -4.12e-4 | +8.9e-5 | -5.87e-4 | -5.30e-5 | diagnostic only |

Selected: 0.3125 mm, the only step passing the registered rule (strictly more than 3e-5 N downforce gain and a computed drag change <= 0 on both grids, five geometry gates). The accepted worst-grid gain is **3.57e-5 N, 19% above the nominal floor**, on flow_24; flow_32 gains 1.15e-4 N with a drag change
of -1.15e-5 N, within the 3e-5 N small-drag margin (the computed sign is not noise-resolved). The reverse diagnostics lose downforce on both grids at both steps, and raise flow_24 drag.

Descriptive (never used in the verdict): the odd/even parts of the 1.25 mm pair are flow_24 +1.80e-4 / -2.32e-4 N and flow_32 +5.03e-4 / -8.4e-5 N. A hindcast against Stage A, for flow_24 downforce, actual / linear / diagonal-curvature estimate: 0.3125 mm +3.6e-5 / +4.3e-5 / +3.3e-5 N; 0.625 mm +3.0e-5 / +8.6e-5 / +4.8e-5; 0.9375 mm +6e-7 / +1.3e-4 / +4.3e-5;
1.25 mm **-5.2e-5** / +1.7e-4 / +1.9e-5 N. The linear model that gave Stage A's FOUND over-predicts the actual flow_24 gain at the full step by 2.2e-4 N, and the diagonal-curvature estimate misses too once the step grows (cross terms and higher order); both agree with the actual only at the quarter step.
flow_32 is predicted well at every step (downforce actual 1.15e-4 to 4.18e-4 N against estimates 1.2e-4 to 4.5e-4 N).

## What is and is not established

Established, for this parent, direction, ladder, two grids, Re 80: the actual changes above; that exactly one step (0.3125 mm) met the registered rule; the hindcast comparison. Not established: a physical gain (the accepted gain is 3.6e-5 N, about 0.011% of the 0.33 N downforce, below the Stage V resolution of about 2.2e-4 N),
drag nonincrease (flow_32 drag is within jitter at the selected step), that the accepted step beats noise (the rule has no multiplicity control: four correlated steps, a max-min selection and a floor of about 1 sigma, so the selected gain is biased upward and is not an estimate of the true gain), grid convergence,
#26, #30, an optimizer or second-iteration qualification, or a go-ahead. The result is a bounded capability statement. A full Stage A step is **not** recommended by this data (flow_24 loses 5.2e-5 N).

## Exit rule

Per the plan and the preregistration, the LOWDIM-04 track ends here and #51 is closed; no third cycle starts on gain headroom alone.

## Validation

See [validation.json](validation.json) and the [post-run review](independent_review_postrun.md).
