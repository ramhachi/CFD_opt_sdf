# XFID-01 geometry input preflight (2026-10-03)

Status: **UNRESOLVED before solver measurement**. The required baseline zero-level
surface fails the repository's geometry integrity gates. Do not launch the #45
solver comparison or #46 FD-08 campaign from this input. Issue #45 remains open:
the required host-verified force-response sign/order verdict does not exist.

## Scope and authority

The run started from authoritative integration commit
`d0a7db68ac5c98424c14ac25f05a43fef4302228` (`codex/kaggle-batch-migration`),
which includes the completed #44 audit. The frozen Candidate C identity remains
`docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json`,
SHA-256 `516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`;
the intended production operator is the Candidate C moment blend with
`normal_floor=0.25`. No WaterLily force was evaluated in this preflight.

The independently host-verified Kaggle CPU v16 OpenCFD v2512 environment
reproduction remains the environment prerequisite. It was reused as a prior
PASS and was not rerun. Its reproduction criteria and package lock are not the
formal XFID criteria. No formal XFID criteria were registered, so this result
has no formal criteria SHA-256. The separate environment reproduction record
is [the #45 environment gate](45_xfid_openfoam_environment_gate.md).

## Bound geometry inputs

The canonical v17 state is the registered file SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`, state
SHA-256 `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`,
and Fortran-order `phi` SHA-256
`e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`. Grid
spacing is `h=0.025 m`; the registered primary shape amplitude is
`ε=0.005 m=0.2h`.

The existing `generate_directions` implementation was reused without changing
directions or epsilon. The exact Float32 direction hashes are:

| Direction | Float32 C-order SHA-256 |
| --- | --- |
| D0 interface offset | `8b5773b7d404cc21819078085eddeae437cad619472910fcac17430b2b6be3b5` |
| D1 filtered seed 11 | `4da3513780c3ba9b2ab91837911d46a2cab362e9a561eedb18468b424f81d4f5` |
| D2 filtered seed 2026 | `bb1eeaf0cdd43bc71085499c853f24eae6335e030851dfc0f9b581f4f5aa8fe8` |

Each exact perturbed `GridSDF` was saved as an NPZ snapshot and round-trip
checked against its recorded state and `phi` hashes. The snapshot manifest binds
to the geometry audit SHA-256
`a5fef9732e03b15f87931f70841b26453b6c96ccc5f7402c132b95491da6cb83` and has
SHA-256 `3e82a6672934d2863d10aafa319a39c728e58b36011fb7003957d5e0825e4955`.
Its sidecar SHA-256 is
`9108b8cc96acd0c4a1b2565420f798d8c59a4881354467e6ccb915ec81774550`; it covers
all six NPZ snapshots and the snapshot manifest.

| Case | Signed volume (m³) | Watertight / winding | Non-manifold edges | Duplicate faces | Min Stage V clearance (m) | STL SHA-256 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| baseline | -0.13385839349594708 | no / no | 712 | 4 | 0.6500000000 | `0c8f78c1befbf3612fe7cb5a1e42b89c4c836850069688d5ea4c883f80bcc32b` |
| D0 −ε | -0.1453838149893201 | yes / yes | 0 | 0 | 0.6458333373 | `88ab3aed96d97ab188b37368f13ab50e89758ec9ea3ca42556151e131fc6e11d` |
| D0 +ε | -0.11083000988206641 | yes / yes | 0 | 0 | 0.6541666627 | `a2698a28049ce1532e03297155cffb387674e0cd2f0e513e248e878b7dbefaa1` |
| D1 −ε | -0.12776484554921838 | yes / yes | 0 | 0 | 0.6458333373 | `86d2a09ac6deec08b0aa6f656531a93c510f0bfe1a4f45093a7978c0e2da8f26` |
| D1 +ε | -0.12847583764507173 | yes / yes | 0 | 0 | 0.6463969886 | `d0a7911785d7bc8177e9f8a944d0cb65d688c6f448ba4af285af49ebc87c5eeb` |
| D2 −ε | -0.1282466443865735 | yes / yes | 0 | 0 | 0.6465995252 | `ed0d2eab234a02f3d38c0e6fb7488f960b367a089d9171367955400f6f7cd91f` |
| D2 +ε | -0.1280951726051519 | yes / yes | 0 | 0 | 0.6464202940 | `debe4be598dc3a303e7e9d8f9523aa2dd8cb06d9e4da2187966e72ba1c0e95ea` |

The baseline and all six candidates are within the Stage V domain and exceed its
0.25 m minimum clearance. The baseline fails watertightness, winding, manifold
edge incidence, duplicate-face, and positive-volume gates. All six perturbed
surfaces fail the repository positive-volume gate: their signed volumes are
negative despite watertight and winding-consistent topology. The repository
geometry checks require positive signed volume; see
`src/cfd_sdf/extraction_qualification.py` and
`src/cfd_sdf/design/geometry_gates.py`.

## Reproduction and evidence

Geometry was exported with the existing
`cfd_sdf.export_vtk.export_zero_surface` (PyVista zero contour), then serialized
as STL with `trimesh` and `process=False`. No smoothing, reorientation, cleanup,
manual repair, volume correction, clipping, or reinitialization was applied.
Coincident STL vertices were merged only in memory to measure edge incidence;
retained PLY/STL bytes were not changed.

Preflight command (run from this repository worktree):

```bash
PYTHONPATH=src /Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/.venv/bin/python \
  scripts/audit_xfid45_geometry_preflight_2026_10_03.py \
  --state /Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz \
  --output docs/evidence/xfid01_geometry_preflight_2026_10_03
```

The exact perturbed states were subsequently materialized and hash-checked with:

```bash
PYTHONPATH=src /Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/.venv/bin/python \
  scripts/export_xfid45_perturbed_state_snapshots_2026_10_03.py \
  --evidence docs/evidence/xfid01_geometry_preflight_2026_10_03
```

Local geometry-preflight runtime: Python `3.12.13`, NumPy `2.5.2`, PyVista
`0.48.4`, VTK `9.6.2`, and trimesh `5.1.0`. Backend was local CPU geometry
processing only. WaterLily, OpenFOAM, mesh generation, and force integration
were not started. No force responses, baseline repeats, solver-specific floors,
or floor inputs were measured. No separate solver host verifier applies to this
geometry-only evidence.

Software validation passed `python -m py_compile` for both new scripts,
`.venv/bin/python -m compileall src tests`, and 58 focused tests across the
direction generator, geometry gates, extraction qualification, handoff, and
geometry preflight. The full repository suite reported 37 failed, 1339 passed,
and 5 skipped; its sorted failure IDs exactly match the pinned 37-ID baseline
(zero new and zero resolved IDs). The baseline file SHA-256 is
`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`; the
current full-suite log SHA-256 is
`d1020d6a3552176650c8df146bfa71d75c888bb25b6587f1e6bf0b6ede063086`, and the
current sorted ID file has the same SHA-256 as the baseline. The full output,
ID list, and validation record are in the `validation/` subdirectory; its
`SHA256SUMS` sidecar SHA-256 is
`440966bfdbdb36f15d9d12d2b8114abc38f2ae289472b896dffbceaa38525efe`.

Evidence files:

- [`geometry_audit.json`](../evidence/xfid01_geometry_preflight_2026_10_03/geometry_audit.json), SHA-256 `a5fef9732e03b15f87931f70841b26453b6c96ccc5f7402c132b95491da6cb83`
- [`SHA256SUMS`](../evidence/xfid01_geometry_preflight_2026_10_03/SHA256SUMS), SHA-256 `3cc2be3f11742ce2720e1983aa3060c42e99148590f9ac5b0e44f44bd39f5123`
- [`state_snapshots`](../evidence/xfid01_geometry_preflight_2026_10_03/state_snapshots/), with its own snapshot manifest and checksum sidecar
- [`validation`](../evidence/xfid01_geometry_preflight_2026_10_03/validation/), full-suite log and exact baseline failure-ID comparison
- Preflight script SHA-256 `7865f6be1ede7d919ee77117f7d5c6a120b14475930a7c93535e7671323d5b00`
- Snapshot exporter SHA-256 `5fac5aa3becea361aff859027d8ff1c629e3a9c5a53918acc6f8a90aa236fb49`

## Decision and limits

This is a solver-free input-geometry blocker and a premeasurement **UNRESOLVED**
branch result, not an XFID force-sign/order comparison and not a `DISAGREE`
verdict. Formal XFID criteria were not registered, response floors were not
selected or measured, and no candidate force response was observed. The issue
remains open because its Done condition requires a host-verified sign/order
verdict.

Per the user-directed dependency order, stop before #46's FD-08 solver campaign.
Do not relax topology/volume gates, flip normals, repair surfaces, replace a
direction, or change epsilon under this result. Any follow-up must be a separately
registered deterministic surface-export/input round that resolves the baseline
and all required perturbed-geometry gates while preserving exact GridSDF-to-STL
lineage. All qualification flags remain false: `fd_oracle`, `field_gradient`,
`reverse`, `optimizer`, `topology`, and `shape_update_allowed`.
