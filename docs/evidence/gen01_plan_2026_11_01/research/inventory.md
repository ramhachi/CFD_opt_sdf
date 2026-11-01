# Implementation inventory: SDF-based aerodynamic optimizer repo (read-only)

(sonnet Explore agent, 2026-11-01, verbatim; line numbers from direct reads, "~" means approximate)

## 0. Bottom line for the planner

- Everything solver-side is a research harness, built around one parent (v18 analytic plate), one lattice and one flow domain. All qualification flags are false and `shape_update_allowed=false`.
- No gradient-based optimizer loop works on the SDF line. Every derivative route on the WaterLily SDF solver is blocked. The only working proposer is a quadratic response surface over 3 analytic modes (SCREEN-01).
- No adjoint RANS on body-fitted meshes has ever worked. The 3D `adjointOptimisationFoam` attempt (Stage S Work F) failed derivative qualification. The 2D attempt (T2-0b) died with SIGFPE.
- Body-fitted OpenFOAM runs are laminar only: Re_L 80 steady `simpleFoam` on a 0.2 m snappyHexMesh background at 3 mesh levels. Turbulent RANS (SA, SST, T2-0) exists only for a 2D wing section on gmsh meshes, no SDF-to-mesh interface.
- Reusable: SDF state container and hashing; geometry gate framework; STL export; local Docker OpenFOAM runner; campaign harness (freeze, verify, SHA256SUMS); ProblemSpec v2 schema.

## 1. SDF representation and genesis

| Item | Facts | Where |
|---|---|---|
| Container | `SDFDesignState`, frozen dataclass. `phi` 3D float32 C-contiguous, phi<0 solid, nodal samples. Fields: `origin_m`, scalar isotropic `spacing_m`, `shape`, bool masks (`design`, `fixed_solid`, `forbidden`, `root`), `narrow_band_width_m`, `generation`, `source_sha256`, topology and reinit policy ids. | src/cfd_sdf/design/sdf_state.py (class ~L103, `create` ~L236) |
| State hash | SHA-256 over metadata JSON, `<f4` phi bytes and the 4 masks. | sdf_state.py `sdf_state_sha256` (~L55) |
| npz schema | keys `phi`, `design_mask`, `fixed_solid_mask`, `forbidden_mask`, `root_mask`, `metadata` (JSON string). Harnesses also use raw Fortran-order float32 (`*.phi_f4_fortran.raw`), both byte orders hashed. | sdf_state.py `save`/`load` |
| Canonical lattice | origin (-1.0,-0.8,-0.6) m, h=0.025 m, 121x65x49 nodes (3.0x1.6x1.2 m). Hard-coded as P22-v2 `NODE_SHAPE`, `ORIGIN_M`, `SPACING_M`. | design/volume_semantics_v2.py L26-35 |
| v18 analytic stadium plate | `plate_phi`: exact SDF of a stadium section extruded in y with flat tips. Parameters xc, zc, alpha, L, t, y_tip, camber, reflex. | scripts/v18_plate.py L64-77 |
| v18 fit rule | fills the v17 solid bbox x(-0.6,0.55), z(-0.25,0.25); Y_TIP 0.4375 m; t by bisection to the v17 smoothed volume: t=0.1153 m, L=1.1039 m, alpha=20.395 deg, chord 1.219 m, span 0.875 m. | v18_plate.py L28-29, L48, L141 |
| Analytic modes | `raw_mode` (L80): heave, surge, pitch, camber (`s^2-1/3`), reflex (`s^3-3s/5`), thick_chord, twist, twist_anti, dihedral, sweep; Gaussian offsets; corrugation; D0 uniform offset. Each mode recomputes the exact analytic phi. `mode_phi` applies it on ACTIVE nodes only. | v18_plate.py L80-122 |
| Harness state model | `harness_direction` returns a max-normalised float32 direction plus a step in mm; state = float32(float64(baseline) + step*direction). | v18_plate.py L124-139; scripts/step01_states.py |
| Older modes | `mode01_modes.py`: trilinear resample, no reinitialization. | scripts/mode01_modes.py |
| Re-derivation policy | v18 modes re-derive phi analytically. Godunov-2 reinitialization exists (`design/sdf_reinitialization.py`) but is not bounded on v17 (REINIT-04 failed). | phase_plan.md L7452 |
| Single-body assumptions | One closed body per state; bbox welded to the v17 solid box; y symmetry in the formula; floats at 0.65 m ride height; `root_mask` empty; clearance profile hard-codes box [-2.5,-1.2,-0.9]..[2.5,1.2,0.9]. | v18_plate.py L1-12 |

