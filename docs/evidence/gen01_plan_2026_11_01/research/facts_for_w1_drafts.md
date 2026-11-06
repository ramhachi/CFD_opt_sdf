# Brief F report: facts for TOPO-2D-00 / TR-00, FORCE-00, GRAD-00, LOCAL-GPU-01

(sonnet research agent, 2026-11-01, verbatim. Tags: [R] primary text read; [W] WebFetch summary; [S] snippet only. Blocked: WashU thesis, core.ac.uk, Springer, TU Delft PDF, Semantic Scholar. One search refused by the classifier (Jasinski & Selig).)

## 1. Zhang & Zerihan double-element wing

Sources: AIAA J. 41(6):1007-1016, open PDF [R] https://eprints.soton.ac.uk/id/eprint/22605/1/AIAA-2057-653.pdf ; Zerihan PhD thesis 2001 (OCR text, Tables 2-4 are coordinate tables) [R] https://eprints.soton.ac.uk/426058/1/00192634.pdf

| Item | Fact |
|---|---|
| Main element | 80 %-scale copy of the 1998 Tyrrell 026 main element, derived from NASA GA(W) LS(1)-0413 MOD (thesis §2.2.1); "modified GAW". Chord 223.4 mm, span 1100 mm, constant chord, TE thickness 1.65 mm (0.007c). |
| Flap | Constant chord 165.7 mm; the aft ~35 mm is a 1 mm-thick region; the car's centre-span flap scaled 80 %. |
| Combined chord | 378.9 mm (datum flap), 381.5 mm (-8.5 deg). All double-element results normalised by c = 380 mm; AR 2.89. Endplates 400x170x4 mm. |
| Coordinates | Thesis Table 2 (single element), Table 3 (main element at the 14.1 deg reference attitude), Table 4 (flap); tabulated text (check OCR against figures). |
| Overlap and gap | Overlap = horizontal distance from main TE to flap LE, positive when the flap LE is upstream of the main TE. Gap = vertical distance from main TE to the lowest point of the flap suction surface, positive when the flap LE is above the main TE. |
| Values | Optimum found at h/c = 0.263, datum flap, 2 mm steps: overlap 0.024c (9 mm), gap 0.032c (12 mm), used for all flap angles; the thesis admits the gap is probably too large for the low flap. |
| Flap angles | Datum ("high"), -8.5 deg ("low"), +9.5 deg (forces only; flap stalled). Rotation point x/c = 0.567, y/c = 0.076. |
| Incidence | "1 deg" on the inclinometer = endplates parallel to the ground; true incidence of the main-LE to flap-TE line 14.1 deg at datum. |
| Re (30 m/s, q = 56.25 mm H2O) | Single element 0.430-0.462e6 on 223.4 mm; double element 0.735-0.765e6 on 380 mm. |
| Transition | Double element: free only. Single element: free and tripped (strips at x/c = 0.1, length < 0.015c; 100 grit final). |
| Heights | h/c from 1.97 to < 0.05; h = ground to the lowest point of the wing at 0 deg incidence, +-0.2 mm. Uncertainties CL +-0.003, CD +-0.0006. |

Measured forces (balance on the 3D wing with endplates): single element alpha = 1 deg: CL 0.69 freestream, 0.84 at h/c 0.671, peak 1.72 at 0.082, tripped peak 1.39 at 0.112; centre-section Cl from integrated pressures 1.286 at h/c 0.224 and 1.385 at 0.134 (thesis Table 15). Double element: low flap peak CL 2.588 at h/c 0.066 (slope discontinuity 0.171); high (datum) peak 3.028 at 0.079 (discontinuity 0.237); below the peak downforce falls sharply; PIV shows main-element TE separation for the high flap at h/c 0.058 and 0.066. Gap: the double-element CL at h/c 0.224 is figure-only (paper Fig. 5a, thesis Fig. 36b); the double-element set is 0.395/0.263/0.211/0.158/0.105 plus PIV heights.

