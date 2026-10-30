# v16 OpenFOAM reproduction, Jammy environment round 3

The exact first Kaggle CPU submission observed Ubuntu 22.04.5 Jammy amd64 and
failed the prior Noble environment lock before apt or any solver command. The
original kernel directory and Round 2 criteria remain unchanged. This separate
round binds official Jammy packages in the same OpenCFD v2512 `2512.0-2`
family; it preserves the archive fixture, all meshing/solver settings and every
numerical reproduction gate.

`runner.py` embeds the complete immutable criteria, package lock, metadata and
fresh case/fixture payload. Its isolated script-only self-check passes. The
old and new `case_template/Allrun` are byte-identical, so the four parent-tested
shell regressions also apply to this round. Run a local self-check with
`python3 runner.py --self-check`; this does not install OpenFOAM or step a solver.

Exact official repository index bytes and package records are retained under
`docs/evidence/xfid_jammy_apt_lock_inputs_2026_10_02/`. The actual installed
package files and hashes, OS, architecture and foamVersion must still be
captured during the fresh run. Index/contract checks alone are not environment
reproduction evidence.

Commit/push the parent source registration before submitting a new exact
private CPU kernel version. Download that exact version and run
`python3 verify_artifact.py ARTIFACT_DIR criteria.json openfoam_package_lock.json PARENT_REGISTRATION_MANIFEST`.
No new OpenFOAM shapes or scientific XFID comparison are allowed until this
gate passes and the composite Candidate C operator contract freezes. All
qualification flags remain false.
