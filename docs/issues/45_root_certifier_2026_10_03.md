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

**Not started.** The preregistration and its pre-target amendment bind source
hashes, runtime, the fixed synthetic suite and seed,
root-count/position/ambiguity rules, and 201 saved input/artifact hashes. After
the amendment and validation evidence are committed and pushed, verify that
remote and local feature-branch HEADs are identical, then replay all registered
`r={1,2,4,8}` saved surfaces and correspondence samples. No target result has
informed or changed the criteria.

Qualification flags remain false: solver qualification, FD oracle, field
gradient, reverse mode, optimizer, topology, and shape update are all disabled.
WaterLily, OpenFOAM, Kaggle, formal XFID, and #46 FD-08 are outside this work.

After the target replay, this note and [the phase plan](../phase_plan.md) will
record the evidence-scoped result. The #29 cross-reference is limited to the
actual zero-level / Stage V export evidence.