Later CFD: Zerihan thesis ch. 9 [R]: 2D CFL3D, single element, S-A and Menter k-omega; 5-block structured grid 25-30k points, y+ ~ 1, boundaries 8c up/downstream and 7c above, new grid per height, ground via prescribed-velocity BC; Cl over-predicted: S-A +15-17 % over most heights (+12 % at 0.090); k-omega +14 % (freestream) to +5 % at 0.224 and -5 % at 0.090; at h/c 0.224 experiment 1.286, S-A 1.475, k-omega 1.352; "for trends"; fixed-transition run "problematic". Heyder-Bruckner PhD (Southampton), 3D double-element [R, grepped] https://eprints.soton.ac.uk/207263/1/Jacques_Heyder-Bruckner_-_PhD_Thesis.pdf : steady RANS (S-A) and DES, ~4M cells isolated wing; 2M and 8.7M at h/c 0.246; downforce under-predicted ~7 % in region a; at the low end of region c RANS +2 %, DES -3 %; drag over-predicted ~6 %; DES shows a sharp fall at 0.063 not in experiment; wrong transition modelling suspected. Mahon & Zhang: J. Fluids Eng. 127(2) 2005 single element (SST, realizable k-eps); J. Fluids Eng. 128(6):1172-1180 (2006), doi 10.1115/1.2353268, inverted double element, RANS with six models, realizable k-eps best [S]. Kachare (GVSU 2017) [W]: 3D RANS of a multi-element F1 wing, SST better at low clearance. No "Genua 2009" double-element paper found.

Three-element ground-effect data: no 2D three-element moving-belt force dataset found. Closest: Imperial Front Wing (3-element plus endplate and nose, 3D, rolling road, h/c 0.36, Re 2.2e5) [R] arXiv 1909.06701; Pegrum thesis (PIV, total pressure; forces not confirmed); 2026 volumetric PTV paper Re 74,896 [W]. Fixed-ground multi-element work cited in 2003: Ranzenbach et al. (2D double), Jasinski & Selig (3D). 30P30N in ground effect is CFD-only [S].

## 2. WaterLily.jl v1.8.0 [R, raw at tag]

