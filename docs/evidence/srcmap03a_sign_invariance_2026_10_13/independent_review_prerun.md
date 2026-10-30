# SRCMAP-03a independent pre-run review

Reviewer: independent Claude Sonnet subagent, adversarial brief, read-only on the frozen state, no execution of the
formal campaign. Orchestrated by the root Claude session under the user-authorized SRCMAP-03a scope (#54).

## Round 1 — frozen state at commit `7415185` (freeze `011725e6…`): PASS_WITH_REQUIRED_CHANGES, no blocker

Verified by experiment (synthetic data only): freeze hashes; mesh hashes under trimesh 5.1.0; the block-batching
enumeration against a per-cell brute force (30 random shapes, shared corners, exact zeros, both amplitude modes,
0 mismatches); Float32 monotonicity of `_corner_mean` (2000 draws); the Eikonal, smoothed-volume and clearance
bounds against 300 random assignments on a synthetic state; the winding number on the real STL at 150 face
centroids offset 1e-3..1e-7 (max distance from {0,1} 4.4e-16) and the `origin + idx*h` coordinate convention.

Findings and dispositions:

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | should-fix, required | integrity checks were bare asserts; INCOMPLETE unreachable; no crash rule | explicit `IntegrityError`, `main()` writes INCOMPLETE, plan "Failure handling" |
| 2 | should-fix, required | prototype outcome undisclosed; plateau claim tautological | plan states the prototype passed every predicate it exercised; wording changed to gap + amplitude <= TAU_REP |
| 3 | should-fix | parent smoothed-volume check not two-sided, parent band not bounded | `smooth_volume_bound`, two-sided parent range, scope statement |
| 4 | should-fix | controls population not asserted | exactly 19, skipped set exactly the two v16 files |
| 5 | should-fix | freeze not enforced at run time | `verify_freeze` (files, parameters, self-hash; records git HEAD and script sha) |
| 6-8 | note | SMOOTH_BOUND_MAX_REL rationale; outside-B signer assumption; label connectivity/empty band | plan text, claims-not-made, empty-band guard |
| 9 | should-fix | tests thin (n=1 enumeration, no negative controls) | 6 new tests; 11 pass |

## Round 2 — frozen state at commit `3aaa2f5` (freeze `2d733e6f82724e3156e2d2a5776656a0eb8ac72890c3dc88a4381ac4d4825a88`): PASS

All required changes resolved; 16 frozen hashes and the self-hash match; `verify_freeze` catches a tampered
parameter and a tampered file hash; 11 tests pass. The reviewer found one self-introduced defect before this round
(my own bug, fixed before review: float32 `TAU_REP` vs the JSON literal). Remaining non-blocking items:

1. `run()` reads the freeze from the output directory. Disposition: the output directory must be the evidence
   directory; the exact command is fixed in `prerun_approval.json` (no frozen file is changed).
2. "Both attempts recorded" needs the operator to save a first INCOMPLETE record before a re-execution (`main`
   overwrites). Disposition: recorded as an operating rule in `prerun_approval.json`.
3. Script comment at line 43 still says the certificate binds to the whole plateau; the plan is authoritative
   (gap + amplitude <= TAU_REP). Comment-only; left unchanged to keep the freeze.
4. A clean working tree is not required at run time; hashed files plus the recorded HEAD are the provenance.
5. Not checked by the reviewer: band size, actual plateau ratio, and P3-P5 outcomes on the real fields.

## Round 3 — Amendment 1, frozen state at commit `c56eca8` (freeze `8eabccd3dbe4b67e26852e9581f5b4f8696f4bac2147cc481ff9bdaa463cab1e`): PASS

Trigger: attempt 1 (freeze `2d733e6f…`) stopped INCOMPLETE in the preflight (SRCMAP-01 manifest check versus two living
documents) before any state, mesh or field was loaded; retained as `attempt1_*` files. The reviewer confirmed that the
diff `d475262..c56eca8` changes only the manifest logic, one comment, one test and the Amendment 1 text (parameters,
predicates, thresholds and method untouched; old freeze byte-identical to the attempt-1 freeze), that the manifest logic
cannot silently skip a changed non-living entry (real manifest: 130 entries, 128 verified, the two living documents
excluded, 0 mismatches), that the amendment honestly discloses the deviation from the plan's own re-execution rule and that
it adds no selection effect, that all 16 frozen hashes match and `verify_freeze` passes, and that 12 tests pass.
Remaining notes, none blocking: the plan's earlier "130-entry" wording at `prerun_plan.md:43` is superseded by
Amendment 1 (the post-run report cites the amendment; editing would force another freeze); the 125-versus-128 dry run
hashed identity files only and is not retained as a log; attempt 1 does not consume the one-run allowance.
