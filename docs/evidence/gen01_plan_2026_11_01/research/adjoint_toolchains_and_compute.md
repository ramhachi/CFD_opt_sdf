# Brief A report: adjoint toolchains and compute

(sonnet research agent, 2026-11-01, verbatim; [unv] = snippet/aggregator only; [derived] = agent arithmetic)

Correction note from the agent: several search-tool summaries were wrong when checked against the paper. Primary PDFs read: DAFoam (S3, S4), OHC-1 (S30), SPUMA (S31), Economon (S15), Karpouzas (S9), ESI manual and slides (S6, S7).

## 1. Status of open-source adjoint RANS toolchains (2024-2026)

| Tool | Status and facts | Fit and issues |
|---|---|---|
| DAFoam (discrete adjoint on OpenFOAM) | v5.0.0 announced 05 May 2026 [S1]; compatible with OpenFOAM v2506, moved to the OpenFOAM-AD fork; release notes: "forward-mode AD is unreliable; verify with check_totals" [S2]; v5.1.1 current docs; Docker images linked [S1]. 2020 paper: SA, k-eps, realizable k-eps, SST, SST-LM adjoints on incompressible simpleDAFoam, wall functions at y+~33 [S3]. | Gradients consistent with the primal. Cost at 10.1M cells: adjoint/flow runtime 1.7-2.2 on 192-1536 cores, but adjoint memory 1146 GB vs 73 GB for the flow solve [S3]; 2018 paper 886 GB vs 25 GB at 10M [S4]. Automotive: DrivAer rear end, 1M cells, y+~46, 50 FFD variables, drag 0.140->0.123 (-12.1 %), 21 adjoints and 71 flows, 58 h on 32 cores [S4]. No published DAFoam whole-vehicle case at 20-50M cells. No GPU path. |
| OpenFOAM ESI adjointOptimisationFoam (continuous) | v1906 SA; v2206 adjoint k-omega SST; v2312 topology optimisation [S6]. v2506 and v2512 release notes mention no adjoint changes [S5]. Manual covers up to v2406 [S7]. | Incompressible simple solvers only [S7]. "Adjoint wall function" only with nutUSpaldingWallFunction; SST path uses kqRWallFunction/omegaWallFunction [S7]. SST adjoint header cites Kavvadias 2015 and notes distance (eikonal) sensitivities are zero [S8]; SA adjoint eikonal optional (includeDistance) [S7]. Automotive: motorBike tutorial, Toyota concept car (SMO 59(2), 2019, SA-WF), DrivAer rear spoiler [S6, S9]. NTUA slides: URANS-adjoint drag cases 5.3M, 16.6M, 37.3M cells, 10k-40k time steps, 132-960 cores, -5.7 to -7.4 % drag [S6]. |
| ESI stability | Manual: the ATC term "is numerically stiff and can often cause convergence difficulties" [S7]; options ATCModel (standard, UaGradU, cancel), extraConvection, zeroATCPatchTypes, nSmooth; primal averaging for limit-cycle flows [S7]. | User reports: divergence after a few thousand iterations from continuity error; floating-point exception in the second cycle [S12]. Kuehl 2025 (arXiv 2501.12518) calls ATC "often instability-inducing" and proposes elliptic relaxation trading consistency for robustness [S11]. Consistent with the SIGFPE; no report of the exact failure found. |
| SU2 v8.x (discrete adjoint, CoDiPack) | v8.6.0 (30 Oct 2026) [S13]: CUDA compatible with the discrete adjoint, new pressure-based incompressible solver, SA wall-function divergence fix. v8.5.0: FGCRODR replaces GMRES for Newton-Krylov adjoints. v8.3.0: sign error and derivative term fixed in the incompressible Spalding wall function. v8.0.0: SST-2003m default. | Hybrid MPI+OpenMP adjoint to 768 cores on an 18M-cell HL-CRM, 2.4x less memory than MPI-only (compressible SA) [S14]. Memory about 10x primal (forum, anecdotal) [S16]. No peer-reviewed SU2 vehicle study at scale; Ahmed body 508k elements, y+~1 [S15]. |
| Kratos ShapeOptimization | node-based vertex morphing [S17]; no RANS adjoint pairing found [unv]. | not a candidate |
| Commercial | STAR-CCM+: frozen turbulence default for k-eps, k-omega, RSM; only SA has a turbulence adjoint; user reports divergence on a race car; first-order is the robust fallback, release 2502 improved second order [S18]. Fluent: frozen turbulence by default; Transition SST not adjoint-compatible [S19]. Vendor: DrivAer adjoint morphing -13 counts [S20]. | benchmarks only |

