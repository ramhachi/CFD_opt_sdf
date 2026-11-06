# GEN-01 plan rev 0 (7bb2049e, SHA-256 7a1432c0...) review, angle G: systems, software, compute and governance

(Opus reviewer, 2026-11-01, verbatim.)

**Verdict: GO_AFTER_FIXES.** The architecture's direction is sound and the plan is unusually honest. But ADJ-00 cannot be registered as written, for four reasons: it is not coherent with PROC-01; it conflicts with the current roadmap authority (phase_plan R5, #66, #67, STATE); it has no fail-closed rules for adaptive cloud campaigns; the cost model understates spend by 2-4x in the cases that decide the budget.

## Findings

**G1 (P1) §4.2, §3.4, §6.4. "Exploratory but pre-registered" ADJ-00 breaks PROC-01.**
- ADJ-00 is labelled exploratory, yet it does three binding things: picks the toolchain for the next 14 months; sets the contract numbers from its own data, so the thresholds come from the data they then judge; fires the reduced-basis branch.
- PROC-01 (phase_plan, 2026-10-16) says exploratory results "never feed a qualification flag, a threshold, a gate", and that registration is "required ... for any claim used in a decision".
- WING-3D-01 has the same defect. sigma_J comes from an exploratory "Stage 0 type charter", and g_min = 3 sigma_J then becomes the gain threshold.
- The only precedent is RE-01's recorded reading (phase_plan L7758): exploratory statistics set engineering parameters only, through formulas fixed beforehand, with "every decision threshold ... fixed before Stage 0".
- Fix: either register ADJ-00 as REGISTERED_FROZEN with the contract thresholds fixed now; or split it: ADJ-00a exploratory and capability-only (does it run, memory, time, feeding node counts only), ADJ-00b the registered contract test plus the selection. For sigma_J, fix the formula in the registration; measure sigma_J inside the registered study, as a first frozen phase on states that are not reused; exploratory sigma_J may set budgets only. Confidence high.

**G2 (P1) §3.9, §8, §10.4. Conflict with roadmap authority, and what must be written where.**
- Four standing records contradict the plan: phase_plan R5 "no gradient backend on the critical path"; #66 body: the backend/cost decision (B6) belongs to M4, and "起票・資料作成は新規 CFD・実装・追加課金を開始しない", "AD/adjoint を不要な完了 gate にしない"; #67: L3 blocked until a registered high-Re evaluator GO and the #66 scope decision; STATE: "#23 remains the sole off-path gradient research issue" and "no rented API or new spending was selected".
- GEN-01 starts cloud spending and an adjoint main line in month 1, with M4 only in month 3, while calling itself subordinate to phase_plan.
- Fix, before the ADJ-00 registration: phase_plan entry recording the user's decisions verbatim (§11 b: cloud provider and budget cap); amend R5, R6 and the 2026-10-16 backend addendum explicitly; add a milestone gate, not a calendar month: before M4, GEN-01 is limited to CLOUD-ENV-01 (new), GEOM-K1, ADJ-00 and LOOP-2D-01, each at its capability or methodology claim ceiling; EVAL-3D-01 (the IFW evaluator, split out of WING-3D-01 with its own fail branch back to M4, as #67 requires) and every later stage wait until M4 records option B with GEN-01 as its instance. STATE: add a GEN-01 row and edit the two sentences quoted. Issues: an umbrella issue plus children CLOUD-ENV-01, ADJ-00, GEOM-K1, LOOP-2D-01, EVAL-3D-01, WING-3D-01, WW-01, CAR-01, VAL-X; re-scope or supersede #33, #40, #32; link #69 to UNS-G; #23 stays WaterLily-only. exploratory_index: every exploratory probe, failures included. Confidence high.

