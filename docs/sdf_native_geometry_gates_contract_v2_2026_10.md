# SDF-native geometry gate contract v2 (GEOM-02, #29)

Plan: [`geom02_plan_2026_10_14.md`](geom02_plan_2026_10_14.md) with Amendment 1 (A1-A8). Evidence class: solver-free contract and capability; research gates only.
v1 ([`sdf_native_geometry_gates_contract_v1_2026_10.md`](sdf_native_geometry_gates_contract_v1_2026_10.md), `geometry_gates.py`) is immutable and still defines every gate whose
text is not repeated here: the same 13 gate ids, `pass`/`fail`/`unmeasured`, verdict = AND, `None` or an invalid threshold = `unmeasured`, never a default. The bundle never modifies
a state; stored states keep `topology_policy_id = sdf_native_topology_policy_v1` and their `state_sha256`.

Code: `src/cfd_sdf/design/geometry_gates_v2.py` (`evaluate_geometry_gates_v2(state, *, parent_state, profile, policy, export_mesh)`). Registration:
`scripts/register_geom02_profile.py` writes the gate profile and the resolved research policy instance under `docs/evidence/geom02_v17_gates_2026_10_14/`
(content-addressed, `.sha256` sidecars, refuses to overwrite, `--check` re-derives). Canonical run: `scripts/geom02_canonical.py`. Tests: `tests/test_geometry_gates_v2.py`.

## Gates that differ from v1

