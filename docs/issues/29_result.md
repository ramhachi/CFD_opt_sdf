# #29 GEOM-01 solver-free gate result (2026-10-02)

## Evidence

The implementation and measurement contract were committed and pushed before
the canonical diagnostic ran: commit `847dab9` on
`feat/issue-29-geometry-gate-completion`. The immutable preregistration is
[`sdf_native_geometry_gates_v16_prereg_2026_10.json`](../evidence/sdf_native_geometry_gates_v16_prereg_2026_10.json),
SHA-256 `3f0d3d87f495495a6e236152032f8e75c56d5dec528902b89dfc79eaa7b6b76b`.
The source-bound contract is
[`sdf_native_geometry_gates_contract_v1_2026_10.md`](../sdf_native_geometry_gates_contract_v1_2026_10.md),
SHA-256 `60ec42669c66868715e12cf7c2b359281ec57722b897763986a30c0f559290d1`.

The run command was:

```text
PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scripts/sdf_native_geometry_gates_v16_2026_10.py
```

It wrote
[`sdf_native_geometry_gates_v16_2026_10.json`](../evidence/sdf_native_geometry_gates_v16_2026_10.json),
SHA-256 `116073b8de63b9da830af0257974ff195267873d50b8734424684652abe0b776`.
The state archive was copied byte-for-byte from the #28 worktree and verified
as SHA-256 `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`;
its embedded state digest is
`44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`. The
genesis manifest SHA-256 is
`3c8e241681c80962a7fd62f1926e382d473ec8e9f3e6b9140bea9600d41cf670`.

Evidence class: solver-free geometry contract/capability diagnostic. No CFD
solver started. The bundle reports 3 gates as pass, 0 as fail, and 10 as
unmeasured; its aggregate verdict is therefore `pass=false`. The passing gates
are finite/canonical structure, structural SDF-array boundary margin, and the
inherited sharp `V_phi` volume limit. The 0.05 m low-gradient band contains
2,659 interior nodes, of which 113 have gradient norm below `1e-6`; those bins
are descriptive only and the registered acceptance floor is absent. The
voxel-cell-union surface proxy is watertight; node/cell component counts are
1/1, it has 2,588 triangles and no non-manifold or duplicate faces, and its
volume is `0.12612499964050936 m^3` against proxy occupancy volume
`0.12612500000000004 m^3` (1,009 occupied cell centers). This proxy does not qualify the canonical GridSDF
zero-level or downstream Stage V/STL export; both actual-export gates remain
unmeasured.

The recorded sampled minimum solid and void widths are each `0.05 m`, but no
physical width limits are registered; the values are estimates, not guaranteed
continuous-geometry bounds. The physical gap, clearance limit, eikonal
tolerance, canonical mask/root binding, disconnected-component policy, and
birth/split/merge/deletion permissions remain unmeasured. The one-cell array
margin is a structural grid check only.

## Validation

The focused GEOM-01 suite passed: 6 tests. The full validation commands were:

```text
PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests
PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q
git diff --check
```

Full pytest reported 36 failed, 1,251 passed, 5 skipped in 217.59 seconds.
The failure-ID set has SHA-256
`d3b0199975fd49498ca74bca2d039e27774aa153a0b326131ab544c1b27a78f0` and has
no IDs beyond the integration baseline's 37 registered failure IDs (baseline
file SHA-256
`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`). One
baseline ID was absent in this run:
`tests/test_canonical_objective.py::test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`.
That change is outside #29 and is not attributed to this implementation. The
comparison is also stored in
[`sdf_native_geometry_gates_pytest_validation_2026_10.json`](../evidence/sdf_native_geometry_gates_pytest_validation_2026_10.json),
SHA-256 `81f604dd53a2bb143006d009af7a91b06a410d2e65b9ca9331f24d9ad5296b68`.
The full log is available in the worktree at
`work/issue_29/pytest-full-postfix.log`, SHA-256
`08edea190da9437b33b3daa1e709d15f8f7552b76887161968031fa10a9796ce`.
Before the final full run, two ignored fixtures were restored byte-for-byte
from sibling worktrees and hash-checked: v17 SDF state
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31` and
`work/pq0_2_smoke/project_downforce_volume.yaml`
`90314ab78073330a784939b3fe03c24319d217f564d3ebad4dea9a29c82d75fe`.
The previously new v17 fixture failure then passed in isolation.

The required qualification flags remain false: `shape_update_allowed`,
`fd_oracle`, `field_gradient`, `reverse`, `optimizer`, and `topology`. This
result does not close canonical geometry qualification or authorize shape
updates; it supplies a reproducible complete gate report and analytic
fixture-only behavior tests for follow-on policy decisions.

## Parent portable-fixture maintenance

The parent integration focused suite exposed a new missing-fixture failure: the newly added canonical-policy test loaded an ignored worktree-local NPZ. The test now loads the already committed canonical v16 input archive from `docs/evidence/reinitialization_parent_review_2026_10_02/raw_round3/canonical_v16_input.npz`, independently checked to be byte-identical (SHA-256 `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`). Geometry implementation, preregistration and measured result are unchanged. Round1 retains its original test identity at measurement source commit `847dab9`; reproducing that immutable round requires its original source checkout. This test-only maintenance does not retroactively replace a registered source hash or produce a new geometry verdict.

Parent maintenance validation: focused 6 passed; compileall passed; full pytest 36 failed, 1292 passed, 5 skipped. Exact-ID comparison with baseline has 0 new failures and one absent baseline failure due to already restored ignored ProblemSpec fixture. Compressed raw logs and hash audit are retained in `docs/evidence/geometry_portable_fixture_parent_validation_2026_10_02/`. No fresh canonical geometry run was made.

## #45 actual zero-level / Stage V STL export cross-reference (2026-10-03)

The formerly unmeasured actual GridSDF zero-level / Stage V STL export component
was evaluated in the solver-free, preregistered
[`#45 surface export round`](45_surface_export_qualification_2026_10_03.md).
The exact-coordinate canonicalization candidate failed: it left 12 baseline
non-manifold edges and an ambiguous face, while local-SDF facewise orientation
created winding conflicts on D1/D2. D0 ±ε passed, but the required all-seven
gate did not. The production exporter remains unqualified and #29 remains open.
This cross-reference covers only GEOM-01 actual export integrity; the other #29
close conditions remain outstanding.
