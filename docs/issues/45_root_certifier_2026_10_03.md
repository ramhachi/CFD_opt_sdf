# #45 XFID45-CERT-01 trilinear root certifier

## Scope and authority

This is a solver-free successor diagnostic for the incomplete normal-ray root
enumeration found in immutable Round 3 evidence. It introduces the new evidence
identity `XFID45-CERT-01`; it does not revise the Round 3 evaluator, verifier,
surfaces, exports, or qualification judgment.

The feature branch starts from `codex/kaggle-batch-migration` at
`3f9322dc0fa0f2847a3204427b81a665932b83b8`. The preregistration will be
committed and pushed before any target replay. Integration is planned as a
reviewed `--no-ff` merge into that authoritative branch.

The fixed Round 3 regression is `D0_interface_offset_minus`, `r=4`, saved
double sample 691. The frozen parent selected approximately `-0.0499999531 m`
after excluding the nearer target root near `+0.00416667075 m`; the saved mesh
intersection is near `+0.00416669846 m`. The Round 3 omission diagnostic
reports the resulting roughly 54 mm discrepancy, while the corresponding
mesh-to-source-root difference is about 33.8 nm. This is a known regression
fixture, not held-out evidence.

## Frozen successor contract

Within each original grid cell, a straight ray restricts the registered
trilinear field to a polynomial of degree at most three. The primary solver
forms that polynomial from the cell coefficients, partitions at derivative
critical points, and isolates crossings with a position bracket. The
independent implementation reconstructs the polynomial from four separately
sampled field values and uses exact-rational Sturm counts and isolation. It
imports neither the primary implementation nor Round 3 helpers.

Both implementations enumerate every cellwise root before nearest-root
selection. Root existence and position accuracy are handled separately; no
absolute residual cutoff drops a candidate. Exact shared cell-plane endpoint
duplicates are merged. Distinct roots closer than the registered positional
tolerance remain present and make the root set unresolved. Zero intervals,
incomplete sets, tangencies, and equidistant nearest roots fail closed.

The preregistered root-position agreement tolerance is
`16384*eps(Float64)*max(h, local interval length, |t_left|, |t_right|, |t_root|)`.
The trilinear field is evaluated piecewise over the full registered `+/-2h`
ray. The unchanged absolute-geometry limit is 0.5 mm. Saved surfaces, float32
STLs, and baseline samples will be re-used without extraction.

## Pre-target qualification

The fixed synthetic suite covers constant through cubic degree, explicit
negative-zero and regular endpoint roots, simple and multiple roots, cell
boundaries, near-endpoint and close roots, dynamic range, small cubic terms,
zero and near-zero nodes, a three-root trilinear cell ray, a 512-case seeded
property family (`451003`), and the fixed Round 3 sample 691 regression. The
primary and independent methods must agree on root counts, positions,
nearest-root identity, and ambiguity status.

The original preregistration was committed and pushed as `c9cecbc`, but its
first runner invocation failed closed before reading any saved target input or
surface: the runner referenced the absent `target_input_inventory` key instead
of the registered `target_replay_inventory.files` schema. The registered
preregistration and Git branch metadata were read; no target output directory
was created. This attempt is preserved at
`docs/evidence/xfid45_root_certifier_2026_10_03/runner_preflight_failure.json`.

Pre-target amendment `XFID45-CERT-01-AMEND-01` binds the corrected inventory
paths and a fix to the all-root-position agreement accumulator. The latter
preserves the registered requirement to compare every root position even when
the nearest roots agree; it does not change the criteria or either certifier.
The amendment binds only the replay runner and regression-test hashes and
records the unchanged contract subtrees. Its SHA-256 is
`1f7d4c713c591a08e9638e8cd68aa2405fffa7de6fc50a73ed8b3812f052d464`.

Final pre-target validation passed the 16 registered synthetic/property and
known-regression cases plus two runner regression checks (`18 passed`).
Compileall, Ruff, formatting and diff checks passed. Full pytest reported
`36 failed, 1385 passed, 9 skipped`; its failure-ID set exactly matches the
frozen Round 3/current set and adds zero IDs against the pinned baseline. One
pinned baseline ID remains absent. The prior pre-final-review full run is
preserved as superseded validation. The two ignored worktree fixtures needed
for reproducible full-suite checks were copied from the original checkout and
their hashes are recorded. See
`docs/evidence/xfid45_root_certifier_2026_10_03/pre_target_amendment_validation/`
for commands, logs, failure-ID comparison and hashes.

## Target replay status

Target replay attempt 01 passed the branch, amendment and 201-file identity
preflight. It recomputed the ten `r=1` double/float32 surface geometry cases,
then enumerated all 1,024 saved `r=1` `D0_interface_offset_minus` double
correspondence samples before failing in output assembly with `KeyError: 'baseline'`.
No result JSON or qualification summary was written. The valid partial trace,
console output and structured failure record are preserved under
`docs/evidence/xfid45_root_certifier_2026_10_03/target/r1_2_4_8/`.

Post-attempt amendment `XFID45-CERT-01-AMEND-02` fixes only replay output
assembly: case-key the current-r surface prerequisite map, represent
non-finite bound comparisons without generating NaN, and write the retry under
`target/attempt02/`. It is chained to amendment 01 and binds the failed attempt
record. Primary and independent certifier hashes, target inventory, and all
criteria remain unchanged. Amendment SHA-256:
`2a4fca403caada581b5bdeb08f963c89cef469af4978697d60ff14a1c6776a48`.