Reuse: container, hashing, npz/raw conventions, "analytic re-derivation, not reinitialization", mask set as a component-role skeleton. Replace: single global scalar h, the 3.0x1.6x1.2 m lattice, the one-plate generator; a vehicle needs a CSG tree of per-component SDFs with a distance-correct union and a vehicle-scale lattice.

## 2. Geometry gates (GEOM-02 v2)

`evaluate_geometry_gates_v2` (src/cfd_sdf/design/geometry_gates_v2.py L392). Gate ids `GATE_IDS` (design/geometry_gates.py L52). Profile v2 (crossing-slope rule): docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json. Policy `SDFTopologyPolicyResearchV2`: solid width 1.5h, void width 1.5h, gap 2.5h.

| # | Gate | Check | Assumption |
|---|---|---|---|
| 1 | sdf_finite_structure | finite float32 3D, sign convention, hash, solid and fluid present | none |
| 2 | sdf_distance_property | median abs(|grad phi|-1) in the band <= 0.10 | lattice FD |
| 3 | near_zero_gradient_band | profile v2: crossing_slope_v1, at every sign-change node max opposite-class slope >= 0.5 | h |
| 4 | sdf_boundary_margin | solid >= 1 cell from array faces | lattice |
| 5 | mask_preservation | material only in design/fixed/root, none in forbidden | masks |
| 6 | component_connectivity | 26-connected components, policy max_components | count only |
| 7 | topology_change_classification | allowed_events=[], birth_qualified=False: any birth/split/merge/deletion vs parent fails | needs parent |
| 8 | min_feature_width | 2*EDT ridge width on 4x supersampled occupancy; solid and void >= 1.5h = 37.5 mm | grid-bound |
| 9 | inter_component_gap | >= 2.5h | lattice |
| 10 | export_surface_integrity | r=8 Lewiner mesh watertight, manifold, positive volume, oriented | export mesh |
| 11 | surface_self_intersection | binned broad phase + P20 narrow phase | O(pairs) |
| 12 | domain_clearance | occupancy bbox to flow box >= 0.25 m | hard-coded box |
| 13 | volume_semantics | P22-v2 count sampled_solid_centers <= 8272 on the registered lattice | registered lattice only |

Retained LOWDIM gates: smoothed-volume band 10 % vs v17; zero-level clearance >= 0.15 m; face-connected solid components == 1.

v18 parent: N_phi 7544 (slack 728), all 13 gates pass. Gate 8 fails 1,089 of 1,824 v18 (state, phase) pairs at one-cell occupancy protrusions ("R0 occupancy alias"); GEOM-03 R3 composite NO_GO; SCREEN-01 admits R0-clean designs only.

Reuse: the 13-gate bundle architecture (fail-closed, profile-driven), self-intersection detector, manifold audits. Replace: width/gap measures (occupancy, h-bound), hard-coded domain/clearance, P22 count; topology gating assumes a parent and few components; per-component masks and ownership needed.

## 3. STL export and OpenFOAM pipeline

### 3a. STL export
- scripts/xfid45_round3_export.py `extract(phi, origin, h, r)`: float64 trilinear refinement r in {1,2,4,8} (production r=8, 3.125 mm), scikit-image 0.25.2 Lewiner marching cubes; exact zeros set to +tau on a scratch copy; version hard-pinned.
- scripts/geom02_canonical.py `export_from_arrays`/`export_from_state`: removes sub-cell components, orients by phi sidedness, audits topology. STL float32 binary with X1 gate. v18 parent STL about 643k triangles. Single-process, O(N).

