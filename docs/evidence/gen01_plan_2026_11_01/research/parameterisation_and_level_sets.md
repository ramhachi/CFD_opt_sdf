# Brief B report: generic parameterisation, regularisation, level sets, topology, constraints

(sonnet research agent, 2026-11-01, verbatim)

## 1. Node-based shape optimisation with regularisation

| Item | What I verified | Source |
|---|---|---|
| Vertex Morphing (VM) origin | Hojjat, Stavropoulou, Bletzinger, CMAME 268 (2014) is the cited origin. Bletzinger, SMO 49(6):873-895 (2014), doi:10.1007/s00158-013-1031-5, derives the filter from a "shape filtering" step. It affects only the shape update, not the initial shape. Abstract-level only for both. | Springer doi:10.1007/s00158-013-1031-5 |
| Filter radius semantics | The radius sets the waviness of the result and steers the optimiser to a different local minimum. Features smaller than the radius are preserved. A good radius is unknown a priori. Large deformations can make the radius too small for the surface mesh. Read. | Antonau et al., SMO 65 (2022), doi:10.1007/s00158-022-03279-w |
| Radius vs mesh size | The smallest allowed radius should be 2 to 4 times the element size. Smaller radii need mesh refinement. Read. | Bletzinger, IASS 2024 paper 627 |
| Adaptive VM | Computes the minimum radius per node, smooths the radius field, and allows local minimum radii. Read. | Antonau 2022 |
| Whole-car case (BMW M4 GT4) | 114.7 M cells and 1,950,141 node variables. Steady k-omega SST with a frozen-turbulence adjoint in STAR-CCM+. Downforce constraint plus 115,830 geometric "max shape update" constraints, aggregated into one. Radii by part: overall 30 mm, rear wing 50 mm, trunk lid 200 mm. 210 h wall time (120,960 CPUh), about 15 h per iteration, so roughly 14 iterations. The run stopped on the iteration limit. Without the downforce constraint the optimiser dropped downforce dramatically. Rear wing plus splitter alone gave about 4% drag reduction. Total gain for the full design not stated. | Antonau 2022 |
| Packaging constraints in VM | Nodal no-penetration against arbitrary bounding surfaces, tested on two automotive CFD cases. Abstract-level. | Geiser et al., SMO 56:1507-1519 (2017), doi:10.1007/s00158-017-1819-9 |
| Regularisation inside the adjoint chain | Design variables are a rough per-face displacement field. A Laplace-Beltrami or p-Laplacian regulariser maps it to a smooth displacement. The regulariser is itself differentiated, so gradients stay exact. This permits CG, BFGS and SQP with constraints. Read. | Papoutsis-Kiachagias & Giannakoglou, EUROGEN 2023, doi:10.7712/140123.10199.18949 |
| DrivAer in that paper | Fastback with mirrors and wheels, 5.3 M cells (half car), moving road, rotating wheels via boundary condition, SA with wall functions. The steady primal oscillates, so J is averaged over the last 3500 of 5500 iterations. 20 CG cycles. Laplace-Beltrami with r = 2 m gave 5.1% drag reduction. p-Laplacian gave 14.7% with an irregular shape. No experimental validation. | same |
| Sobolev smoothing as Hessian approximation | ONERA M6 with 198 FFD variables, SST. Drag fell 26.8% (surface smoothing), 26.6% (plain gradient descent) and 28.85% (SLSQP). One-shot with the smoothing preconditioner 30.1%. Smoothing mainly helps step size and stability. Read. | Dick, Gauger, Schmidt, arXiv 2109.15279 |
| DrivAer rear end, discrete adjoint | 1 M cells, y+ about 46. Wheels and mirrors removed, underbody smoothed. 50 FFD variables and 38 constraints. CD 0.140 to 0.123 (12.1%) in 21 iterations, 21 adjoint and 71 flow solves, 58 h on 32 cores. Adjoint error 0.76% against finite differences. Poor flow convergence the main obstacle. Only wind-tunnel validation is the Ahmed body, 9.4% drag reduction. Read. | He et al., Comput. Fluids (2018) |

