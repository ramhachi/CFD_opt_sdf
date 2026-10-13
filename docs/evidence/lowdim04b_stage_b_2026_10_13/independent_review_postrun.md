# LOWDIM-04 Stage B independent post-run review

Reviewer: independent Claude Sonnet subagent with fresh context (not the pre-freeze reviewer); not a human reviewer. Scope: approve or reject only the **recording** of this result; no downstream use is covered.

## Review at commit `e45bbd9`: PASS_WITH_REQUIRED_CHANGES, no blocker

Reproduced with the reviewer's own code (own trapezoid, an fsum variant, the production `recompute_force_n`, and the Julia summary values; no use of the analyzer or the contract): all 14 state forces agree across the four paths to 5.6e-16 N; the changes against the parent, the registered
rule, the selection (only 0.3125 mm passes, worst-grid gain 3.566e-5 N), the odd/even parts and the hindcast (linear term from the Stage A secants and basis coefficients, diagonal estimate) equal the recorded analysis with zero difference; the geometry gates and counts equal the inventory. The sign chain was verified (the proposal raw equals the sum of the
Stage A basis coefficients times the basis directions divided by 1.25 mm to float32 rounding; the opposite sign is off by 2.0; all six non-parent state hashes regenerate; all 14 kernel summaries match the inventory hashes). The 0.625 mm flow_24 gain (2.9655e-5 N, 3.4e-7 N under the floor) is robust: the force paths differ by at most 5.6e-16 N and the Julia
summary values give the same verdict. Integrity: the manifest gate passes; all 63 frozen hashes match at the source commit and at HEAD (tree id included); nothing under scripts, src, tests, infra or julia changed after the freeze; both submission records and run identities match the freeze; the fresh parents are byte-identical to the retained LOWDIM-03 ones; the 48 failure IDs equal the
SRCMAP-02 record; `--check` reproduces integrity and the verdict; 24 stage tests pass.

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | should-fix | dangling link to this file; manifest | this file added, manifest refreshed and re-gated |
| 2 | should-fix | "biased upward" stated as fact | reworded: likely biased upward (selection on a floor of about 1 sigma, noise model unmeasured) |
| 3 | should-fix | 0.3125 vs 0.625 mm read as a ranking | stated as a threshold artifact; accepted margin 5.7e-6 N (about 0.19 sigma at a 1 sigma floor) |
| 4 | should-fix | "cross terms and higher order" is an untested cause | "cause untested"; model-free even-part ratio 3.7 (about s^2), diagonal formula low by about 40% |
| 5 | note | the 2.2e-4 N Stage V resolution is the OpenFOAM 3-SE | stated |
| 6 | note | flow_32 drag decrease is mostly even-part; the drag hindcast is poor | stated in the report and the living docs |
| 7 | note | 30 skips here vs 23 in the SRCMAP-02 record | explained in validation.json |
| 8 | note | the living docs say #51 is closed | #51 is closed after the merge (checked) |

Not checked by the reviewer: Kaggle-side execution, the machine-bound `npz_sha256` and float-volume re-derivation, that the runner fetched the right tree, kernel logs beyond DONE and the run identity, and the causes of the 48 known failures.