### 3b. Case builders
V1/V2/V3 are mesh levels of one template: scripts/fid01/fid01_build.py (`LEVELS` L50-52); template infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template/.

| Item | Setting |
|---|---|
| Domain | [-2.5,-1.2,-0.9]..[2.5,1.2,0.9] m |
| Background | V1 25x13x9 (0.2 m); V2 50x26x18; V3 100x52x36 (endTime 6000) |
| snappyHexMesh | castellated+snap, no layers; refinementSurfaces design_candidate level (2 3); region allowed_design_domain level 2; nCellsBetweenLevels 3; locationInMesh (-2 0 0.27); maxGlobalCells 2e6; snap tol 2.0, 30 iter |
| Cells | V1 ~39-41k; V2 212,822; V3 1,461,141 |
| BCs | inlet/outlet/sides/top freestreamVelocity (1,0,0) and freestreamPressure; bottom translatingWallVelocity (1,0,0), zeroGradient p; body noSlip. Patch names design_candidate/bottom. |
| Physics | laminar, nu=0.01, rho=1, U=1, Re_L 80 (lRef 0.8, Aref 0.64). No turbulence model. |
| Solver | simpleFoam, SIMPLE consistent, div(phi,U) bounded Gauss upwind (first order); p GAMG relTol 0.01; relaxation p 0.2, U 0.5 |
| Convergence | residualControl p 1e-5, U 1e-6; endTime 3000 cap. V1 567-584 iterations; V2 1562; V3 4548 |
| Mesh checks | checkMesh -allGeometry -allTopology; one "Failed 1 mesh checks" (concave cells <= 8 %) allowed |
| Forces | forceCoeffs on design_candidate, CofR (0.25,0,0), lift (0,0,1); window last 25 % of rows (min 20); N = 0.32 x Cd, -0.32 x Cl; window mean, std and drift recorded (x3_formal/runner.py `force_window` L129) |
| Cost | V1 ~73 s solver, ~294 s wall; V2 ~6.1 h per 13-case kernel; V3 ~8-18 h per case |

Rigid sub-cell shift phases: 32 Halton shift vectors with mirror pairs, 0.5-4 mm per axis (a mesh-phase ensemble).

### 3c. Runner and hashing
- scripts/local_openfoam.py runs a registered kernel's runner.py unchanged in Docker; mounts /kaggle/working and /kaggle/input/<slug>. CLI: build, run KERNEL --out DIR [--dataset DIR] [--cpus 4 --memory 8g], run --subset, stage-x3.
- Image `cfd-local-openfoam:2512-noble-amd64` (sha256:e9ceb8a79fd8...), ubuntu:24.04 noble, linux/amd64 (Rosetta on Apple silicon), OpenFOAM v2512 2512.0-2 locked by SHA; 297 dpkg entries; gmsh 4.15.2, numpy 2.5.4.
- Wrapper refuses to run if the image id differs; records dpkg_after_matches_lock; runner checks CRITERIA_SHA256 and input SHAs.
- Per-case case_result.json: stl_sha256, per-stage wall and RSS, snappy/checkMesh/solver/force-window; logs gzipped, mesh deleted.
- U3/X3 pipeline LOCAL_ENV_PASS_BITWISE; T2-0c gmsh pipeline LOCAL_ENV_FAIL.