## 2. Robustness of steady RANS adjoint in separated or weakly unsteady flow

| Evidence | Finding |
|---|---|
| Krakos & Darmofal, AIAA J 48(11), 2010 [S21] | If the primal does not converge steady, adjoint sensitivities depend on which unconverged state is linearised and can be badly wrong even for small output unsteadiness. Output windowing proposed. |
| Wang, FUN3D white paper 2015 [S22]; Blonigan et al., CTR 2016 [S23] | Chaotic flows: transient tangent/adjoint grows with the positive Lyapunov exponent (matches the WaterLily result). LSS fixes it but costs more than the primal; a 2D airfoil with ~10K DoF already needed large memory and wall time; NILSS scales with the number of positive exponents. Not practical for 3D RANS-scale vehicles [derived]. |
| Windowing in SU2, arXiv 2412.00604 [S24] | Windowed URANS sensitivities; adjoint matches forward mode to 0.03-1.9 %; square window drifts; at Re 1e6 the sensitivity amplitude still grows exponentially. |
| Skamagkis, Papoutsis-Kiachagias, Giannakoglou, IJNMF 2021 [S10] | Recursive projection method (RPM; Campobasso & Giles 2004 [S26]) on primal and adjoint plus controlled ATC damping; motorbike fairing; unsteady re-evaluation showed a reduced time-averaged objective. |
| Karpouzas et al. 2016 [S9] | Upwind plus near-wall ATC masking stabilises but loses accuracy; cell-by-cell ATC damping where diagonal dominance would be lost. Steady adjoint on a time-averaged DES flow gave different rear-spoiler sensitivities than RANS, and the DES result matched a vehicle test (Audi A7). |
| Margetis et al., IJNMF 2023 [S29] | Unsteady adjoint with checkpointing plus lossy compression in OpenFOAM [unv]. |
| Industry practice | Sensitivity maps from one steady adjoint guide morphing in small steps (2 mm per step plus a tanh filter) [S9]; ESI loops usually finish in under 20 cycles [S6]. |
| Not found | Pseudo-transient adjoint as a named method. |

## 3. Discrete vs continuous adjoint accuracy; mesh sensitivity

| Evidence | Agreement |
|---|---|
| DAFoam, ADODG case 102,912 cells [S3] | discrete adjoint vs FD: 0.002-0.195 % over solvers and models (SST 0.010 % incompressible) |
| DAFoam, DrivAer with poor flow convergence [S4] | error 0.76 % on one derivative; optimizer needed more flow solves; "poor flow convergence is one of the most challenging issues" |
| SU2, Ahmed body, SA, coarse mesh [S15] | continuous surface-integral adjoint with frozen turbulence can be an order of magnitude off AD and FD; field-integral form tracks better; including mesh differentiation matters more than an adjoint turbulence model |
| Frozen turbulence [S25, S27, S28] | Dwight & Brezillon 2006 studied approximate discrete adjoints incl. constant eddy viscosity; Tsiakas 2024: frozen turbulence should not be assumed; Schramm 2018 compared for airfoils; numbers not obtained |
| ESI enhanced surface integrals | grid sensitivity handled through the ESI formulation [S6, S7]; Kavvadias et al., JCP 301 (2015) [unv] |

Design implication [derived]: discrete adjoint gradients are exact only on a fixed-topology mesh that is deformed. Re-meshing from the SDF every iteration breaks that consistency. NTUA topology slides: re-evaluating the optimised geometry on a body-fitted snappyHexMesh gave a uniformity objective of 898 vs 541 and 873 vs 354 [S6].

## 4. GPU RANS and cloud cost