Not found: Hojjat 2014 settings; any Toyota, Audi or VW whole-car VM paper 2014-2026. VW/Audi evidence is Othmer, J. Math. Ind. 4:6 (2014), abstract-level. SAE 2020-01-0915 snippet: about 8 drag counts (steady) and 10 (unsteady) on a production SUV, mirror and air-dam changes checked in a wind tunnel.

## 2. Level-set / SDF topology optimisation

| Topic | Finding | Source |
|---|---|---|
| Fluid level-set history | Zhou & Li (JCP 2008), Challis & Guest (IJNME 2009) abstract-level. Kreissl & Maute (SMO 2012) XFEM Navier-Stokes. | SMO doi:10.1007/s00158-012-0782-8 |
| CutFEM fluids | Villanueva & Maute, 3D laminar, Re < 200, level-set parameters tied to design variables. | arXiv 1702.02473 |
| CutFEM shape optimisation | Burman et al., CMAME 328:242-261 (2018). Fixed mesh, level set transported, no remeshing. Linear elasticity 2D. | arXiv 1611.05673 |
| Hole seeding | Barrera, Geiss, Maute: density-field hole seeding. Høghøj, Andreasen, Maute, SMO 2025, doi:10.1007/s00158-024-03956-y: density-based seeding in XFEM level-set fluid optimisation, laminar. | arXiv 1909.10703 |
| High-Re level set | A 2021 JCP paper: 2D RANS with a level-set boundary, immersed boundary and standard wall function, AMR at the wall. Only high-Re level-set precedent found, 2D. | JCP S0021999121005258 |
| Brinkman failures | Theulings, Langelaar, van Keulen, Maas, SMO 66:133 (2023): low-permeability solids leak; VANS gave fewer inferior local optima. Abdelhamid & Czekanski: maximum inverse permeability depends on mesh size and flow. | TU Delft; arXiv 2302.14156 |
| Explicit-contour precedent | Picelli et al.: binary variables on a grid, smooth contour extracted, then k-epsilon with wall functions on an explicit boundary. Up to Re about 1e5. | arXiv 2302.05288 |
| Body-fitted level-set remeshing | Dapogny & Feppon, C. R. Math. 361 (2023), doi:10.5802/crmath.498: exact mesh of the shape each iteration, topology change handled. Feppon et al., CMAME 376:113638 (2021): heat exchangers, minimum thickness, non-mixing as a minimum distance between phases. Laminar only. | Numdam; HAL |
| Minimum thickness via SDF | Allaire, Jouve, Michailidis, SMO 53:1349-1382 (2016). | IP Paris |
| Velocity extension and reinitialisation | Hilbertian extension-regularisation extends the normal velocity, adds regularity, guarantees descent. Reinitialisation shifts the zero contour slightly. | Wegert et al., SMO 66:204; arXiv 2101.03286; GridapTopOpt arXiv 2405.10478 |
| Implicit VM on a background grid | Meßmer et al., CMAME 426:116999 (2024): Helmholtz/Sobolev filter on embedded boundary vertices, minimum-wall-thickness constraints, mesh-independent shape gradients. Structural. Closest match to "filtered smooth variables on a fixed grid". | TUM |
| Parametrised level sets | Wang & Wang, IJNME 65:2060-2090 (2006), RBF level set. | UTS |
| Scale | Stokes-flow narrow-band method with 5e7 design variables on 370^3. | arXiv 2508.04261 |

## 3. Remeshing vs mesh deformation, and noise

- Iteration noise is large and mesh/model dependent: Ahmed benchmark steady solvers, noise up to 22% on tets, much lower on hex/poly; SA under 1%; noise above 7% broke one objective in a metamodel study. Gilkeson et al., Comput. Fluids 94:84-97 (2014).
- Remesh noise itself is unquantified in what was found. Morphing is preferred for gradient methods.
- Morphing limits: RBF morphing handles large changes better than elasticity; quality degrades over many iterations (arXiv 2302.12100). Vendor guidance: morph the surface and remesh, not morph the volume (Simcenter blog).
- Coping: EUROGEN 2023 averages the last 3500 of 5500 iterations; BMW used constant step with a bound on shape update. No explicit trust-region-with-noise or GCI-style floor in car adjoint papers.
- Fixed-mesh alternatives (CutFEM/XFEM) only laminar or elastic. No RANS CutFEM car case.