### 3d. T2-0 2D RANS pipeline and the adjoint failures
- scripts/t20_case.py (gmsh 2D), t20_foam.py, t20c_case.py, t20d_case.py, t20b_adjoint.py. One 2D Tyrrell-026 section, Re_c 4.6e5, moving ground, SA-WF primary (SST-WF, SST, LM also), Kaggle CPU. Verdicts T20B_NO_GO, T20C_MORPH_NO_GO, T20D_NO_GO. Cost 15 s to 92 min per evaluation; gmsh meshes vary run to run; remeshing noise 0.2-0.9 % of Cl.
- ADJ_FAILED (T2-0b): scripts/t20b_adjoint.py (adjDownforce, adjointOptimisationFoam singleRun, frozen turbulence, volumetricBSplines 10x6x3). Record docs/evidence/t20b_registered_2026_10_19/verdict.json L230, analysis.md L79-80, note.md L23 (primal converged, SIGFPE in the `pa` GAMG solve at adjoint iteration 1322). Kernel infra/kaggle/kernel_t20b_cpu/runner.py. DAFoam not attempted.
- Stage S Work F (3D body-fitted adjoint): src/cfd_sdf/stage_s_adjoint_case.py, stage_s_adjoint_qualification.py (volumetricBSplines 8^3; adjDrag, adjDownforce). FD vs adjoint failed the 5 % gate on random-seed directions; ablations did not fix it; "fail-closed and unqualified". Reduced-basis K=16 FD registered but never run past S0R/S1R.
- Stage T porous/Brinkman adjoint: Cartesian density with custom openfoam_extensions/porousDirectionalForce; not body-fitted.

Reuse: STL chain, Docker runner and lock discipline, case template idea, force-window extraction, case_result schema. Replace: laminar first-order template (needs turbulence model, layers, second-order schemes, per-component patches); single design_candidate patch; hand-set locationInMesh and refinement regions; snappy-from-STL is not differentiable or cross-platform reproducible.

## 4. WaterLily kernel path