| Gate | v2 decision (threshold source) |
| --- | --- |
| `sdf_distance_property` | median `abs(abs(grad phi) - 1)` over the interior narrow band <= 0.10 (profile; the value used as a hard gate in every LOWDIM registration). |
| `near_zero_gradient_band` | **zero-level gradient floor.** Interior nodes with a 6-neighbour of the other class (exact zero counts as fluid), central differences, `abs(grad phi) >= 0.5` (profile). Sign-change nodes on the array boundary make the gate `unmeasured` (reason `sign_change_nodes_on_array_boundary`) and are never evaluated with one-sided differences. The report carries the failing nodes' `abs(phi)`, a location split (exact-zero node / adjacent to an exact zero / other thin or cancelling) and the five worst nodes. v1's 0.05 m band bins are not carried. Thin features (about two cells or less) fail this floor by construction; that is the purpose (the shape-derivative normal velocity is ill-conditioned there). |
| `sdf_boundary_margin` | one cell from the array extent (profile; structural). |
| `domain_clearance` | cell-AABB clearance of the solid to the registered WaterLily flow box (`FLOW_ORIGIN_M`, `BASE_MAX_M` of `julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl`, path and sha256 pinned in the profile) >= 0.25 m (the `clearance.minimum_m` of the XFID Round 3 pre-registration, pinned). Not the SDF array extent. |
| `mask_preservation`, `component_connectivity`, `topology_change_classification` | `topology_policy_research.evaluate_research_transition` on the **stored** states with `feature_metrics=None`, `allowed_events=()` (OPT-01 topology-fixed), `birth_qualified=False`. Exactly three violations are removed **by name**, nothing else: `current_state_policy_hash_mismatch`, `proposed_state_policy_hash_mismatch` (stored legacy binding), `feature_measurements_missing` (widths and gap are gated by the bundle itself); the policy's own unresolved-limit names are skipped because the width/gap gates are `unmeasured` for them. Disconnected components are allowed, root connectivity is optional. Solid components only: cavities and tunnels are not judged. Empty fixed/forbidden/root masks are reported (`empty_masks`, `vacuous_empty_masks`); an all-empty mask gate is a vacuous pass, not a substantive one. The source ProblemSpec binding is absent (the v17 genesis binds none) and is reported, not inferred. |
| `min_feature_width` | v1 `2*EDT` ridge estimate (4x supersample) with the resolved instance limits `minimum_solid_width_m = minimum_void_width_m = 1.5h = 0.0375 m` (v1 guard h/4: pass >= 0.04375 m, fail < 0.03125 m). Measured on the solid's cell AABB padded by one cell. A void with no ridge there is `pass` labelled `not_applicable_no_enclosed_or_slot_void`. |
| `inter_component_gap` | v1 gap estimate with `minimum_gap_m = 2.5h = 0.0625 m` (v1 guard h: a one-cell gap fails, a 2-3 cell gap is `unmeasured`, 4 cells pass). One 26-neighbour cell component: `pass` labelled `not_applicable_single_component`. |
| `export_surface_integrity` | the state's own zero level, not the voxel proxy: `scripts/xfid45_round3_export.py` `extract` (scikit-image Lewiner, float64 trilinear refinement r=8), sub-cell components removed and counted (bounding-box diagonal < 0.025 m, `build_xfid45_stage_v_input_2026_10_04.remove_small_components`), `orient` by phi sidedness, then `topology`: watertight, winding consistent, edge-manifold, vertex-link-manifold, no duplicate/degenerate faces, positive signed volume, orientation established. The mesh volume against the sharp count volume is informational only (v1's 1e-6 rule fails by construction). The pipeline lives in the scripts layer; the bundle takes its result dict. |
| `surface_self_intersection` | `mesh_self_intersection`: cell-binned broad phase (bins of twice the largest triangle extent, 26-neighbourhood), P20 AABB test, vectorized exact rejections (non-shared vertices strictly on one side of the other plane; coplanar pairs separated by an edge line), and the **unchanged** P20 contact tests (`_triangle_intersection_contacts`, `_contacts_confined_to_shared_simplex`) for every remaining pair. The P20 triangle cap (12,000) does not apply. With P20's own tolerance (`1e-10` of the extent) the verdicts equal P20's on meshes P20 can evaluate (differential test). Two deliberate differences, both forced by the registered extractor's output and recorded with the artifact: the degenerate-triangle rule is a rounding-level collinearity test (P20's 1.3e-10 m^2 doubled-area floor trips on needle-thin Lewiner triangles created by the zero-tie epsilon), and the contact tolerance is the profile value `export.self_intersection_tolerance_rel` times the extent (P20's absolute 1e-10 tolerance makes its coplanar test report a phantom contact on two needle triangles that touch only at a shared vertex; a regression test pins this). |
| `volume_semantics` | P22-v2 integer hard count `N_phi <= 8272` on the registered v17 lattice (profile `max_solid_centers` and `lattice`; any other lattice is `unmeasured`). Representation-specific; not a physical volume. |

## Non-blind registration and claims

The profile and the resolved policy instance (`sdf_topology_policy_v2_research` with the three limits above, a new content-addressed policy per the #31 record) are registered
before the canonical run. Thresholds are **non-blind**: v16 and v17 values from the GEOM-01/SRCMAP-03a/LOWDIM records and the read-only plan-review measurements were known
(the observed minimum width was 2h; it was not used because that would be circular). The width and gap limits are **lattice representability limits (research)**, not physical or
manufacturing minima; their authority is the 2026-10-13 blanket delegation read as an interpretation (as #31 did). A threshold change after the canonical run is a new profile.
A canonical `fail` is an admissible, recorded outcome.

May say: every GEOM-01 gate id is measured on the v17 states against a registered research profile, and which passed or failed. May not say: manufacturing or physical feature
qualification, export certification at 0.5 mm, cavity/tunnel topology control, grid-independent downforce or FSAE qualification, or any shape-update permission. All six
qualification flags stay false.

## Environment

`scikit-image==0.25.2` (required by `extract`, absent before this work) was installed with

`uv pip install --python /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scikit-image==0.25.2`

which resolved to scikit-image 0.25.2 (plus imageio 2.38.1, lazy-loader 0.6, networkx 3.7, tifffile 2026.9.20); numpy 2.5.2 and scipy 1.18.1 were unchanged. The canonical
script requires that `extract` on the v17 baseline reproduces the saved XFID Round 3 baseline r=8 surface (array hash `e337541d...084be`, arrays identical to the saved
`surface.npz`) before any gate is evaluated.
