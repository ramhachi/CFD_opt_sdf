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

Pre-target checks are complete: focused suite `16 passed`; compileall, Ruff,
formatting, staged and unstaged diff checks passed. The full suite reported
`36 failed, 1383 passed, 9 skipped`; its failure-ID set exactly matches the
frozen Round 3/current comparison, and it adds zero IDs relative to the pinned
baseline. The two ignored worktree fixtures needed for reproducible full-suite
checks were copied from the original checkout and hash recorded. An earlier
run without those fixtures is preserved separately as an environment-only
attempt in the pre-target validation evidence.

## Target replay status

**Not started.** The preregistration now binds source hashes, runtime, the
fixed synthetic suite and seed, root-count/position/ambiguity rules, and 201
saved input/artifact hashes. The next step is to commit and push it, verify that
remote and local feature-branch HEADs are identical, then replay all registered
`r={1,2,4,8}` saved surfaces and correspondence samples. No target result has
informed or changed the criteria.

Qualification flags remain false: solver qualification, FD oracle, field
gradient, reverse mode, optimizer, topology, and shape update are all disabled.
WaterLily, OpenFOAM, Kaggle, formal XFID, and #46 FD-08 are outside this work.

After the target replay, this note and [the phase plan](../phase_plan.md) will
record the evidence-scoped result. The #29 cross-reference is limited to the
actual zero-level / Stage V export evidence.