Attempt 02 completed at the registered feature-branch HEAD `c18989e` with exit
code 0 in 3216.98 s. All 201 preregistered input files and the effective source
hashes match; the complete Round 3 `r={1,2,4,8}` saved-surface and fixed-sample
inventory was replayed without extraction. Attempt 01 remains preserved as an
incomplete software failure, not a CERT-01 result. Its runner correction is
bound by amendment 02; no numerical source or criterion changed after target
evaluation.

The final pre-target validation at `c18989e` passed 21 focused tests, including
the 16 registered synthetic/property/regression cases and five runner checks;
compileall, Ruff, formatting and diff checks passed. Full pytest reported
`36 failed, 1388 passed, 9 skipped`. Its failure-ID set matches the frozen
Round 3/current set exactly, adds zero IDs against the pinned baseline, and
omits one pinned baseline ID. Commands, logs, hashes and comparison are in
`docs/evidence/xfid45_root_certifier_2026_10_03/attempt02_validation/`.

The 49,152-line compressed root trace contains 98,304 baseline/target root-set
comparisons. A fresh post-run aggregation from that trace exactly reproduces
the independent result's global counters, but primary and independent root-set
agreement **fails**: 5,670 status mismatches, 5,214 root-count mismatches, and
234 paired-root position mismatches. Root-kind and zero-interval mismatch
counts are zero. The maximum paired-root position delta is `1.4335e-8 m`
(14.3 nm), versus the registered maximum tolerance `3.6380e-13 m` (0.364 pm).
The maximum nearest-position delta is `1.0606e-13 m`, but that does not cancel
the status, count, and root-position failures. Representative trace rows show
roundoff-sensitive endpoint roots and candidates rejected by the primary
roundoff enclosure while the independent Sturm implementation reports a
complete root set. CERT-01 is therefore **not qualified on target data**; this
is Case C and the certifier work stops without tuning thresholds.

On the fixed regression sample `r=4`, `D0_interface_offset_minus`, double
sample 691, both implementations enumerate the near target root at
`+0.004166670752 m` and choose it as the unique nearest root; they also agree
on the baseline roots within the registered tolerance. The saved mesh/source
displacement diagnostic remains about `33.8 nm`. The old far-root selection at
`-0.0499999531 m` and its roughly `54 mm` frozen error are not reproduced on
this sample. This closes that local regression only; it does not override the
full-target agreement failure.

Under the unchanged 0.5 mm absolute-geometry contract, counting all ten saved
cases in each storage:

- `r=4`: double and float32 each have 3 PASS, 0 FAIL, and 7 UNRESOLVED.
- `r=8`: double and float32 each have 4 PASS, 0 FAIL, and 6 UNRESOLVED.

The maximum certified lower bounds are `0.3784 mm` at `r=4` and `0.0974 mm`
at `r=8`, so these results prove no above-limit case. Three heldouts plus
`r=8` D0-minus pass absolute geometry; the remaining upper-bound evidence is
insufficient. Including the frozen non-geometry gates, the combined surface
status is `3 PASS / 2 FAIL / 5 UNRESOLVED` at `r=4` and `4 PASS / 3 FAIL /
3 UNRESOLVED` at `r=8`. The combined FAILs retain both orientation and
positive-total-volume gate failures: `D1_filtered_seed11_minus` and
`D2_filtered_seed2026_plus` at `r=4`, and those two plus
`D2_filtered_seed2026_minus` at `r=8`. For these cases both storage forms have
`orientation=FAIL` and `positive_total_volume=false`; the other listed legacy
non-geometry gates pass.

No perturbation fidelity pair is qualified. All 12 case/storage pairs at each
of `r=4` and `r=8` fail the registered surface prerequisite; the baseline
surface is not certified, and root-set agreement also fails. During review, the
full trace exposed that each fidelity pair's
`primary_independent_root_agreement` counters in `primary_result.json` are
cumulative snapshots, not pair-local values. The derived
`root_set_agreement_by_group.json` recomputes all 48 groups from the raw trace;
its global counters match `independent_result.json` exactly. This output
assembly limitation is retained in the audit record and no target results were
rewritten.

See
`docs/evidence/xfid45_root_certifier_2026_10_03/target/attempt02/r1_2_4_8/`
for the untouched primary, independent and Round 3 comparison outputs, complete
gzip trace, console output, post-replay validation, trace-derived group table,
and expanded checksum manifest. Validation files are in
`docs/evidence/xfid45_root_certifier_2026_10_03/attempt02_validation/`.

Qualification flags remain false. #45 stays OPEN/UNRESOLVED; formal XFID must
not restart from this evidence. #46 remains BLOCKED. No solver, Kaggle,
OpenFOAM, production exporter, or criteria changes were made. The #29
cross-reference is restricted to the actual zero-level / Stage V export
measurement; it does not close GEOM-01 overall.

Qualification flags remain false: solver qualification, FD oracle, field
gradient, reverse mode, optimizer, topology, and shape update are all disabled.
WaterLily, OpenFOAM, Kaggle, formal XFID, and #46 FD-08 are outside this work.

The phase-plan entry records the evidence-scoped result. The #29
cross-reference is limited to the actual zero-level / Stage V export evidence.
