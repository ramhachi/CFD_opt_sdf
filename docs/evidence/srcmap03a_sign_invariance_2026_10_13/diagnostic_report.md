# SRCMAP-03a: P22-v17 boundary-sign invariance certificate

Terminal classification: **P22_V17_SIGN_INVARIANCE_CERTIFIED**. Issue: [#54](https://github.com/ramhachi/CFD_opt_sdf/issues/54).
Evidence class: solver-free arithmetic certificate over retained evidence. CFD runs 0, Kaggle submissions 0,
`selected_delta=null`, `shape_update_allowed=false`; every qualification flag unchanged.

This result does **not** resolve source-mapping nondeterminism and does not qualify any signer. It shows that, for
the retained v17 baseline lattice and source STL only, the P22 hard mask is independent of the signs assigned to
boundary-ambiguous nodes, and that the registered LOWDIM gates keep their pass/fail classification.

## Authority, freeze and the two executions

- Integration parent `f82a5e037409f7e17e8542dfe05043d3bade03f8` (descends from the SRCMAP-02 record `910ead1…`;
  difference: a documentation-only change). Source STL SHA-256 `5e6d2107…8d11`; baseline NPZ `7a972b33…`, state
  `02f48f64…`; no input, SRCMAP-01 or SRCMAP-02 evidence was modified.
- Final freeze `8eabccd3dbe4b67e26852e9581f5b4f8696f4bac2147cc481ff9bdaa463cab1e` (16 file hashes, parameters and
  precedence rule), enforced at run time by `verify_freeze`; script SHA-256 `9064bb8c…3922`; run at git head
  `f4b5dd3b6fcedad3481f5f6ca819fe30c5b71fb6`.
- **Attempt 1** (freeze `2d733e6f…`) stopped `INCOMPLETE` in the preflight: the SRCMAP-01 manifest check treated two
  living documents as frozen. No state, mesh or field had been loaded. This was handled as **Amendment 1** (plan,
  refreeze, independent re-review), not as a re-execution of unchanged source. All attempt-1 files are retained.
- Independent reviews: round 1 PASS_WITH_REQUIRED_CHANGES (all applied), round 2 PASS, round 3 (Amendment 1) PASS;
  see [pre-run review](independent_review_prerun.md), [approval](prerun_approval.json).
- Disclosure carried from the plan: an exploratory prototype passed every predicate it exercised before
  registration, so this is a confirmatory replication with frozen code, not a blind preregistration. The frozen
  script reproduced the prototype's figures on its own.

## Results (all from [certificate.json](certificate.json))

| Predicate | Observation | Frozen criterion |
| --- | --- | --- |
| P1 gap | band `B={\|phi\|<1e-6}` has 5370 nodes (4075 negative, 797 positive, 498 exact zero); largest inside magnitude `2.385e-8`, smallest outside `0.02499998`, ratio `1.05e6` | ratio >= 1e3, B non-empty |
| P2 outside signs | 380,015 outside nodes; winding number within `4.44e-16` of {0,1}; 0 sign mismatches against the registered field; mesh watertight and consistently wound, hashes match | <= 1e-9 and 0 mismatches |
| P3 occupancy | 10,752 cells touch `B`; over all 2^8 patterns at amplitude `1e-6` and at the actual magnitudes: 0 ambiguous cells, 0 cells differing from the reference; both endpoint fields give 8272 solid centers equal to the reference mask; endpoint values equal the enumerated extrema; smallest `\|centre\|` over patterns `3.124e-3` | 0 ambiguous, count 8272 both ends |
| P4 gates | clearance worst case `0.349999` m (gate 0.15; baseline `0.349999994`); Eikonal median `2.46e-7` plus bound `1.39e-4` < 0.10; smoothed-volume bound `1.05e-5` m³ (relative `1.18e-4`, criterion < 1e-3), retained parent relative change `-1.183%` with worst range `[-1.196%, -1.170%]` inside the 10% band; cell components 1 at both endpoints | each gate passes with the bound |
| P5 controls | 19 retained v17 fields (18 SRCMAP-01 variants + Oct12 replay; the two v16 controls excluded): 3,988 sign differences in total, **0 outside `B`**, every field has the reference mask | population 19, 0 outside, all masks equal |

Descriptive margin: the endpoint fields still give the reference mask up to a uniform ambiguity amplitude of
`3.78e-3` m, about `1.6e5` times the largest observed band magnitude. The certificate itself is bound to amplitude at
most `1e-6` m.

## What is and is not established

Established, for this STL and this v17 lattice: (i) signs outside `B` agree with an independent numerical winding
number at every node (a numerical certification in Float64, not a formal proof); (ii) for every sign assignment of the
ambiguous nodes, exhaustively per cell through the production `_corner_mean`, no h-cube centre changes sign, so the
P22 hard mask and count (8272) are identical; (iii) the clearance, Eikonal-median, smoothed-volume-band and
cell-component gates keep their pass/fail classification, by explicit bounds (not invariance of the observables
themselves: smoothed volume and Eikonal values do change at the 1e-8 to 1e-4 level); (iv) 19 retained variants,
including the independent `contains` composition that differs at about 3,900 nodes, agree.

Not established: mapping reproducibility or the cause of nondeterminism; any signer; correctness of any sign inside
`B` (no ground truth exists on the surface); any candidate or perturbed state; other STLs or lattices; invariance for
a signer that errs outside `B`; CFD response; physical or continuum volume; grid convergence. The plan's earlier
"130-entry" manifest wording at `prerun_plan.md:43` is superseded by Amendment 1 (128 entries checked, two living
documents excluded).

## Consequence for the successor stage (not performed here)

The P22-v2 proposal gated registration on "source-mapping reproducibility resolved". This certificate is the
evidence on which a separate decision record may supersede that precondition for a bounded, representation-specific
contract bound to the immutable baseline artifact. That registration is Stop 2 and is a separate freeze and commit.

## Validation

See [validation.json](validation.json): twelve new tests pass; full pytest has the same 48 failure IDs as the
SRCMAP-02 record and as a clean baseline at the parent (new 0, resolved 0), not an all-pass suite; `compileall` of
`src`, `scripts`, `tests` and `git diff --check` pass. The [post-run review](independent_review_postrun.md) limits
approval to recording this result.