src/Flow.jl (the only three schemes; `median` still branches in 1.8.0):
```
@fastmath quick(u,c,d) = median((5c+2d-u)/6,c,median(10c-9u,c,d))
@fastmath vanLeer(u,c,d) = (c<=min(u,d) || c>=max(u,d)) ? c : c+(d-c)*(c-u)/(d-u)
@fastmath cds(u,c,d) = (c+d)/2
function Flow(N::NTuple{D}, uBC; mem=Array, dt=0.25, nu=0., g=nothing, u0=nothing, ulambda=nothing, perdir=(), exitBC=false, lambda=quick, T=Float32) where D
```
`ulambda` is a deprecated alias of `u0` (#303). src/WaterLily.jl: `Simulation(dims::NTuple, uBC, L::Number; U=nothing, dt=0.25, nu=0., eps=1, g=nothing, u0=nothing, perdir=(), exitBC=false, lambda=quick, body::AbstractBody=NoBody(), T=Float32, mem=Array, flow_ctor=..., pois_ctor=...)`.

src/Metrics.jl (no `∮nds`, no `total_force_and_moment` in 1.8.0):
```
@inline function nds(body,x::AbstractVector{T},t) where T
    d,n,_ = measure(body,x,t,fastd2=one(T))
    n*WaterLily.kern(clamp(d,-1,1))
end
@loop df[I,:] .= p[I]*nds(body,loc(0,I,Tp),t) over I in inside(p)            # pressure_force
@loop df[I,:] .= -2nu*S(I,u)*nds(body,loc(0,I,Tu),t) over I in inside_u(u)   # viscous_force
total_force(sim) = pressure_force(sim) .+ viscous_force(sim)
```
`nds` uses kern(d) = (1+cospi(d))/2, a fixed +-1-cell kernel that ignores eps, evaluated at cell centres. Sums in promote_type(Float64,Tp); from v1.9.2 in the field type. `nds` unchanged in v1.9.2 and v1.10.0.

src/AutoBody.jl and src/Body.jl: `struct AutoBody{F1,F2} <: AbstractBody; sdf::F1; map::F2; end`; `AutoBody(sdf, map=(x,t)->x)`; no `compose` keyword (gone by v1.7.0); the map is always composed. `measure` takes the SDF gradient by AD, normalises d by the gradient magnitude, NaN-safe zeros at kinks. `+` or union of bodies is `SetBody(min,...)`. 2D setup per README with +2 ghost cells. measure!: `a.V .= 0; a.mu0 .= 1; a.mu1 .= 0; d2=T(2+eps)^2; if d[I]^2<d2 (band: per-face d_i; d_i = abs(d_i) <= 0.5 ? d_i : copysign(d_i,d[I]); mu0[I,i]=mu0(d_i,eps)) elseif d[I]<0 mu0[I,i] = 0`; `mu0(d,eps) = d/eps < -1+sqrt(eps(d)) ? 0 : kern0(min(d/eps,1))`. So mu0 is 0 at d <= -eps and 1 at d >= eps; default eps = 1.

## 3. Issues #369 and #367 [R via GitHub API]

#369 "The force integral does not close: a uniform pressure gives a force on a body", open, 2026-10-19 (timesselens), no PR or release. Reproducer: unit pressure on an off-grid circle gives (8.5e-3, 2.7e-3, 2.9e-2) for R = 8, 16, 32; off-grid sphere R = 16 gives 0.29 (true 0). Proposed fix: `nds = sum_i e_i (mu0[I+delta(i,I),i] - mu0[I,i])`, telescoping along each grid line; closure < 1e-15 (circle), 1.4e-14 (sphere); flow bitwise identical in 14 runs; the first version used the SDF distance (13 % error when the SDF is not a true distance), the branch now reads mu0 stored by measure!; branch `poc-force-integral` on timesselens/WaterLily.jl (fork, not a PR), adds a `Measured` wrapper and `Adapt`. Maintainer weymouth prefers passing mu0 through the force-function signatures; it changes every force and moment slightly; no rush. Viscous-force note for a moving no-slip wall: Cf = 2nu/Uref^2 [u(x+eps n) - u_b].t / (eps + mu1(0)), needs fine near-wall resolution. The fix does not solve the #293 drag gap (mean drag -8.45 % -> -8.36 % vs control volume).

#367 "pressure keeps the constant of its initial guess", closed 2026-10-19 (not planned); diagnosis withdrawn in favour of #369; an unfixed uniform pressure shifts lift by 1.4 % on the off-grid circle; master commit #375 (2026-10-26, "constant shift preserved AC = 0") related.

Control-volume examples: #293 "Forces disagrees with control-volume-based forces", open since 2026-06-05. Coarse case D = 64, Re = 100: built-in total_force mean cD 1.3412, control volume 1.4649, DIK 1.4230 (CV +9 %). At 160 cells/D vs Turek: built-in cDmax -7.2 %, CV -0.55 %. CV code is 2D: interpolated u and p on the CV surface, viscous stress via WaterLily.S, storage term from sim.flow.u0 and dt[end-1]. weymouth: a CV needs the unsteady momentum term and numerical dissipation adds a loss; prefers vorticity impulse plus a Lamb correction. llfung's variant: a larger "measuring body" SDF with pressure_force and viscous_force plus a flux_force (llfung/WaterLily-Examples branch WIP, ThreeD_Spheroid.jl, CVMetrics.jl); b-fg gave a GPU-compatible flux_force. No CV function merged in master.

## 4. Issue #358 (AD noise) [R via API]

Open, 2026-10-08 (b-fg). Case: spinning cylinder of test_forwarddiff.jl, d(lift)/dxi at xi = 2; D = 16, grid (2D, 2D), nu = 16/500. Float32: nu moved by -10..+10 ulps at tend = 1. Float64: ForwardDiff vs central difference at tend = 2 and 4.

| Scheme | Float32 tend = 1 | Float64 tend = 2: FD-AD / central | Float64 tend = 4 |
|---|---|---|---|
| QUICK | 0.4666-0.568 | -13.51 / 0.4266 | -1.918e29 / 0.4514 |
| QUICK without 10c-9u (`quick_nobound(u,c,d)=median((5c+2d-u)/6,c,d)`) | 0.5463 | 0.4137 / 0.4138 | 0.4795 / 0.4796 |
| vanLeer | 0.5604 | 0.5101 / 0.5101 | 0.4897 / 0.4897 |
| cds | 0.3576 | 0.2437 / 0.2437 | 0.3946 / 0.3946 |

Hypothesis in the thread: the 10c-9u inner median bound gives AD factors 10 and -9 whenever round-off flips the selection; the pressure solver is shared by all schemes so is not the cause on this static case; moving bodies may need separate debugging (possibly the pressure solver). No fix landed. v1.9.0's #326 made the median branch-free: median(a,b,c) = max(min(a,b),min(max(a,b),c)); NEWS v1.10.0 "The QUICK limiter no longer branches"; the inner 10c-9u bound is still in v1.9.2, v1.10.0 and master. #351 (merged v1.9.2) runs the AD test in Float64. Release dates [W]: v1.8.0 26 Jun, v1.9.0 30 Sep, v1.9.1 2 Oct, v1.9.2 12 Oct, v1.10.0 21 Oct 2026.

## 5. CUDA.jl on WSL2 and the RTX 40-series

WSL2: Windows driver only (no Linux display driver), libcuda.so stubbed [R] NVIDIA WSL user guide; Pascal+; Windows driver r535+ for CUDA; wsl-config (2026-10-16) [gpu] appendLibPath=true and [automount] ldconfig=true add /usr/lib/wsl/lib; .wslconfig defaults memory 50 % of RAM, swap 25 %, gpuSupport=true; no GPU-memory setting. CUDA.jl needs only a working driver (own runtime artifacts); WSL not mentioned in the support matrix. Reports: Oct 2024 Discourse (Julia 1.11.1, RTX 2080 Ti) ran with /usr/lib/wsl/lib on LD_LIBRARY_PATH; NVML assertion failed (NVML partial on WSL), called not a concern; test workers died, fewer workers fixed it. Regression to avoid: microsoft/WSL#42107 (open 2026-10-29): Windows preview update KB5127936 made cuInit(0) segfault on an RTX 5090 laptop (WSL 3.0.4.0, driver 592.02); uninstalling fixed it. Other limits: managed memory not fully supported, pinned memory limited. Overhead (NVIDIA blog Aug 2021 [W]): Blender within 1 % of native, short kernels >= 90 %, early Rodinia Myocyte up to 10x slower later fixed; recommends hardware-accelerated GPU scheduling. No WaterLily-on-WSL2 report; WaterLily launches many small multigrid kernels, so launch latency is the risk; measure. Native Windows alternative: CUDA.jl supports Windows natively; WaterLily v1.10.0 NEWS benchmarked a Windows laptop RTX A2000 8 GB (Julia 1.11.9): 3.5M-cell moving cylinder 69.3 ms/step, ~19.8 ns/DOF/step. Paper anchors [R] arXiv 2407.16032: memory-bandwidth-bound; H100 1.57 ns/DOF/step (TGV FP32); 226M DOF 29 GB FP32 (~128 B/DOF); profiling on an RTX 4060 laptop.

RTX 4070 Ti vs 4070 Ti SUPER: 7680 vs 8448 CUDA cores; 12 GB vs 16 GB GDDR6X; 192-bit vs 256-bit; boost 2.61 GHz; TGP 285 W; bandwidth 504 vs 672 GB/s (TechPowerUp [S]; = 21 Gbps x bus/8). FP64 1:64 FP32 (CC 8.9: 128 FP32 vs 2 FP64 results/clk/SM) -> 4070 Ti ~40 TFLOPS FP32, ~0.63 TFLOPS FP64: Float64 GRAD-00 runs on this card are slow.

## 6. BDIM thickness floor

Lauber, Weymouth & Limbert, JCP 457 (2022) 111076 [R] arXiv 2110.06535: classic BDIM needs a flat mu0 = 0 section inside the body for the Neumann pressure BC; with eps = 2 dx the minimum thickness is 5 dx in 1D and (4 + sqrt N) dx in N dimensions, i.e. t_min = 2 eps + sqrt(N) dx; 2 dx and 4 dx disks fail the initial added-mass force (97-99.6 % error). BDIM-sigma: eps = dx/2 and SDF offset s = s_sigma - max(d/2, C1 dx), C1 = 1/2 + sqrt(N)/2; minimum thickness (1 + sqrt N) dx = 2.41 dx in 2D. Disk peak force vs experiment 1.33 +- 0.02: classic 22.4 % error at d = 2 dx, 1.6 % at the thickest; BDIM-sigma within ~3.4 % as d -> 0. Elliptic wing: minimum (1 + sqrt 3) dx; mean-lift convergence O((d/D)^1.55), 2.7 % Richardson error. Translation to WaterLily (agent inference): default eps = 1 gives t_min = (2 + sqrt 2) dx = 3.41 dx in 2D; BDIM-sigma emulation eps = 0.5 and an SDF of the plate mid-surface minus max(d/2, (1+sqrt 2)/2) cells. For the Zhang & Zerihan flap (1 mm thin region, 1.65 mm TE, c = 380 mm): cells/chord 128 -> dx 2.97 mm, t_min 10.1 mm (eps=1) / 7.2 mm (sigma); 256 -> 1.48 mm, 5.1 / 3.6 mm; 512 -> 0.74 mm, 2.5 / 1.8 mm. de Boer & Buchner (arXiv 2607.26260): plate normal to the flow at Re 1000, thickness c/15, 64 cells/chord = 4.3 cells thick, force differs < 3 % from 128 cells/chord and ~8 % at N = 32 (not inclined). No inclined-plate thickness-vs-error table found.

## What to put in the drafts (agent)
TOPO-2D-00/TR-00: pin the geometry (Tyrrell 026 main, flap 165.7 mm, overlap 9 mm, gap 12 mm, flap -8.5 deg and datum, c = 380 mm); coordinates from thesis Tables 3 and 4 (OCR check); double element tripless; compare 2D CFD to centre-section pressures/integrated Cl, not balance CL; thickening rule t_min = 2 eps + sqrt 2 cells (or BDIM-sigma); record thickening ratios; expect ~15 % 2D Cl bias with S-A (Zerihan) and ~7 % under-prediction with 3D RANS as scatter, not criteria; no 3-element data. FORCE-00: pin v1.8.0 force functions; closure test; CV cross-check per #293; expect built-in ~6-9 % from CV at D = 64, ~7 % from Turek at 160 cells/D; viscous term not wall-resolved. GRAD-00: cite #358; pin lambda; run AD in Float64 (#351); v1.9.0 branch-free median does not touch the bound; moving-body AD may have a pressure-solver source (unconfirmed). LOCAL-GPU-01: gate on nvidia-smi and CUDA.functional(), launch-latency benchmark vs native Windows; record Windows build/driver/WSL version; avoid KB5127936; specs; memory anchor 128 B/DOF 3D FP32 (~100 B/DOF 2D estimate); .wslconfig caps RAM not VRAM.

## Open gaps
Double-element CL at specific h/c and single-element balance CL at 0.224 are figure-only; Zhang & Zerihan 2003 DOI (10.2514/2.2057 snippet); Mahon & Zhang 2006 details; Genua thesis; Jasinski & Selig geometry (blocked); no WaterLily force-closure effect on this geometry; no WaterLily-on-WSL2 timing; no NVIDIA-sourced 4070 Ti bandwidth; whether WaterLily eps = 1 satisfies Lauber's condition is inference (test with a leakage check).