GPU: OHC-1 (arXiv 2603.27565): 237 data points on DrivAer 65M/110M/236M cells, SST, OpenFOAM v2412 [S30]; full GPU ports 58 vs 14 MFVOPS per node, about 10-15x fewer nodes; practical strong-scaling limit about 10k cells per core, most submissions 100k-1M cells per core. SPUMA (arXiv 2512.22215, Dec 2025): A100 ~ 200-300 Sapphire Rapids cores above 10M cells per GPU; at 236M cells SIMPLE iteration 1.53-1.70 s on 20 A100 vs 4.79 s on 1600 CPU cores [S31]; forward-only. Hybrid AmgX/PETSc offload modest [unv]. No official NVIDIA OpenFOAM product found. SU2: CUDA FGMRES, ILU, LU-SGS; v8.6.0 adjoint compatibility [S13].

Cloud prices (on-demand Linux; aggregators [unv]):

| Instance | Cores | $/h | $/core-h |
|---|---|---|---|
| AWS hpc7a.96xlarge (us-east-2) | 192 (768 GiB) | 7.20 (Vantage 9.08) | 0.038 |
| AWS hpc8a.96xlarge | 192 (768 GiB) | 7.92; up to 40 % faster than hpc7a | 0.041 |
| AWS hpc6a.48xlarge | 96 (384 GiB) | 2.88 | 0.030 |
| AWS hpc7g.16xlarge | 64 (128 GiB) | 1.68 | 0.026 |
| Azure HB176rs_v4 (East US) | 176 | 7.20 (spot ~1.33) | 0.041 |
| GCP h3-standard-88 | 88 | 4.92-5.97 (spot ~2.5-2.7) | 0.056-0.068 |
| Rescale | n/a | 0.25/core-h HPC+ (undated) | 0.25 |

Azure HBv5 (GA Nov 2025) advertised 4.8x HBv4 on a 100M-cell motorbike case (vendor).

Wall-clock and cost 20-50M cells [derived]: from SPUMA CPU table, OpenFOAM ~25 core-seconds per million cells per SIMPLE iteration (Sapphire Rapids, DrivAer simpleFoam). 30M x 2000 it ~ 420 core-h ~ $16 on hpc7a; 50M x 3000 ~ 1040 core-h ~ $40. At 50k cells per core, 30M runs on 600 cores in ~0.7 h. A DAFoam adjoint at 113 kB per cell [S3] extrapolates to ~3.4 TB at 30M and 5.6 TB at 50M (5-8 hpc7a nodes for memory; extrapolation). A DrivAer-style campaign (71 flows, 21 adjoints) ~ 113 flow-equivalents; at 30M ~ 47k core-h ~ $2k. Compute dollars are not binding; memory and robustness are.

## 5. Immersed boundary and cut-cell alternatives

| Option | Gradient availability |
|---|---|
| Cart3D (cut-cell Euler) | discrete adjoint on embedded-boundary Cartesian meshes [S39]; inviscid; viscous cut-cell RANS with wall functions in research form [S40], no adjoint |
| OpenFOAM / commercial IB | 2025 IB + k-omega wall functions on Cartesian grids is 2D [S41]; no differentiable IB wall-function RANS; Converge/Simcenter cut-cell adjoint: nothing |
| LBM | adjoint LBM on a 3D car at 130 km/h, AIAA J 2019 [S38]; LES-adjoint gradients blow up (ECCOMAS 2022, secondhand); AD adjoint LBM with LES in OpenLB at Re 3900 only; PowerFLOW/waLBerla no adjoint [unv] |
| Flow360 | GPU RANS, DrivAer ~10 min on 48 A100 (vendor); optimisation product not described as adjoint [S37] |

None gives production-grade gradients for high-Re wall-bounded vehicle flow.

