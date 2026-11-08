# WP5 Amendment 2 validation records (2026-11-07)

Base HEAD: `45917d8c`. Evidence is development code/contract validation only.
No OpenFOAM, physical E2 smoke, Kaggle, production solve, freeze, commit or push.

**N2 remains BLOCKED.** The prescribed vertex-order/Halton inputs are indexed
and eight mesh hashes differ, but raw same-index Gmsh output is not repeatable
on the measured synthetic local med30 case. The strict assertion is retained.
No coordinate post-processing or candidate mesh options remain in final code.
A single pass is not used to override retained counterexamples.

## Final implementation and tests

- `source_inventory.json`: final implementation/test/schema/fixture hashes.
- `frozen_inputs_unchanged.json`: 19 protected files compared byte-for-byte
  against e3dcdf61; all unchanged.
- `authority_read_receipt.json`: required document identities and read coverage,
  including read-only external registration/reviews, plus actual worker routing.
- `focused.xml`, `focused_execution.json`, `focused.log.gz`: final focused run.
  The raw `.log` is an ignored working copy; `.gz` preserves exactly its bytes.
- `full.xml`, `full_execution.json`, `full.log.gz`: final complete result-side
  command, `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`.
- `compileall.log.gz`: `compileall src tests` final execution output, exit 0.
- `validation.json`: final counts, failed/error node sets and base comparison.
- `final_workspace_checks.json`: final source/protected-file hash readback,
  compileall, whitespace and branch/HEAD checks; no Git mutations.
- `commit_files.txt`, `SHA256SUMS`: exact intended handoff files and artifact
  hashes; Claude stages/commits/pushes on the host.

## Mesh mechanism and its counterevidence

- `mesh_realisations.json`: final raw-output focused measurement; receipt
  written before strict assertions. Contains eight indices, physical feature
  remapping, Halton offsets, mesh SHAs, cells/quality, source identities and
  the actual same-index repeat result. This final focused repeat FAILED.
- `mesh_realisations_full.json`: independent final full-suite measurement,
  also written before assertions. Keep both outcomes; do not select a pass.
- `mesh_repeat_artifacts.tar.gz`, `mesh_repeat_artifacts.json`: exact focused
  input JSON and nine manifests, plus the two raw meshes from the failed
  index-3 pair; per-file hashes and bytes are recorded separately. This retains
  the concrete 31,798/31,796-cell counterexample after pytest cleanup.
- `historical_geometry_fixture.json`: provenance of the intentionally invalid
  branch-local WP4 attempt-2 gzip input fixture. No external code is executed.
- `gmsh_source_review.json`: independent primary-source trace and inference
  boundary, official Gmsh 4.15.2 archive hash. It identifies a pointer-ordered
  BL node creation/internal-number path, not an instrumented causal proof.
- `mesh_repeat_diagnostics.json`: failed raw repeat despite Reproducible=1,
  with few-ULP coordinate differences and equal quality.
- `mesh_repeat_diagnostics_13digit_focused.json`: failed 13-digit trial;
  includes a nearest-node/ID-permutation explanation and its limitations.
- `mesh_realisations_13digits_single_pass.json`: historical single passing
  serialization trial. REVOKED as acceptance evidence by the later failure.
- `failed_focused_13digits.*.gz`, `serialization13_validation_attempt.json`:
  274 passed / 1 failed and the source identities for that withdrawn trial.
- `interrupted_full_13digits.log.gz`: parent stopped obsolete run, exit 130;
  never counted as completed full-suite or baseline-equivalence evidence.
- `mesh_option_probes.json`, `mesh_option_control_probes.json`,
  `mesh_final_option_pair_probes.json`: isolated candidate controls. An initial
  four-pass repositioning control later failed; the paired relocation/topology
  control gave four raw hashes in eight same-index-3 processes. No candidate
  option was adopted. These are not formal T2-0 family qualification evidence.

Proxy metrics are informational. No checkMesh acceptance follows from any of
these local synthetic meshes. Gmsh output/allocator behaviour on Kaggle is
unverified, as are corrected physical E2 geometries and force convergence.

## Hermetic schema/reference validation

- `synthetic_measurements.json.gz`, `synthetic_rans_results.json.gz`: branch-only
  synthetic fixtures, not experimental forces. Their temporary raw input
  paths were provenance during validation, not a study freeze inventory.
- `schema_validation.json`: existing host Python 3.9/jsonschema 4.25.1 validated
  both Draft2020-12 schemas and synthetic outputs, rejected observable mismatch,
  missing height and legacy COMPLETE success label. No project dependency added.

No fixture or test imports another worktree's analyzer. CSVs in the tests are
synthetic; no experimental figure was digitized. Actual reference CSVs remain
a user input. WP4 schema/analyzer synchronization and any N2 contract/Gmsh
implementation decision belong to the owner before integration/freeze.