## 4. Whole-vehicle adjoint literature

- Moving road and rotating wheels via boundary conditions in the EUROGEN DrivAer case; He et al. removed wheels and mirrors.
- NTUA multi-point car paper (SMO 2019) abstract-level.
- Racing: no open adjoint whole-FSAE-car paper. Closest: hybrid Kriging + Fluent-adjoint F1 front wing, 2D sections, 17 parameters (Machines 11(2):231); a 2026 adjoint full-car undertray paper (doi:10.1080/19942060.2026.2649519) abstract-level; a 2025 AIAA racing-wing adjoint paper (doi:10.2514/6.2025-0025) abstract-level.
- Experimentally validated: only Ahmed body (9.4%, He et al.), SUV mirror/air-dam (SAE 2020-01-0915, snippet), VW XL1 flow-control at 1:4 (Othmer 2014, snippet). No wind-tunnel validation of a whole-car downforce gain from adjoint shape optimisation found.

## 5. Derivative-free and surrogate baselines

| Method | Evidence | Source |
|---|---|---|
| DFO-LS / Py-BOBYQA | Restart-based noise robustness; DFBGN random subspaces. No budget for 100-1000 variables found. | arXiv 1804.00154 |
| Gradient-free scaling | Evaluation counts grow quadratically to cubically in variables; gradient-based two orders fewer. Snippet. | Lyu et al., ICCFD8 |
| Compact parameterisation | Gradient-free CRM wing under 1000 evaluations with compact modes. | AIAA J 2021 doi:10.2514/1.J059921 |
| CMA-ES | Near-adjoint results at roughly 2000-3000 evaluations. Unverified. | ShapeBench arXiv 2605.20763 |
| Bayesian optimisation | TuRBO, SAASBO (to 388 dimensions). No aero comparison. | arXiv 2103.00349 |
| Active subspaces | Othmer, Lukaczyk, Constantine, Alonso, AIAA 2016-4294. | doi:10.2514/6.2016-4294 |
| Neural surrogates | DrivAerNet++ (8000 designs), DrivAerML (500 variants, hybrid RANS-LES), AB-UPT, GeoTransolver conformal study 2026. No car shape optimisation validated through surrogate gradients. | arXiv 2406.09624, 2408.11969, 2502.09692, 2607.17297 |

Adjoint baseline: BMW about 10 h per primal and 2.5 h per adjoint response; He et al. 21 adjoint + 71 flow solves for 50 variables.

## Recommendation (agent synthesis)

Parameterisation: a normal-displacement control field on a coarse lattice or narrow band around the SDF zero set, lattice spacing about the filter radius (1e3-1e4 variables). Map through an implicit Helmholtz/Sobolev filter (Meßmer 2024); differentiate the filter in the adjoint chain (EUROGEN 2023); radius per component (adaptive VM), r at least 2-4 times surface mesh size and at least the minimum feature width.

Level-set update: bounded offset of the SDF per iteration (BMW: 10 mm updates, 5 mm constraint bound); Hilbertian extension-regularisation rather than frequent reinitialisation. Constraints: SDF union for components, intersection with an envelope SDF, sum-of-distances clearance, offset-based minimum thickness; aggregate many geometric constraints.

Remesh and noise: fix all mesh-generation settings; measure the objective SD by remeshing sub-cell shifts of identical geometry; require predicted gain per step to exceed a multiple of that SD; trust region.

Topology later: fixed topology first; then (a) body-fitted remeshing from phi (Dapogny-Feppon, laminar only) or (b) short density/porosity screen on a fixed grid, contour extraction, body-fitted RANS (Picelli pattern). No validated turbulent 3D car precedent.

Top 5 risks: (1) separated steady-RANS gives noisy, partly inconsistent adjoint gradients; (2) remesh noise may exceed per-step gain, unquantified; (3) the filter radius decides the answer (5.1% vs 14.7%); (4) constraints drive the result; (5) reported gains largely unvalidated, optimisers exploit RANS model error; turbulent topology change has no mature 3D precedent.
