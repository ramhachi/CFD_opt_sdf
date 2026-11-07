# WP5 Amendment 1 validation

These artifacts describe development tooling, synthetic tests and the
invalidation of the first attempt's rendered kernels. No corrected E2
OpenFOAM smoke, production solve, experimental Cp digitization, freeze or
qualification was performed in this amendment. See [the report](../wp05_report.md).

- `validation.json`: exact final commands, completion/exit results and failure
  node sets. The base is the user-supplied Claude host observation at e3dcdf61;
  this amendment runs the result side only, excluding the specified Metal file.
- `test_logs.tar.gz`: final focused and full-suite stdout, focused JUnit XML
  and compileall log. The archive's `ARTIFACT_MANIFEST.json` binds every other
  member by bytes and SHA; the archive is read back after writing.
- `source_inventory.json`: actual HEAD/dirty state and amended script/test/
  schema hashes, environment versions, external review identities and routing
  preflight. It does not pretend the dirty tree is a committed/frozen source.
- `authority_read_receipt.json`: the full-file read receipt for the seven
  authority/research documents covered by the read-only worker.
- `frozen_inputs_unchanged.json`: 17 selected immutable sources, contracts,
  dependency manifest and pins checked byte-for-byte against e3dcdf61.
- `geometry_preflight.json`: the five available first-attempt WP4 inputs,
  raw SHAs, density metrics and new loader rejection reasons. All five are
  rejected. E3_sharp is missing from that local input set; no authoritative
  six-member study boundary-layer plan was invented.
- `render_invalidation.json`: working plan/wrapper metadata changed only to
  development/ready=false, with before/after SHAs. Embedded source payloads
  were not regenerated. Original raw execution copies and historical archive
  bytes are preserved; their embedded old ready flags are revoked by this
  receipt. They must not be executed or pushed.
- `synthetic_mesh_summary.json` and `synthetic_unit_meshes.tar.gz`: three
  final unit-test meshes/manifests (two-body sharp, two-body blunt, three-body
  med30), their input/mesh/plan SHAs and complete informational quality proxy.
  The tiny third synthetic nose has proxy failures; no checkMesh acceptance is
  asserted. The archive includes a member/hash manifest and was read back.
- `schema_validation.json`: JSON Schema Draft 2020-12 checks and seven
  synthetic instance checks with the existing temporary jsonschema package
  target. No dependency was installed or changed. Unknown observables reject;
  duplicate mesh cells preserve point diagnostics and block the ratio path.
- `run_forecast.json`: counts and planning arithmetic from `make_plan` only,
  without rendering kernels. Runtime figures remain assumptions; the global
  160 CPU h ledger is owner-managed, not enforced by independent case caps.
- `commit_files.txt`: exact amendment paths for Claude's host commit. Work
  directories and `publication.git` are not publication paths.
- `SHA256SUMS`: repository-relative hashes of these validation files, except
  the checksum file itself. It does not modify old evidence manifests.

Archive timestamps are zero, members are ordinary relative files and the
inventory is explicit. Extract into a new directory. The first delivery's
archives remain under `../wp05_validation/` as historical artifacts; their
old source/mesh records do not certify this amended implementation.
