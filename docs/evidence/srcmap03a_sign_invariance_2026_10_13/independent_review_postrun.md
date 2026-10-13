# SRCMAP-03a independent post-run review

Reviewer: independent Claude Sonnet subagent with fresh context (not the pre-run reviewer), orchestrated by the
authoring session; not a human reviewer. Scope: approve or reject only the **recording** of this result; no downstream
use (P22-v2 registration, LOWDIM-04A) is approved or rejected here.

## Review at commit `a5bb58d`: PASS_WITH_REQUIRED_CHANGES, no blocker

The reviewer re-derived the results with its own code (no use of the certify script): band 5370 nodes (4075 negative,
797 positive, 498 exact zero), inside/outside magnitudes and ratio; all 10,752 touching cells enumerated over 241,946
sign patterns at amplitude 1e-6 and at the actual magnitudes (0 sign changes, minimum centre magnitudes equal to the
recorded values to the last digit; endpoints 8272/8272 equal to the reference mask); a separately written winding number
at all 380,015 outside nodes (max distance from {0,1} 4.44e-16, 0 mismatches) and at the 11,903 nodes within 0.05 m of
the surface; the controls (19 fields, 0 outside the band, all masks equal, the two v16 files skipped); the clearance
worst case, the smoothed-volume bound and the parent range, all exactly equal to the record. Integrity checks: the 16
frozen hashes match at the run commit `f4b5dd3` and the frozen files are unchanged at HEAD; no change outside the
SRCMAP-03a files, the script and the test; attempt-1 files consistent with Amendment 1; `validation.json` consistent with
the retained logs; failure-ID set identical to the SRCMAP-02 record; 12 tests pass.

Required changes (all wording or completeness; none affects a predicate) and dispositions:

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | the report's margin figure `3.78e-3` is the first failing point of a 60-point grid; the exact onset is `0.025/7 = 3.571e-3` | report reworded (grid point, exact onset, ratio about 1.5e5) |
| 2 | "same 48 IDs as a clean baseline" was inaccurate (scratch baseline: 50) | report and `validation.json` now say 48 vs 50 and cite the `FileNotFoundError` on git-ignored `work/` state |
| 3 | "sign differences" is a sign-bit count (3988; 3930 for `D_fallback`); by `phi<0` it is 3553 and 3495 | definition and both figures stated |
| 4 | gate scope: five gates of `gates()`, baseline plus one parent only; `masks_and_support_preserved` rationale loose | scope stated; rationale reworded |
| 5 | "values do change at 1e-8 to 1e-4" was stated as observed | reworded to "may change by up to the recorded bounds" |
| 6 | prototype reproduction and "flags unchanged" had no evidence in the record | reworded as the author's statement; branch-diff scope cited |
| 7 | referenced post-run review and `SHA256SUMS` were missing | this file and `SHA256SUMS` added |

Notes adopted: the mechanism (at most seven of eight corners in the band, every outside node at least about one h from
the surface, lattice aligned with the STL faces) is in the report; reviewers are subagents, stated in the report; the
smoothed-volume bound analytic value 1.0544e-5 m³ differs from the recorded float32-difference value 1.0537e-5 by 0.07%,
immaterial against the criterion. Not checked by the reviewer: the unrecorded prototype, the Eikonal median value
itself (only the bound algebra), and the Amendment 1 dry run.

## Confirmation at commit `fbbe105`: PASS for recording this result

The reviewer re-checked findings 1-7 against the committed text and recomputed the new wording (the exact onset
`0.025/7 = 3.5714e-3` from the 163 cells with seven band corners, the 3988/3930 sign-bit and 3553/3495 `phi<0` figures,
the scratch-baseline explanation, the branch-diff scope) and found no new over-claim or factual error. Items not checked
by the reviewer, added to the list above: Float32 monotonicity of `_corner_mean` beyond the computed cases (it holds by
construction for fixed-order rounded addition and is exercised by the enumeration test), and the former "qualification
flags unchanged" statement, which was replaced by the branch-diff scope claim rather than verified. The `SHA256SUMS` named in
finding 7 is generated after this paragraph in the recording commit.