**G3 (P1) §6.0, §6.4-6.6, §9. Adaptive optimisation campaigns have no fail-closed, exhaustive rules.**
- No termination rule ("30 反復" is a cost assumption). Nothing says which iterate is the deliverable (best-of-trajectory carries the optimizer's curse). "原因分解...再登録は 1 回" leaves open what may change and who decides. "80 % で縮小して登録し直す" means rescoping after partial data are visible. No data-loss rules for eviction, node failure, capacity errors or controller crash (is an OOM at the registered node count a result or an infrastructure loss?). A new software stack will have defects; with one re-registration, defect restarts use up the science retry. "記述的 URANS で符号一致" is listed as a pass condition although descriptive.
- Fix: a generic registered-adaptive-campaign protocol in rev 1. Freeze: code SHA, parent, hyperparameters, acceptance rule, termination (maximum accepted steps, maximum consecutive rejections, budget, stationarity). Deliverable: the last accepted iterate, or another rule fixed in advance; confirm it on fresh mesh realisations. Labels (exhaustive): PASS / FAIL / INCONCLUSIVE / INCOMPLETE_BUDGET / INFRA_LOSS / INVALID_DEFECT, each with its branch. Defect restarts separately capped, with a root-cause record, restarted from the parent under a new freeze. Evaluations atomic, re-run only from identical inputs; partial data never pooled. Confidence high.

**G4 (P1) §5 and gen_cost.py. The cost model understates spend.**
- Whole-node rental: gen_cost prices only the cores in use, but nodes rent whole and every hpc7a size costs the same (verified). WING-3D-01 uses 60 of 192 cores: the per-OP campaign is 825-3,060 USD, against the model's 261-969. LOOP-2D-01 uses 4 cores but §4.2 mandates one node type, so 344-1,275 USD against a 200 USD budget.
- Operating points: the table is for one OP while budgets assume 2-3. CAR-01 with 3 OPs: 11,100-43,700 USD before validation, against a 30,000 cap.
- Yaw cannot use the half-model symmetry plane: about 5e7 cells, roughly twice the memory and cost.
- No Spot on hpc7a (On-Demand, Reserved and Savings Plans only), so "spot ~ 0.4x" is invalid for it; Azure HBv4 Spot exists at about 1.33-1.74 USD/h with eviction.
- Fallback branch (K = 30-50, centred FD): 2,900-11,600 USD per OP on WING-3D-01, against the 4,000 cap.
- NLopt's default inner-iteration gradients would turn each rejected trial into a full gradient, roughly doubling campaign cost (G7).
- Omitted: snappyHexMesh with layers at 25M cells, sigma_J ensembles, before/after mesh pairs at checkpoints, development and debug runs, storage, idle nodes.
- Fix: rewrite gen_cost.py to price node-hours: node count = max(compute, memory) x wall time; multiply by OPs and adjoints per OP; add the fallback branch, meshing, sigma_J and a development factor (1.5-2x); print each stage cap against its bound; redo §5.2 before the user decides (b). Confidence high on arithmetic, medium on multipliers.

**G5 (P1 for the ADJ-00 part) §2 C/D, §3.9. Two OpenFOAM builds and the evaluator's identity.**
- Verified: DAFoam v5.0.0 is "fully compatible with OpenFOAM v2506" and "Migrated to the new AD-enabled OpenFOAM distribution"; OpenFOAM-AD differentiates only the necessary libraries.
- §2 C names simpleFoam as the evaluator. If DAFoam wins, the optimising primal is DAFoam's solver and its own objective classes in the v2506 AD fork; the convergence certificate and force window (v2512 function objects) do not carry over.
- "ビルドの違いが検証の独立性になります" is wrong: a build difference is a confound, not independence. The IFW evaluator registration must be done on the build that optimises, and the verifier needs its own registration.
- Fix: in ADJ-00, a build-equivalence measurement (parent plus one perturbation, same mesh, both builds, difference-of-differences sigma_build); add "evaluator consolidation" to the selection rule; order the verification tiers: same build on another mesh family first, then the other build. Confidence medium-high.

**G6 (P2) §2, inventory §8. The existing code supports less of §2 than the plan claims.**
- SDFDesignState is a dense single-h lattice with four boolean masks; its docstring makes phi canonical ("meshes are derived artifacts, never the design state"); 88 files reference it. The plan's surface-based working state needs a new hashed state type: base surface SHA, u, filter parameters, component labels.
- ProblemSpec v2: geometry regions are .stl files with five roles only; no fields for design variables, r_c, geometric constraints, rule sets, or per-OP attitude; `_is_v2_execution_ready` requires grid.kind == "uniform_cartesian".
- campaign_schema.py is harness v1.1 for WaterLily on Kaggle T4; cannot hold an adaptive campaign. local_openfoam.py runs single-host Docker emulating /kaggle paths. fid01_build.py is a study-specific template copier.
- Missing modules: (a) the map and its transpose between design nodes and each mesh's CFD wall points (per OP and per remesh); (b) sharp features; (c) component labels through extraction, with snappy regions and feature edges at junctions; (d) CAD ingest and cleanup; (e) ProblemSpec v3 and compiler; (f) morph adapters per toolchain; (g) an unattended, resumable cloud controller; (h) harness v2 for adaptive cloud campaigns; (i) a large-artifact evidence store with a retention rule.
- On (b): h = r_c/4 with r_c = 30 mm gives 7.5 mm; cannot represent a 3 mm endplate or a 1-2 mm trailing edge; the phi round trip blunts the parent itself. Keep the CAD-derived surface as the master, remesh from it at checkpoints, use phi only for constraints and topology. Confidence high.

**G7 (P2) §2 E, §6.2. Dependency choices.**
- NLopt MMA: v2.11.0 (GitHub 2026-06-05, PyPI 2026-07-17); MMA code MIT, NLopt LGPL; inequality constraints only; gradients evaluated on inner iterations by default (inner_gradients = 1, new in v2.11); black-box loop, cannot insert the 3 sigma_J/rho rule, (recalled) not checkpointable across multi-day evaluations. The repo's nonlinear_acceptance.py already evaluates the gradient once per parent, uses function-only trials and rolls back. Recommendation: own the loop; extend that controller with the noise floor and a small trust-region subproblem; NLopt only if MMA is truly needed, with inner_gradients=0 and an x-hash cache.
- trimesh winding numbers: none; signed_distance takes the sign from face normals plus ray casting and returns positive inside (opposite of the repo's phi<0 = solid; verified in source). Use libigl 2.6.3 (MPL-2.0) winding-number signed distance for non-watertight CAD.
- Cotangent Laplacian: use robust-laplacian 1.1.0 (MIT: SPD, intrinsic Delaunay, lumped mass, tolerates nonmanifold meshes) instead of hand-built cotangent weights on marching-cubes slivers.
- IDWarp or RBF: dictated by the toolchain (IDWarp for DAFoam, OpenFOAM motion solvers for adjointOptimisationFoam, SU2_DEF for SU2).
- SU2: v8.6.0 published 30 Oct; CUDA with discrete adjoint "Experimental"; SA wall-function fix only in this release; snappy meshes need polyhedra decomposition and SU2 is vertex-based. Make SU2 conditional: only if DAFoam and adjointOptimisationFoam both fail.

**G8 (P2) §3.3, §4.2. Reproducibility on the cloud.**
- gmsh is "not run-to-run deterministic, on Kaggle or here" (local_openfoam_env_gate L66), so fixing the node type does not fix it. LOOP-2D-01 and ADJ-00 case (3) must use the hash-pinned T2-0c base mesh; the T2-0c evidence holds only SHA-256s, not mesh.msh.gz, so retrieving the mesh must be a named task.
- No fallback if the bitwise check fails: define the reproducibility class in advance (bitwise, or a registered tolerance folded into sigma_J).
- Multi-node: pin decomposition method and processor count (snappy's output depends on them) and MPI/libfabric versions. On HPC, Docker is normally replaced by Apptainer, so the image-ID lock needs a new format. Restarts: binary at full precision.
- Pin images by digest: dafoam/opt-packages:latest re-pushed 2026-10-29, the v5.0.0 tag on 2026-05-10; amd64-only.
- Fix: a CLOUD-ENV-01 engineering gate, modelled on LOCAL-OF-01, before ADJ-00.

**G9 (P2) §3.4, §4.2, §8. ADJ-00 depends on things that do not exist in month 1.**
- Contract 2 needs filtered random directions (GEOM-K1 filter, month 2). Contract 3 needs an optimiser and acceptance rule. Contracts 1-2 need sigma_J, and §3.5(a)'s remesh-ensemble sigma_J is undefined on the fixed TMR NACA 0012 grid.
- Contract 4 on case (2): converging to 1e-8 on Ahmed 25 deg may be impossible for every candidate, deciding the branch in advance.
- Selection rule gaps: partial passes, NOT_RUN by cap, ties, K "30-50".
- Fix: order CLOUD-ENV-01 and the GEOM-K1 filter first, then ADJ-00; make contract 3 a fixed-step steepest-descent rule; sigma_J definition per case; exhaustive selection table; fixed K.

**G10 (P2) §4.2, §5.2, §11. Budget enforcement and operations.**
- Caps are prose only; 1,500 USD is 208 node-hours on hpc7a. Enforce mechanically: IAM limited to the registered instance type and count; budget alarms with automatic stop; idle shutdown; a cost ledger per study.
- Capacity: HPC vCPU quotas must be requested; multi-node launches face single-AZ capacity errors.
- User-only actions (month 0): account, billing, SSO, quotas; the controller needs an instance role, not user credentials.
- CAD data residency: hpc7a is in us-east-2, eu-west-1, GovCloud and eu-north-1; sponsor CAD going to US regions needs a decision.

**G11 (P2) §8. Effort and schedule.** Rough estimate (agent-weeks): GEOM-K1 8-12; ProblemSpec v3 and compiler 4-6; cloud environment, controller and harness v2 4-6; adjoint plus morph adapter per toolchain 3-6 each; optimiser loop 3-4; verification pipelines 3-4; PROC-01 overhead about 9 studies 1-2 each; total about 45-70, before compute wall-clock (CAR-01 8-32 days per OP). Month 1 also carries XV-01 and RE-01. User effort unscheduled: account setup, CAD for every component, budget approvals; uncosted: manufacturing parts for VAL-X. STATE records "No deadline": gate by milestones, drop calendar-tied decisions. Confidence medium.

**G12 (P3) §6.2. GEOM-K1 pass criteria need precision.** The Helmholtz filter (M + r^2 K)^-1 M is not symmetric in the Euclidean inner product; use the dot-product test <Fu, v> = <u, F^T v> to 1e-12 and state whether sensitivities are covectors or densities. "FD 1e-6" fails at trilinear-interpolation kinks; self-thickness is not analytic. Idempotence needs a Hausdorff tolerance. "13 gate 相当": list the gates; the P22 count and the hard-coded domain box are specific to the old lattice.

**G13 (P3) §4.1, §5.1. The memory table uses a legacy mode.** In pyDAFoam.py (main), the default useAD reverse mode is documented as "a Jacobian free approach"; the 113 kB/cell figure (2020 explicit Jacobian) is a legacy upper bound. Explicit mode would also be memory-bound on hpc7a: 4 GiB/core is less than about 5.6 GB/core at 5e4 cells/core. ADJ-00 should measure the default mode.

**G14 (P3) Licences and data.** OpenFOAM and DAFoam images are GPL-3: fine for internal use, but do not publish modified images without the source. NLopt LGPL overall with MIT MMA; libigl MPL-2.0; robust-laplacian MIT; trimesh MIT (recalled). Get the team's agreement on where the CAD is stored.

## What the plan gets right (keep in revision)
- Fixed-topology morphing within a campaign; remeshing only at checkpoints, with the jump recorded as a mesh difference, not a gain.
- A primal that does not converge is a result, not retried.
- The gradient contract is "sufficient for optimisation", with 5 % agreement descriptive only, and FD comparisons only where the response is at least 5 sigma.
- Claims are paired differences across mesh families and models, never absolute values. The §0 list of what is not promised.
- Pre-declared fallback branches, caps without extension, and r_c frozen per registration.
- A reproducible cost script, and the finding that memory and robustness bind, not dollars.
- Separate compute pools; #23 not reopened; the LOOP-2D-01 claim ceiling written on line 1; standard test cases before the main line; more than one toolchain candidate.

## Claims checked externally
- NLopt v2.11.0 (GitHub 2026-06-05; PyPI 2026-07-17); MMA code MIT; library LGPL; inequality constraints only; inner_gradients defaults to 1, new in 2.11. Verified.
- DAFoam: releases v5.0.0 (05 May), v5.1.0 (29 Jul), v5.1.1 (12 Sep); v5.0.0 compatible with OpenFOAM v2506, moved to OpenFOAM-AD, "forward-mode AD ... unreliable"; Docker dafoam/opt-packages:v5.1.1 amd64 ~2.36 GB, latest updated 2026-10-29, dafoam/openfoam:2506 exists; OpenFOAM-AD v2506-ad branch; Jacobian-free mode default in pyDAFoam.py. Verified (GitHub, Docker Hub API, get-started page, source); OpenFOAM-AD README via snippet only.
- AWS hpc7a: four sizes (24-192 cores), each 768 GiB and 300 Gbps EFA, same price for every size; On-Demand, Reserved, Savings Plans, no Spot; regions us-east-2, eu-west-1, GovCloud, eu-north-1. Verified from AWS pages; the 7.20 USD/h from aggregators (Vantage 9.08, Cloud-Mercato 16.03); official pricing page not fetched.
- Azure HB176rs_v4: on-demand 7.20 USD/h; Spot 1.33-1.74 USD/h East US. Aggregators only.
- trimesh: no winding numbers; positive-inside sign. Verified in source.
- libigl 2.6.3, MPL-2.0, winding-number signed distance in C++ headers; Python exposure not verified.
- robust-laplacian 1.1.0, MIT, SPD. Verified.
- SU2 v8.6.0 on 30 Oct; CUDA with discrete adjoint "Experimental"; SA wall-function divergence fix. Verified.
- In the repo: gmsh run-to-run nondeterminism (local_openfoam_env_gate L66); T2-0c meshes excluded from the evidence; #66 and #67 issue texts (via gh). Verified.
