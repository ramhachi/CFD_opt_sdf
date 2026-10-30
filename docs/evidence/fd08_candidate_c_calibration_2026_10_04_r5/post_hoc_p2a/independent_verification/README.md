# FD-08 P2a independent verification

A separate checker recomputed A1–A4 from the Step A definitions and the registered R5 input artifacts. It did not import the primary P2a script or consume its output during calculation.

## Bound inputs and integrity

- Criteria SHA-256: `928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c`.
- Registered analysis SHA-256: `dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b`.
- Dataset input hashes: 89/89 matched.
- Force CSV hashes: 47/47 matched the runner manifest.
- `state_result.json` hashes: 47/47 matched the runner manifest.
- The manifest contains 244 entries; one non-input file, `instantiate.log`, is absent from the staged runner output. The primary and independent integrity records both disclose it.

## Numerical comparison

A1 force decompositions, A2 interval regressions, A3 window-local plateau metrics, A3′ LOO calculations/statuses, A3″ assumed-sigma rows and A4 soft-volume functionals produced 3,388 numeric comparisons. There were zero mismatches at absolute and relative tolerances of `5e-12`. The largest absolute difference was `9.14823772291129e-14` percentage points for D1 downforce's 50 µN A2 interval-spread summary.

## Checker draft corrections

Before the final independent result was written, the checker draft was corrected to follow the instruction literally: it requires four eligible interval points before LOO, then fits the remaining three points to the two-parameter `q = g + c epsilon_mm^2` model; it computes a separate median/normalizer for each five-point plateau window; and it includes all five epsilons in each assumed-sigma window. The final calculation follows those definitions. These checker-draft corrections did not alter criteria, thresholds, epsilon values, directions, primary diagnostics or the R5 verdict.

## Hashes and scope

- Checker source SHA-256: `882dbc6af417f89ef558afa5fe51aafa91ce7ff83020092b2c314f48c6ac84b2`.
- Independent result SHA-256: `5978c022eaac294c198b1970300615179eaff9cd8feb318b393de8edef7b4711`.
- Comparison and full verification record are stored beside this file with a SHA-256 manifest.

This is descriptive independent verification only. It does not change the registered R5 `FAIL`, make a new verdict, or qualify FD-08, gradients, reverse mode, optimization or shape updates.
