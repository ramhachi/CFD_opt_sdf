# Brief E report: WaterLily-native, topology-free, GPU optimisation at moderate Re

(sonnet research agent, 2026-11-01, verbatim. Evidence key: R = primary page/PDF read; S = snippet or abstract only; U = unverified or the agent's inference.)

## 0. Findings that change the plan

1. **A candidate cause of the exponential tangent is in a public issue (R).** The QUICK scheme in WaterLily master is `quick(u,c,d)=median((5c+2d-u)/6, c, median(10c-9u, c, d))` (src/Flow.jl). Issue #358 (open, no fix merged) compares ForwardDiff with central differences on the spinning-cylinder test in Float64: with QUICK, ForwardDiff gives -13.5 at t=2 and -1.9e29 at t=4, against central differences of 0.43 and 0.45; with the `10c-9u` bound removed, ForwardDiff and central differences agree (0.4137 vs 0.4138; 0.4795 vs 0.4796); vanLeer and cds also agree; all schemes used the same pressure solver, so the issue's author rules the solver out. U: in a quiescent far field c=d=u, so the three median arguments tie and the tangent branch is set by round-off — matching growth "from a far-field corner" — not tested on the project's data. Cheap test: rerun the AD with `λ=cds`, `vanLeer` or bound-free QUICK (the `Flow` constructor takes λ, R, master). U: NEWS.md says the v1.10 limiter "no longer branches", so 1.8.0 does branch.
2. **The pressure-force integral does not close (R).** Issue #369 (open): a uniform pressure produces a spurious force that depends on where the surface cuts the cells and does not shrink with body size (off-grid circles R=8, 16, 32: error 8.5e-3, 2.7e-3, 2.9e-2 against a true value of 0; R=16 sphere 0.29). Issue #367: lift moves 1.4 % when p is offset by 1; mean p drifted from 0.10 to 0.25 over t=0.5 to 2.5. The flow is unchanged; only the force readout is affected. A placement-dependent noise source at roughly the 0.1-0.5 % level of the project's gains. The proposed fix defines `nds` as the telescoping change in mu_0 per cell (Metrics.jl, not merged, under review). Alternative: a momentum control-volume force (#293 reports mean drag about -8.4 % against the control volume).
3. **Released WaterLily lacks several features (R).** No wall model, no non-uniform/stretched grid, no AMR; MPI only as open PR #281.
4. **Thin bodies have no built-in remedy (R).** Body.jl uses eps=1 and has no minimum-thickness handling.
5. **Re transfer differs sharply between single- and multi-element wings (S).** See section 6.

## 1. Component-based (MMC-type) topology optimisation

| Item | Finding | Ev. |
|---|---|---|
| MMC, Guo/Zhang/Zhong, J. Appl. Mech. 81(8), 2014 (arXiv 1404.4820) | Each component has a topology description function with a large even exponent; components may overlap and a redundant one "disappears" by hiding inside another; a rectangular component has 5 variables (20 components = 100 variables); union by pointwise max. | R/U |
| Smooth union | Zhou et al., CMAME 310:1-32 (2016): KS aggregate of feature SDFs plus an approximate SDF to avoid grey regions. Norato et al., CMAME 293:306 (2015): geometry projection with bars whose out-of-plane thickness is penalised so they can vanish. | R/S |
| R-functions | Algebraic smooth union; min/max stays closer to a true distance; no TO use found. | S |
| Fluids | Yu et al., SMO 60:151 (2019), MMC for thermal-fluid Navier-Stokes. MMV for steady Navier-Stokes with closed B-spline voids and Brinkman penalty (CAMWA 2024). Hirotani et al., Mar 2026 (arXiv 2603.28137): walls 5 variables, fins 3, TDF projected by tanh, MMA with adjoints, small components deleted by size thresholds. | R/S |
| Aerodynamic multi-element use | None found. Closest: an MMC morphing-wing section optimised with evolutionary algorithms (SMO 2020). | S |
| Gradient-free variants and variable counts | Westra et al. (arXiv 2601.22241): MMC with 5 DoF per beam and curved MMC with 10, using DE, CMA-ES and HEBO at 10, 20 and 50 variables; budget 20 x D evaluations with 15 seeds; parameterisation mattered more than optimiser; MMC won at 10D, curved MMC at 20D and 50D; CMA-ES tied HEBO at 50D; infeasible designs rejected before simulation without costing budget. | R |

## 2. WaterLily.jl status (2026)

| Topic | Finding | Ev. |
|---|---|---|
| Latest release | v1.10.0 on 21 Oct 2026: fused/vectorised `conv_diff!`, `BDIM!`, `residual!`; Poisson default `tol` changed from 1e-4 to 2e-3 with a joint L1/Linf criterion; bodies can define `bbox`; WaterLilyNarrowBand.jl new; Metal supported; GPU vector interpolation 3-4x faster. | R |
| Speed-up vs 1.8.0 | RTX A2000 8 GB FP32: GPU TGV 128^3 1.42x; CPU 4-thread TGV 64^3 2.33x. | R |
| Since 1.8.0 | v1.9.0 Metal and a deforming-body source; v1.6.0 `RigidMap`; v1.9.2 fused force and moment integrals. | R |
| Multi-GPU / MPI | PR #281 (ImplicitGlobalGrid) open; scaling paper CPU-only (EPYC): weak scaling > 96 % to 1e9 cells; "ready for many-GPU" claimed without data (arXiv 2607.07687). | R |
| Throughput | H100 TGV: 1.57 ns per cell per step; MI250X about 2x slower; 226 M cells take 29 GB FP32 (~128 B/cell). No T4, A100, 4090 or 5090 numbers (CPC paper, arXiv 2407.16032). | R |
| Wall model, non-uniform grid, AMR | None. PR #291 (variable viscosity closure) open; PR #374 (`walls=` no-slip keyword) draft for v2.0. | R |
| Enzyme reverse, PR #285 | Open since 30 Apr 2026; full `sim_step!` reverse mode works on CPU and matches ForwardDiff; error ~10 % at default tol, 2.4e-5 at tol=1e-10; custom `poisson_solve!` adjoint rule; GPU reverse fails with `EnzymeNoDerivativeError` on `cuMemcpyHtoDAsync_v2`. | R |
| Issue #358 | Open, no merged fix (section 0). | R |
| Validation (CPC 2025) | TGV Re 1600 vs DNS; sphere Re 3700: CD 0.38 within 4 % of DNS and 7 % of LES; oscillating cylinder Re 7620 within 3 %; no airfoil or flapping-foil validation at Re 1e4-1e5 found; a 2D tandem-airfoil AD example exists (WaterLily-Examples). | R/S |

## 3. Tangents and adjoints that blow up while the primal converges

| Item | Finding | Ev. |
|---|---|---|
| General cause | Hueckelheim et al. (arXiv 2305.07546): iterative solvers can converge for the primal but break down for the derivative; differentiating through a fixed-point loop ties accuracy to the initial guess and stopping rule; remedy is to treat the process as an implicit function with its own derivative iteration. | R |
| Christianson 1994 | Optim. Methods Softw. 3:311-326: the adjoint iteration converges at least as fast as the primal, memory independent of iteration count. | S |
| RPM | Campobasso & Giles, AIAA J. 42(9):1765 (2004); Skamagkis et al., IJNMF 2021; Albring, Dick & Gauger, AIAA 2017-3664 (record only). | S |
| Unsteadiness | Krakos & Darmofal, AIAA J. 48(11) (2010); Padway & Mavriplis (arXiv 2104.02826): linearisation accuracy depends on convergence of the nonlinear solve. | S/R |
| Segregated solvers | Fang & He, JCP 2024 (10.1016/j.jcp.2024.112860): rewrite the segregated solver as a left-preconditioned Richardson iteration and transpose it. | S |
| Newton-Krylov on a time-stepper map | Established for steady states and bifurcations (Tuckerman & Barkley 2000; Kelley et al.); a Newton-Krylov adjoint exists for turbomachinery (AIAA J. 2021); no published adjoint of a projection or BDIM code built this way. | S |
| Poisson solve | SPD, so the adjoint reuses the same solve (PR #285 does this); a JAX-CFD direct-forcing IB reports a similar trick (arXiv 2403.06257). | R/S |
| Chaotic case | NILSS cost scales with the number of positive Lyapunov exponents; LSS on a ~10k-DoF LES already needed large memory and time; U: wing iLES at Re_c 1e3-1e4 has extensive chaos, judged intractable. | S/U |

Newton-Krylov is a known route only where a steady state exists and is reached; not a drop-in fix for an unsteady iLES.

## 4. Gradient-free and reduced-basis optimisation with noise (20-60 variables)

| Method | Evidence | Ev. |
|---|---|---|
| CMA-ES | Default lambda = 4 + floor(3 ln n) (14 at n=30); covariance learning rates ~2/n^2 and mu_eff/n^2, time horizon ~n^2/mu_eff generations (Hansen tutorial arXiv 1604.00772); U: roughly 1e3-1e4 evaluations at n~40; larger population gives noise robustness (Hansen 2009). | R/S/U |
| DFO-LS, Py-BOBYQA | Restarts are a cheap and effective noise remedy and beat sample averaging (arXiv 1804.00154). | S |
| TuRBO | 14D at 10k evaluations, 60D at 20k, 200D at 10k, batches of 50-100; CMA-ES and BOBYQA runners-up (arXiv 1910.01739). Budgets far exceed a Kaggle quota. | R |
| SPSA and FD with CRN | CRN raises the FDSA rate from k^-1/3 to k^-1/2; SPSA gain smaller (Kleinman et al. 1999). BO with CRN: Pearce et al., Oper. Res. 2022. | S |
| Aero examples | Plaban et al. (arXiv 2505.09088): Nelder-Mead, COBYLA, BO vs L-BFGS-B, SLSQP, up to 32 FFD variables; not noisy iLES. Lyu/Yu/Martins (2018): wing design spaces effectively unimodal. | R/S |
| Reduced bases | Active subspaces for airfoils (arXiv 1702.02909); survey arXiv 2405.13944; Laplace-Beltrami leading eigenfunctions as an optimal smooth subspace (Aflalo et al.); no FD-in-LB aero study found. | S |
| Placement noise | #369 and #367 (section 0). | R |

## 5. Thin bodies on a uniform Cartesian IB grid

- Lauber, Weymouth & Limbert, JCP 457:111076 (2022), read (arXiv 2110.06535): classic BDIM needs thickness >= (4 + sqrt N) dx, about 5.4 dx in 2D (5.7 dx in 3D); leaks when d/dx < ~4; at d = 2 dx the peak-force error exceeds 20 %. BDIM-sigma offsets the SDF as s = s_sigma - max(d/2, C1 dx), C1 = 1/2 + sqrt(N)/2; minimum thickness (1 + sqrt N) dx, about 2.4 dx in 2D and 2.7 dx in 3D. Disk at Re 1.25e5 with d/dx = 4: peak force within 3.2 % of experiment; oscillating shell second-order convergence; elliptical plate wing at Re 100, thickness ~2.7 cells: 2.7 % error, converging as O((d/D)^1.55). No airfoil case, no cells-per-chord guidance.
- WaterLily implementation: ParametricBodies has a `thk` option and does not mention BDIM-sigma. U: the sigma offset and Lauber's kernel convention may not map onto WaterLily's eps=1; by analogy the classic floor with eps=1 is about (2 + sqrt N) dx. Consequence: elements with t/c below ~0.1 at 32 cells per chord are sub-floor.
- Resolution evidence: the Re 3700 sphere needed 88-168 cells per diameter, with only ~3 cells in the boundary layer (CPC paper).
- Alternatives: sharp-interface IB with two-sided forcing for arbitrary thickness (Vagnoli et al., Jun 2026, arXiv 2606.09799, abstract only); Oceananigans `PartialCellBottom` / `GridFittedBoundary` (bathymetry-style, no thin-body evidence).

## 6. Re transfer

| Evidence | Finding | Ev. |
|---|---|---|
| Zhdanko & Kolomenskiy, arXiv 2605.19468 | Re 1-3000, Joukowski family: zero-thickness cambered airfoils optimal; optimal camber peaks near Re 40-50 then declines; optimal incidence falls with Re; optimum sharply peaked at Re >~ 1000. | R (abstract) |
| Winslow et al., J. Aircraft 55(3):1050 (2018) | At Re 1e4-1e5 lift and drag not constant below 1e6; cambered plates beat thick rounded-LE sections below 1e5. Selig: sharp Cl,max drop from 1e6 to 1e5. | S |
| Roberts, Finnis & Knowles, J. Fluids Eng. 2016 | Single-element wing in ground effect: downforce changed up to 320 % and drag 35 % over delta Re_c 0.81e5; the multi-element wing and the F1 wing changed by under 6 %; the laminar separation bubble moves upstream and grows at lower Re and lower clearance. | S |
| Gap and overlap optima | NASA flap tests (high Re): gap/overlap optima shift with Re, sensitivity grows with element count; no optimum gap at Re 1e4-1e5 found. | S |
| Persistence of optimal topology | No direct study found. | none |
| Benchmark anchor | LES of a multi-element inverted wing at Re 2.2e5, h/c 0.36: Cl ~ -8.33, Cd ~ 0.17 (Flow Turbul. Combust. 2023). | S |

## 7. GPU options and cost (2026)

| Option | Figure | Ev. |
|---|---|---|
| Kaggle | ~30 h/week GPU commonly cited, no official number; sessions 12 h (older sources 9 h); T4x2 or P100; Colab Pro/Pro+ linking may add 15/30 h. | S |
| Colab Pro | $9.99 for 100 units; Pro+ $49.99 for 500 units; T4 ~1.2-1.8 units/h, A100 ~12-15 units/h. | S |
| RunPod (28 Oct 2026, Secure / Community per hour) | A100 80GB SXM $1.79 / $1.39; H100 SXM $3.99 / $2.69; RTX 4090 $0.89 / $0.34; RTX 5090 $1.19 / $0.69; L40S $1.09 / $0.79. | R |
| RTX 5090 purchase | MSRP $1,999; October street price about $4.3k-7.5k, scarce. | S |
| Other rentals | Vast.ai A100 SXM 80GB from $1.17/h; CoreWeave spot ~$1.21/h (Jul 2026). | S |
| Apple and AMD | Metal since v1.9.0, Float32 only; AMDGPU supported; no published Metal throughput. | R |

U, derived: scaling the H100 figure by memory bandwidth gives ~16 ns per cell-step on a T4, 5 ns on a 4090, 3 ns on a 5090, 2.6 ns on an A100; cost per 1e12 cell-steps roughly $0.5-1.2 across GPUs; measure before relying on it. Memory ~128 B/cell: ~115 M cells on a T4, 180 M on a 4090, 240 M on a 5090, 600 M on an 80 GB card.

## One-page recommendation (agent)

Representation: 4-5 analytic element slots plus fixed mesh SDFs (via WaterLilyNarrowBand); ~6 variables per element (position 2, chord, incidence, camber, thickness ratio) = 24-30 variables, plus 2-3 per element for spanwise twist or taper; union by min of SDFs (exact outside the union, no smoothing needed without AD; KS plus approximate SDF only if differentiating through the geometry).
Topology rules: a zero-cost geometry gate before any CFD (rejected designs outside the budget count, as Westra et al.): thickness at or above the BDIM floor (or implement BDIM-sigma); inter-element gap >= ~4 cells; overlaps forbidden or merged by explicit rule. Treat element count as an outer discrete loop N = 1..N_max, warm-started by splitting. Do not rely on continuous vanishing: a plate cannot shrink away smoothly because the thickness floor keeps it blocking until chord is a few cells; the MMC "hide inside another component" rule works only when parked inside a solid.
Optimiser: (1) screen in a reduced basis of 10-15 modes with separable/diagonal CMA-ES or DE at 20-50 x D evaluations; (2) polish with Py-BOBYQA with restarts and paired CRN evaluations; (3) FD gradients only in the top modes at steps above the noise floor; TuRBO only with 8+ GPUs; use Kaggle's two T4s as one CRN pair per session.
Re ladder: Re_c 1e3 for screening; 3e3-1e4 for ranking; a WaterLily probe at 3e4-1e5 as an unvalidated trend check only; OpenFOAM primal verifier at 2e5-5e5 with a transition-capable model; predeclare ranking-retention metrics and an N-ablation.
Engineering fixes first: replace or patch the force readout (#369) or use a control-volume force; pin the Poisson tol; test the QUICK lambda swap in the AD run; decide deliberately whether to leave the 1.8.0 pin (v1.10 changes the default tol and the `mom_project!` API).

Top 5 risks: (1) Re transfer (optima at Re_c 1e3-1e4 may not persist at 2e5-5e5; single-element especially Re-sensitive; no direct evidence); (2) force artefacts at the gain scale (sub-floor thickness plus the non-closing force integral give placement-dependent errors comparable to 0.1-0.5 % differences; the optimiser could chase artefacts); (3) budget versus noise (1e3-1e4 noisy evaluations at 30-60 variables vs ~30 h/week; reduced basis and Re ladder mandatory); (4) blocked or fragile AD and no scaling path (QUICK-limiter pathology #358 open, Enzyme GPU reverse fails, no multi-GPU/wall model/non-uniform grid in releases, a 1.10 upgrade changes defaults); (5) verification and discontinuities (element merging or gap closure makes the objective discontinuous and can stall DFO; the sharp optimum can sit on a geometry constraint; OpenFOAM verification covers only top-k designs, so selection bias against a 0.5 % margin remains).