1. docs/harness/*_campaign.json lists baseline raw phi, direction raws (max-norm 1), per-state step_mm/sign and identity SHAs.
2. scripts/harness.py build|smoke|freeze|verify (src/cfd_harness/campaign_schema.py, campaign_build.py, campaign_runner_template.py, campaign_verify.py) renders infra/kaggle/kernel_<campaign>_<k>/runner.py; runner checks the pinned commit, regenerates every phi, checks both byte orders, calls the job.
3. scripts/waterlily_lowdim02_flow32_job.jl loads the raw phi, builds GridSDF (trilinear), device copy, composite body, WaterLily.Simulation.
4. Per-run W4_CANONICAL_ORIGIN_M (x,y) places the body at sub-cell phases (JOB-02); z fixed per kernel.

| Item | Detail | Where |
|---|---|---|
| Flow cases | flow_N = N cells per 0.8 m; domain [-2.5,-1.2,-0.9]..[2.5,1.2,0.9]; flow_16 (100,48,36), flow_24 (150,72,54), flow_32 (200,96,72) 1.38M, flow_48 (300,144,108) 4.67M. validate_w4_case hard-codes n in {16,24,32}. | julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl L7-104 |
| Re | Re_L = 80; U=1, L=N cells, nu=N/80. | L9-45 |
| Boundaries | inflow velocity, convective exit, slip sides/top; V16MovingGroundBody planar half-space +1 m/s at z=-0.9 (approximation). | src/V16PhysicalProfile.jl; job L337 |
| Body | CandidateCWaterLilyBody(NormalFloorWaterLilyBody(GridSDF)) normal floor 0.25; candidate-only body for forces. | job L317-336 |
| dt | WaterLily 1.8.0 adaptive sim_step!; steps ~183.6n + 7.5n^2 (13,549 at flow_32, 27,372 at flow_48); T_END 120, BURN_IN 80 tU/L. | job L58-60 |
| Forces | pressure + viscous; drag +Fx, downforce -Fz; window mean; half-window drift. | job L90-120, L213-260 |
| Cost/memory | T4: flow_32 ~342 s, 186 MB (134 B/cell); flow_48 ~2,267 s, 612 MB (131 B/cell); flow_24 ~110 s; flow_16 ~38 s. Float32. | summaries; grid02_plan L47 |
| Runtime | Julia 1.12.6 by SHA; WaterLily 1.8.0. | campaign_runner_template.py L21-22 |

AD/FD attempts (all flags false):

| Attempt | Code/evidence | Status |
|---|---|---|
| FD-05/06 (v17 flow_24) | docs/issues/37_fd05_result.md, 37_fd06_result.md | FAIL: 4 of 6 combos 6.4-8.7 % off the 5 % plateau |
| FD-07 | scripts/sdf_native_fd07_*; docs/issues/37_fd07_*.md | diagnosis: half-cell sign-consistency dominant cause |
| FD-08 v2 | src/cfd_sdf/fd08_*.py; docs/evidence/fd08_v2_formal_2026_10_07_amend3 | formal PASS 24/24, interior interpolation only, not a gradient |
| Forward AD spike (GRAD-02) | scripts/waterlily_grad_forwarddiff_spike*.jl; docs/issues/22_... | capability only; Enzyme reverse MethodError |
| DIAG1-5 | scripts/waterlily_grad_g2_diag*.jl; phase_plan L6995-7151 | tangent explodes from a far-field corner (onset ~step 838); DIAG5 R4_INCONCLUSIVE; AD tangent changes ~60 % under 1-ulp primal noise while the finite response changes 0.1 % |
| GRAD-TA1 | scripts/waterlily_grad_ta1_2026_10_15.jl; docs/issues/23_grad_ta1_result_2026_10_15.md | INCOMPLETE/BLOCKED; tangents > 1e30 at step 700 |
| Decision | phase_plan L7476-7490 | #23 the single off-path research issue; gradient-free screening default (R5) |

Reuse: harness (schema, freeze, verify, JOB-02 placement), GridSDF adapter, force-window recipe, Kaggle runner, placement/grid confound evidence. Replace: WaterLily as the gradient source.

## 5. Optimizer and proposer code

| Component | Interface | Notes |
|---|---|---|
| SCREEN-01 response surface | scripts/screen01/screen01_pool.py (gen, p0, design, propose, constrained_argmax, d_optimal9, fit9, predict9); analyze_screen01.py; screen01_check.py | quadratic 9-parameter over 3 modes; not general |
| LOWDIM / OPT-01 | src/cfd_sdf/lowdim0{1,2a,3}_contract.py | small subspace secant steps; OPT-01 v1 rejected |
| Mode generators | scripts/mode01_modes.py, v18_plate.py, mode01_v18_prescreen.py | solver-free |
| Stage T density/Brinkman | src/cfd_sdf/stage_t_loop.py (ProjectedGradientBackend, VolumeTargetBackend, ProjectedVolumeTargetBackend, run_stage_t_loop), density_optimizer.py, projected_restoration.py, nonlinear_acceptance.py, fixed_grid_optimizer.py (projected-gradient and slsqp-linearized, scipy SLSQP) | the only gradient loops; Cartesian density-Brinkman with OpenFOAM adjoint; 97 accepted steps; surrogate ranking did not transfer |
| B-spline Stage S | stage_s_reduced_basis.py (K=16), stage_s_adjoint_*.py, adjoint.py | adjoint fail-closed |
| MMA/GCMMA | none | |
| Parametric front wing | src/cfd_sdf/parametric.py, optimization.py | legacy demo |

Reuse: nonlinear_acceptance.py and the TrialProposal/accept-reject/rollback/checkpoint structure of stage_t_loop.py; ResponseOracle/ParentOracle/TrialBackend protocols. Replace: every mode-specific proposer; an MMA or projected-gradient backend for hundreds-thousands of variables is new.

## 6. Harness, registration and CI

- Campaign schema: SC.validate_campaign (src/cfd_harness/campaign_schema.py). Fields: harness_version "harness v1.1", campaign_id, owner, repo_url, job_env_common, measurement, domain, baseline, directions, states (SHAs both byte orders), kernels (job, case, budgets, runs). Budget rule: solver_wall_time_cap_s + reserve + instantiate + gpu_probe <= kernel_timeout_s.
- Freeze: <campaign>.prerun_freeze.json (+.sha256): identity-free Kaggle check, pins of every source file (Julia include closure), smoke-table SHA, harness_tool_sha256.
- Evidence dirs: docs/evidence/<study>_<date>/ with inputs/, kernel_output/, freeze*.json, analysis.json/.md written once, SHA256SUMS; scripts/check_sha256sums_tracked.py; write_once helpers; --check re-derive modes.
- PROC-01: EXPLORATORY_COMMITTED and REGISTERED_FROZEN; docs/exploratory_index.md append-only.
- Tests: 273 files; source hashes vs freezes; lineage via git show; byte-replay of frozen records.
- CI (.github/workflows/ci.yml): push to main, PRs to main and codex/kaggle-batch-migration; ubuntu-latest and macos-latest, Python 3.12; pip install -e ".[dev]"; compileall; git diff --check; pytest -q 1 thread. No OpenFOAM, Julia or GPU; geometry-gates extra not installed.
- Pins: Python >=3.10; numpy>=1.26, scipy>=1.11, trimesh>=4.4, pyvista>=0.43, pyyaml, typer, rich, rtree; extras geometry-gates (scikit-image==0.25.2), metal, plots, dev. Docker image lock; Julia 1.12.6, WaterLily 1.8.0.

Reuse: freeze/verify/SHA256SUMS discipline and write-once pattern. Replace: the single-baseline-plus-directions state model (phi = baseline + step x direction); per-state W4_* env vars encode single-lattice assumptions. Add solver-side CI smoke if needed.

## 7. Known limits recorded in docs

| Limit | Record |
|---|---|
| Single parent, one object | every registered campaign uses the v18 plate with 3 modes, Re 80 |
| Fixed far-field domain and clearance | [-2.5,-1.2,-0.9]..[2.5,1.2,0.9] in Julia constants and blockMesh; GEOM-02 clearance >= 0.25 m; profile qualified on one body |
| R0 occupancy alias | width gate flags one-cell protrusions at sub-cell phase; R3 NO_GO; SCREEN-01 restricted to R0-clean |
| flow_24 demoted | flow_32 proposes, flow_48 confirms |
| Poisson confounding | flow_40 Poisson-confounded (GRIDRES-01); flow_32 the only grid commensurate with the 0.025 m lattice |
| Grid and placement dependence | downforce slope along one direction varies 50-100 % across grids and placements; OpenFOAM retains 0.57-0.77 of WaterLily differences |
| Fidelity and physics | both solvers laminar Re 80; T2-0 NO-GO; RE-01 scope Re_c <= 3.8e3; pure heave TIER_B_FAIL |
| Multi-body / ground / wheels | ground a planar moving half-space or translating bottom patch; no multiple bodies; no rotating wheels in code (requirement only in docs/fsae_readiness_execution_plan.md L497, L507) |
| Symmetry planes | none in the SDF line; full span simulated with slip side walls |
| ProblemSpec v2 | src/cfd_sdf/problem_spec.py (1,445 lines): geometry roles (fixed_solid, initial_design, design_domain, forbidden_region, root), multiple flow cases (freestream, k_omega_sst, motion_profiles incl. moving ground), responses (force, moment, pressure_loss, flow_rate, plugin), multipoint objectives, constraints, topology policy (examples/generic_problem_v2/project.yaml). Compiled only into the Cartesian porous OpenFOAM case (solver_case_compiler.py). |
| Gradient status | exact AD, tie-averaged AD, 3D and 2D adjoint all failed or blocked |
| Grid h scale | gates and P22 defined for h=0.025 m on a 3 m lattice; a vehicle would not fit; no multi-scale SDF |

## 8. Reuse versus replace summary

| Area | Judgment |
|---|---|
| SDF container, hashing, masks | reuse; generalise h/origin/shape; per-component fields; CSG |
| Analytic generator | replace; keep "exact analytic SDF re-derived per parameter set" |
| Gate bundle | reuse framework; replace width, gap, clearance, P22 |
| STL export | reuse; swap for a mesh path whose derivative w.r.t. phi is defined |
| OpenFOAM case builder | replace physics and meshing; keep result schema and force window |
| Docker runner and lock | reuse unchanged |
| WaterLily kernels | keep as cheap Re-80 screening oracle only |
| Harness and freeze | reuse discipline; replace baseline+direction schema |
| Optimizer loops | replace; reuse acceptance/checkpoint/rollback |
| T2-0 / adjoint | adjointOptimisationFoam crashed (SIGFPE, frozen turbulence, wall functions); discrete adjoint on SDF-generated body-fitted meshes is new development |
