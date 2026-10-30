# LOWDIM-04A Stage A independent post-run review

Reviewer: independent Claude Sonnet subagent with fresh context (not the pre-freeze reviewer); not a human reviewer. Scope: approve or reject only the **recording** of this result; Stage B and any downstream use are not covered.

## Review at commit `7cfb241`: PASS_WITH_REQUIRED_CHANGES, no blocker

Reproduced with the reviewer's own code (own CSV reader and trapezoid rule, the production `recompute_force_n`, SLSQP with 300 random starts on an epigraph form of the L1 problem): the 18 state forces (relative difference 1.3e-15; 0 against the
production function), the 16 secants (5.6e-13 N/m; resolved flags identical, only flow_32 drag P1 unresolved, contrast 1.48e-5 N), main and robust `t*` (0.25755653831, 0.20055906516; 3e-13), the four single-grid `t*`, the coefficient vectors (1.3e-8), `m`, the predicted
1.25 mm gains and basis coefficients (identical to four digits). The sign chain was verified by rebuilding every perturbation in float64, casting to float32 and matching all eight phi hashes, the parent hash and the four direction hashes with the inventory and the Kaggle summaries;
the descriptive curvature estimate recomputes to the reported values. Integrity: the manifest gate passes on 108 entries; the 58 frozen hashes match at the source commit and at HEAD (tree id included); nothing under scripts, src, tests, infra or julia
changed after the freeze; both run identities equal the freeze (commit, runner hash, pins, failure stage none); both submission records match; the fresh parent CSVs are byte-identical to the retained LOWDIM-03 ones; `--check` reproduces integrity and the verdict; the analysis
sha equals the report; the 48 failure IDs equal the SRCMAP-02 record (0 new); 26 stage tests pass.

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | should-fix | the post-hoc estimate gave no formula | formula and inputs stated in the report |
| 2 | should-fix | "+1.9e-5 N" is a difference of two terms of about 1.6e-4 N | sign and size stated as not established |
| 3 | should-fix | the flow_32 drag number conflicts with the jitter caveats | labelled jitter-level, not evidence of drag nonincrease |
| 4 | should-fix | "as disclosed before the run" overstated (42% disclosed, 172% and 122% observed) | reworded: larger than disclosed |
| 5 | should-fix | "curvature" without the registered "cause untested" caveat | added in the report and the register |
| 6 | should-fix | the living docs dropped the non-blind and near-certain-FOUND disclosure | one sentence added to each |
| 7 | note | flow_32 drag wording; "linear model" in the phase-plan heading; the missing review file and manifest refresh | all applied (this file; SHA256SUMS regenerated and re-gated) |

Not checked by the reviewer: real Kaggle behaviour beyond the parent byte identity, `build_lowdim04a_inputs.py --check` on another machine, the full suite (log and junit used), that `--write` ran exactly once (process history is not in the repository),
the physical meaning of the negative even parts and the flow_32 floor.
