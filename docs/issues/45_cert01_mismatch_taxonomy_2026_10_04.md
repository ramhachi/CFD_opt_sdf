# #45 CERT-01 mismatch taxonomy (post-hoc, solver-free)

Evidence class: `solver_free_post_hoc_trace_taxonomy_unregistered`.

This is a descriptive reading of the already-frozen CERT-01 attempt 02 trace
(`docs/evidence/xfid45_root_certifier_2026_10_03/target/attempt02/r1_2_4_8/correspondence_roots.jsonl.gz`,
49,152 rows, 98,304 baseline/target root-set comparisons). It was written
after the target result was known, sets no threshold, changes no gate and
qualifies nothing. CERT-01 stays FAIL (Case C). #45 stays OPEN/UNRESOLVED,
#46 stays BLOCKED, all qualification flags stay false.

Reproduce: `python3 scripts/diagnose_xfid45_cert01_mismatch_taxonomy_2026_10_04.py`
(reads only the trace; no certifier import). Output:
`docs/evidence/xfid45_cert01_mismatch_taxonomy_2026_10_04/taxonomy.json`
(records the trace SHA-256).

## Result

5,796 of 98,304 comparisons disagree (the registered 5,670 status mismatches
plus 126 both-UNRESOLVED rows with count/position differences). Exclusive
classes, in rule order:

| Class | Count | What the trace shows |
| --- | ---: | --- |
| A | 4,398 | Sturm has one extra root at `\|t\|≈4.55e-14 m` (root at the sample point itself). Primary returns UNRESOLVED (`endpoint_value_within_roundoff_envelope` + `monotonic_interval_endpoint_sign_unresolved`). **All baseline side.** |
| B | 144 | As A, but the extra root is a real other crossing at `\|t\|` 2.3–29 mm that sits on a cell endpoint. Baseline side, r=1/2/4. |
| C | 672 | Primary COMPLETE with one root; Sturm UNRESOLVED (`distinct_roots_not_separable_at_registered_precision`) with two roots 4.55e-14 to 9.1e-14 m apart. Baseline side. |
| D | 564 | Same root set, positions within tolerance; primary UNRESOLVED for `root_position_exceeds_roundoff_enclosure`. 90 target side, 474 baseline side. |
| F | 18 | 12 endpoint-envelope without extra root, 6 `reduced_degree_root_within_discarded_term_envelope`. Baseline side. |

By side: **baseline 5,706, target 90**. Every target-side disagreement is
class D (primary UNRESOLVED, Sturm COMPLETE with the same unique nearest root);
there is no target-side count or extra-root disagreement. In every class-A/B
row the extra root is the nearest root on the baseline side.

Registered position statistics are consistent with this: nearest-root position
delta is at most 1.06e-13 m (inside the 3.64e-13 m tolerance) in every r group,
and `nearest_status_mismatch == nearest_identity_mismatch` in every group, i.e.
the nearest-root disagreement is always one certifier declining to decide, never
the two certifiers picking different roots.

## Reading (hypotheses for a later preregistered round, not decisions)

- A and C (5,070 of 5,796) concentrate on the baseline side, where the nearest
  root is the sample point's own surface crossing at `t≈0`. The disagreement
  there is how a root at an interval/cell endpoint is owned or enclosed, not a
  difference in where the surface is.
- The task-relevant target-side search has no extra or missing roots; its 90
  disagreements are primary-side conservatism only.
- In A and C the roots in question lie within about one ulp of cell-plane
  arithmetic of each other or of the sample point, so no position tolerance
  separates them; an ownership rule for shared endpoints is the candidate
  lever. The Sturm count already returns COMPLETE for A, B and D.
- Not established: whether class C is a duplicate across two adjacent cells or
  a genuinely double root, and whether any class-B root changes a nearest-root
  choice at the target side. Both need a targeted check before contract text.

## Not claimed

No tolerance, ownership rule or acceptance criterion is chosen here. Equivalence
criteria for CERT-02 must be preregistered before any fresh replay, and must not
be tuned to these counts. Absolute geometry and orientation (small components
D1−/D2±) are unaffected by this note.