## Recommendation (agent)
1. DAFoam v5 primary: discrete-consistent SA/SST with wall functions, adjoint 1-2x primal; memory the limit (plan 5-8 hpc7a-class nodes for 30-50M); IDWarp-style deformation between re-meshes with a surface-point Jacobian to the SDF nodes; direct node-based parameterisation not documented [unv].
2. SU2 v8.6 discrete adjoint as cross-check/fallback (FGCRODR, hybrid MPI+OpenMP, GPU linear solver; incompressible wall-function adjoint recent; snappyHexMesh to SU2 conversion needed).
3. ESI adjointOptimisationFoam for sensitivity maps and small-step morphing (least memory, native snappy meshes; continuous adjoint not consistent with the discrete primal; ATC settings needed).
4. Commercial only as benchmarks. 5. IB, cut-cell, LBM not recommended.

## Top 5 risks
1. Adjoint divergence/non-convergence in separated or weakly unsteady flow [S9, S10, S12, S21, S22]; mitigations averaged primal, RPM, ATC damping, first-order fallback, windowed objectives.
2. Memory at 20-50M cells (DAFoam ~113 kB/cell at 10M [S3]; SU2 ~10x primal anecdotal).
3. Gradient inconsistency from re-meshing each iteration; topology change breaks the discrete adjoint [S6, S15].
4. Model validity at Re 4.6e5 (transitional, laminar separation) vs fully turbulent SA/SST-WF [inference]; frozen turbulence degrades gradients.
5. Toolchain maturity: DAFoam v5 moved to OpenFOAM-AD in 2026 with a "forward AD unreliable" note; SU2 wall-function adjoint bugs fixed 2025-26; ESI SST adjoint neglects distance sensitivities; no open-source adjoint on a 20-50M-cell whole vehicle documented.

## Sources (accessed 2026-11-01)
S1 https://dafoam.github.io/index.html; S2 https://github.com/mdolab/dafoam/releases (v5.0.0); S3 He, Mader, Martins, Maki, AIAA J 58(3) 2020 doi 10.2514/1.J058853; S4 He et al., Comput. Fluids 168 (2018) 285-303 doi 10.1016/j.compfluid.2018.04.012; S5 openfoam.com v2512/v2506 release notes; S6 Papoutsis-Kiachagias NTUA/ESI training slides (events.grnet.gr); S7 adjointOptimisationFoamManual_v2312.pdf; S8 api.openfoam.com/2512 adjointkOmegaSST.H; Kavvadias et al., Eng. Optim. 47(11) 2015 doi 10.1080/0305215X.2014.979816; S9 Karpouzas et al., Int. J. Automotive Eng. 7(1) 2016 (zenodo 808434); S10 Skamagkis et al., IJNMF 2021 doi 10.1002/fld.4993; S11 Kuehl arXiv 2501.12518; S12 cfd-online threads 240144, 254036; S13 github.com/su2code/SU2/releases; S14 Bluehdorn et al., Comput. Fluids 289 (2025) 106528, arXiv 2405.06056; S15 Economon et al., AIAA 2017-4363; S16 cfd-online su2 237979; S17 pypi KratosShapeOptimizationApplication; S18 Siemens docs/blog, cfd-online star-ccm 201745; S19 Ansys Fluent adjoint usage v261; S20 pdsvision blog; S21 Krakos & Darmofal AIAA J 48(11) 2010 doi 10.2514/1.J050412; S22 fun3d qiqi_doe_whitepaper_2015; S23 Blonigan et al. CTR 2016 arXiv 1702.06809; S24 arXiv 2412.00604; S25 Dwight & Brezillon AIAA J 44(12) 2006 doi 10.2514/1.21744; S26 Campobasso & Giles AIAA J 42(9) 2004 doi 10.2514/1.1225; S27 Tsiakas et al., Fluids 9(4) 2024 doi 10.3390/fluids9040087; S28 Schramm et al., Computation 6(1):5 2018; S29 Margetis et al. IJNMF 2023 [unv]; S30 Lesnik, Olenik, Wassermann arXiv 2603.27565; S31 Bna et al. SPUMA arXiv 2512.22215; S32 AWS instance docs; devzero, vantage, sparecores; S33 azurespeed, sparecores; S34 sparecores, holori; S35 Microsoft tech community, signal65; S36 rescale blog; S37 flexcompute blog; S38 AIAA J 2019 doi 10.2514/1.j057955; S39 NAS-06-007, JCP 2008; S40 AIAA 2012-1301; S41 doi 10.1080/19942060.2025.2486657
