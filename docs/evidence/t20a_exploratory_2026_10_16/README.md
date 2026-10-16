# T2-0a: 2D ground-effect wing RANS on Kaggle CPU (issue #57), exploratory

Registration status (PROC-01): **EXPLORATORY_COMMITTED**. Evidence class when run: capability and descriptive numerical evidence only. It never feeds a
qualification flag, threshold, gate or `shape_update_allowed`; all flags stay false. It is listed in `docs/exploratory_index.md`, failures included
(that index is append-only and was not edited by the implementation; the row is added when the kernel has run).
Current state of this directory: attempt 1 stopped before any case (Kaggle image is Ubuntu noble, only the jammy lock was registered); attempt 2 installed OpenFOAM v2512 and ran the smoke stage:
SA-WF and SST-WF on `coa30` completed 200 iterations, but `checkMesh` failed on both meshes and `kOmegaSSTLM` on `wrc` died with SIGFPE after 9 iterations (see "Attempt 2 findings and the fix").
This revision (mesh, LM two-stage setup, kernel policy, MESH_ONLY kernel) is tested locally only (gmsh and a Python proxy of `checkMesh`, no OpenFOAM) and has not been run on Kaggle.

## Question

Is a body-fitted 2D RANS evaluator at an FSAE-relevant Reynolds number feasible on Kaggle CPU (case development, mesh, wall time per case), and how
far do the three model setups sit from the published OpenFOAM reproduction (Genua 2009) and from the quoted experiment? No claim about downforce
accuracy, grid independence, or fitness of the evaluator is made or implied.

## Case

Zerihan & Zhang single-element wing in ground effect, Tyrrell 026 main element (inverted, moving belt), chord 0.2234 m, U = 30 m/s,
Re_c = 4.6e5 (nu = 1.4570e-5 m2/s), Tu 0.3 %, integral length 1 cm. Geometry: the **XFOIL-sharpened CFD variant "Tyrrell026S"** from Genua (TU Delft MSc
thesis, July 2009, Table 1), not the tested blunt-TE (0.007c) wing. Ride height h = distance from the lowest point of the suction surface to the ground
(the table's minimum, x/c = 0.1996, y/c = -0.0771); domain 2c upstream, 5c downstream, 6.8c above the ground, slip top, ground moving at U (no-slip in the belt frame).

**Incidence (what could and could not be determined).** Genua states only that the listing of the profile "at alpha = 3.6 deg" is in Zerihan's PhD thesis and
that, for the inverted wing, alpha is positive when the leading edge is rotated toward the ground. Table 1 gives the coordinates already in that orientation (LE at
(0,0), TE at (1, 0.0603), suction side y < 0 toward the ground; the chord-line angle of the table is atan(0.0603) = 3.45 deg, which is consistent with, but not
exactly equal to, 3.6 deg after the XFOIL sharpening and renormalisation). Genua does not state any other incidence for his comparisons, so the generator uses the table
as given (nominal 3.6 deg) and offers `--delta-alpha-deg` (counter-clockwise about the LE, LE toward the ground = +) only for later work. The incidence used by
Zerihan & Zhang for the quoted experimental Cl was not verified from the primary source.

## Attempt 2 findings and the fix

`checkMesh -allGeometry -allTopology` failed on both smoke meshes (`coa30`: unused points, 4 skew faces, 14 small-determinant cells, 2 low-weight faces; `wrc`: the same plus 2359 small-determinant cells,
23 low-weight faces, 33 low-volume-ratio faces, max aspect ratio 798, and non-orthogonality up to 89.9 degrees). Causes, found by reproducing the logs locally (`scripts/t20_case.py:mesh_quality`, which reproduces
the old logs' unused-point count, max non-orthogonality 89.938, low-weight 2/23, volume-ratio 33, max aspect ratio 797.857 and the cell-determinant count 14/2359 with its minimum to 7 digits):

- **Unused points (1024 coa30/wrc, 1121 med30, 1290 fine30/wr2)**: `_write_msh` wrote every gmsh node, including geometry points and spline control points that no cell uses. Now only nodes of volume cells are written.
- **Slivers and 89.9-degree faces**: gmsh's boundary-layer field on the ground ended on the inlet/outlet, leaving 0.8 m x 8 mm sliver triangles from the layer top to the inlet/outlet nodes (116 / 215 faces above 70 degrees; probably also most of the skew faces, not isolated). The ground layer is now an explicit structured block (transfinite quads, exact first layer and growth, vertical ends on the inlet/outlet, extruded to hexahedra).
- **Cell determinant (2359 cells)**: OpenFOAM computes it from the *internal* faces only, `det(sum (S/avg|S|)(S/avg|S|)^T)/8`, so a wall cell is flagged above aspect ratio ~141, an interior quad above ~89 and a cell with a boundary face on its
  short side (the end columns of the ground layer at the inlet/outlet) above ~35. `wrc` had aspect ratio 800 (ds 8 mm / y1 10 um), `wr2` 200. Wall-resolved meshes now keep ds/y1 = 60 (`wrc` 1.2 mm / 20 um, `wr2` 0.6 mm / 10 um),
  and the ground block's end columns are graded to 20 y1 wide.
- **Face weights / volume ratios at the sharp-TE fan (0.0006 / 0.0004)**: the wall spacing (4 mm) was far wider than the fan cells (~y1). The TE surface spacing now starts at `te` first-layer heights and grows 20 % per
  length, with `fan` fan elements, tuned per mesh. The best face weight of a sharp-TE fan is about 1/(1 + sqrt(1.5 R/y1)) for a layer stack of thickness R, which is why the wall-resolved stack ends at 0.3 ds
  (R/y1 about 90) instead of the equal-area 0.433 ds: it keeps the weight at 0.06-0.08 (checkMesh limit 0.05). The cost is a thinner structured stack (about 0.9 mm for `wr2`), a limitation for the transition model.
- **`sigfpe: true` in the SA-WF smoke record** was the startup line `trapFpe: Floating point exception trapping enabled`, not a crash (parser fixed to look for `sigFpe::sigHandler`).

Local proxy metrics per mesh (all 25 mesh spec x height combinations, from `tests/test_t20_case.py`; before = attempt-2 generator, after = this one; checkMesh limits in brackets):

| mesh | cells | unused pts | non-orth max (70 severe) | weight min (0.05) | vol ratio min (0.01) | det min (1e-3) | aspect ratio max (1000) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| coa30 before / after | 7.1-9.4k / 7.4-9.5k | 1024 / 0 | 86.9-89.3 / 33-47 | 0.033 / 0.116-0.148 | 0.025 / 0.131 | 2e-6..6e-5 / 8.4e-3 | 17-39 / 13 |
| med30 | 13.8-15.9k / 13.7-15.9k | 1121 / 0 | 84-87 / 36-41 | 0.063 / 0.141-0.148 | 0.05 / 0.13 | 6e-5..1.4e-4 / 2.6e-2 | 10-14 / 7 |
| fine30 | 26.0-28.7k / 25.3-28.0k | 1290 / 0 | 75-76 / 37-46 | 0.117 / 0.172 | 0.100 / 0.156 | 1.4e-3 / 4.7e-2-6.3e-2 | 5-7 / 4 |
| wrc (old 8 mm/10 um, new 1.2 mm/20 um) | 10.7-13.0k / 62.1-65.2k | 1024 / 0 | 89-90 / 39-54 | 0.0006 / 0.080 | 0.0004 / 0.065 | 4e-8 / 2.9e-3 | 798 / 62 |
| wr2 (old 2 mm/10 um, new 0.6 mm/10 um) | 63.6-67.8k / 129.6-132.5k | 1290 / 0 | 90 / 42-55 | 0.0022 / 0.062-0.079 | 0.0017 / 0.050-0.065 | 4e-10 / 2.4e-3 | 657 / 69 |

Gap cells across the minimum gap at h/c 0.09 (the registered probe needs >= 15): coa30 16, med30 18, fine30 20, wrc 47, wr2 56. Per-mesh metrics are in every case manifest (`mesh_stats.quality`, `mesh_quality_failures`).

The proxy is exact for the quantities above but NOT verified for skewness: the old logs report 29 skew faces (wrc, max 11.7) / 4 (coa30, max 8.3), which the proxy does not reproduce (its internal-face skewness on the old meshes is below 4);
the boundary-face definition is from memory (`skew_boundary`) and the sliver region of the old meshes was run-to-run unstable. The new meshes have internal skewness <= 0.8 (limit 4), so any plausible boundary definition passes, but this is the one
checkMesh quantity the Kaggle mesh-only run has to confirm.

## kOmegaSSTLM: continuation instead of a cold start

The LM run died at iteration 9 from a uniform initial field on the bad mesh (continuity error 1e18). Each `sst-lm` case is now two stages in one case directory, on the same wall-resolved mesh:
1. kOmegaSST (SIMPLEC, relaxation 0.7) for `min(2000, iters/2)` iterations;
2. the runner copies the 0/ `gammaInt` and `ReThetat` (uniform from the inlet values) into the latest time, swaps in `stage2/` (kOmegaSSTLM, `consistent no`, relaxation U 0.5, p 0.2, k/omega/ReThetat/gammaInt 0.3,
   `startFrom latestTime`, upwind `bounded Gauss` for all turbulence and transition equations, as in stage 1) and continues to `iters`. Stage 2 forceCoeffs go to `postProcessing/forceCoeffs/<stage-1 end time>/`.

UNCERTAIN, never executed: the optional velocity limiter `system/fvOptions` (`velocityDampingConstraint`, UMax 2 U_inf, C 1: ESI fvOptions syntax from memory) - if stage 2 dies before its first iteration with a FOAM FATAL the runner removes the file
and reruns the stage once (`stages[-1].limiter` says which); the `kOmegaSSTLM` model keyword and field names in v2512 (the attempt-2 run did start the model and read both fields, so this part is confirmed); whether first-order upwind and these
factors are enough to avoid divergence on the real flow (not tested: only the dictionaries and the runner flow are tested, the latter with shell stubs).

## What is in the repository

| file | role |
| --- | --- |
| `data/t20/tyrrell026s_genua2009.dat` | Tyrrell026S table (numbers + citation header) |
| `data/t20/reference_genua2009.json` | Genua's OpenFOAM Cl (Table 6, 23 cases at free stream/0.224/0.09; appendix Table 1: Cl and Cd of 14 cases at 7 heights), mesh specs (Tables 2-3) and the quoted experimental Cl (0.766 / 1.286 / 1.371), each with the thesis table and PDF page |
| `scripts/t20_case.py`, `scripts/t20_foam.py` | case generator (gmsh 4.15.2 mesh + OpenFOAM v2512 dictionaries + manifest) |
| `infra/kaggle/kernel_t20a_cpu/` | kernel template (`PIN_SOURCE_COMMIT`/`PIN_MODE`/`PIN_PINS`) and metadata (title == slug `cfd-opt-sdf-t20a-cpu`, CPU, internet, private) |
| `scripts/build_t20a_kernel.py` | renders the kernel for a source commit and verifies every pinned file against it; `--mode mesh_only` renders the checkMesh-only kernel under the slug `cfd-opt-sdf-t20a-meshcheck` |
| `scripts/analyze_t20a.py` | tabulates the kernel output next to Genua and the experiment |
| `tests/test_t20_case.py`, `tests/test_t20a_kernel.py` | local tests (no OpenFOAM) |

## Registered run (before the result is visible)

Kernel `ramhachi888/cfd-opt-sdf-t20a-cpu`, OpenFOAM v2512 from the hash-locked recipe of the XFID X3 runner (lock of the Round 5 environment reproduction, sha256
`b5e59f8a...6746`; explicit alias sourcing for the `foamVersion`/PS1 pitfall of `docs/issues/45_result.md`), `pip install gmsh==4.15.2`, one submission.
0. Optional pre-check, a separate kernel (`--mode mesh_only`, slug `cfd-opt-sdf-t20a-meshcheck`): generate all 25 registered (mesh, h/c) meshes, `gmshToFoam`, boundary fix, `checkMesh -allGeometry -allTopology`, no solver; writes `meshcheck.json` / `meshcheck.md`
   (checkMesh next to the local proxy per mesh, status `MESH_OK`/`MESH_FAILED`). Use it to verify the mesh fix in minutes before the full run.
1. Smoke stage first: the three models on coarse meshes at h/c 0.448, 200 iterations (`kOmegaSSTLM` as 100 SST + 100 LM). Only SA-WF and SST-WF gate the kernel (infrastructure failure ends it with `ERROR.json` before the list);
   an LM failure, in the smoke stage or the list, is the recorded case result `LM_DIVERGED` (failed stage, last time, residuals, log tail) and never stops the kernel.
2. Case list (13 cases): h/c in {0.671, 0.448, 0.224, 0.134, 0.09} x {sa-wf, sst-wf} on `med30` (4 mm surface spacing, first cell 0.6 mm, Genua's Med30), and sst-lm
   (`kOmegaSSTLM`, wall resolved, `wr2`: 0.6 mm, first cell 0.01 mm, 14 layers, growth 1.25, two-stage as above) at h/c in {0.224, 0.134, 0.09}.
   Iterations: 5000 (wall functions), 10000 (wall resolved); `residualControl` p 1e-6, U 1e-7, turbulence 1e-6.
3. Four independent cases concurrently (4 vCPU), per-case solver timeout 2.5 h (wall functions) / 5 h (wall resolved), kernel budget 10.5 h.
4. Per case: forces history (`coefficient.dat`, `force.dat`), final and tail-mean Cl/Cd, iterations, wall time, residual-convergence and force-plateau flags (last 20 %
   of iterations, relative std and drift < 0.5 %: descriptive, not a gate), `checkMesh` log, gmsh mesh (gz), case dictionaries, artifact manifest. `DONE` is written last.

Local mesh sizes (cells, one-cell extrusion; gmsh output varies by a few cells between runs): coa30 7.4k-9.5k, med30 13.7k-15.9k, fine30 25.3k-28.0k, wrc 62k-65k,
wr2 130k-133k across h/c 0.09-0.671 (the wall-resolved meshes grew: checkMesh's determinant limit forces ds <= ~60-80 y1, see above).

## What is visible before the run

Genua's OpenFOAM results (`reference_genua2009.json`): his Med30SA follows the experimental Cl(h/c) curve with a peak at h/c = 0.134, Cl 1.255 at 0.224 and 1.381 at 0.09;
his Med30KWS (k-omega SST, wall function) predicts no separation at 0.09 and Cl 1.779 there; the experiment is 1.286 and 1.371 at those two heights. These numbers were read before
this implementation and shape the expectation that sa-wf is closest and sst-wf fails at h/c = 0.09; no prediction is registered for sst-lm (no Genua counterpart). No result of this
implementation is visible. Any agreement or disagreement is descriptive: the case could agree because of compensating wall-function and y+ effects (Genua's own finer grids were worse),
and the experiment has a laminar separation bubble that fully turbulent models cannot represent.

## Claim ceiling

Allowed after the run: that the case generator, mesh, OpenFOAM setup and the three models run to completion (or not) on Kaggle CPU with stated wall times, cell counts and
convergence flags, and a descriptive table of Cl/Cd against Genua's numbers and the quoted experimental Cl.
Not allowed: any statement of absolute downforce accuracy, grid independence or a verdict on the evaluator, qualification for full-vehicle or high-Re FSAE flow, a Stage T/V ranking,
or a transfer to the SDF pipeline. Citable in a decision only after a registered re-run (PROC-01).

## Known gaps and deviations

- **Executed so far (attempt 2)**: `gmshToFoam`, the patch-type fix, `checkMesh`, and `simpleFoam` for SA-WF and SST-WF (200 iterations, plateaued Cl 1.03-1.05 at h/c 0.448), and the start of `kOmegaSSTLM`. **Still unexecuted**: the LM continuation
  (stage switch, `stage2/` dictionaries, the fvOptions limiter), anything on the new meshes (the local proxy is not checkMesh), the long runs. Original list of untested items from before attempt 2: dictionary syntax (v2512 `model` keyword in `momentumTransport`/`turbulenceProperties`, `forceCoeffs`/`forces` options, regex keys in
  `fvSolution`), `gmshToFoam` on the prism/hex extrusion, the patch-type fix for `empty`/`wall`, `kOmegaSSTLM` availability and its boundary conditions, wall-function behaviour on the moving
  ground, and the gmsh PyPI wheel on the Kaggle image (the runner installs GL libraries if the import fails) are all untested. The smoke stage is the first execution.
- **Mesh not bit-reproducible.** Dictionaries, manifest inputs and the airfoil geometry are bit-reproducible; gmsh 4.15.2's boundary-layer path changes the triangle core by a few cells between
  runs (not threads, `Mesh.RandomFactor` or the algorithm choice; cause not isolated). The mesh file written is canonical (sorted) and each run's `mesh.msh` and SHA-256 are kept.
- Genua's meshes (ANSA, fictitious wake surface, 7.9k-141k cells) are not reproduced: this is a gmsh quad-layer + triangle core mesh with a fan at the sharp TE, and the layer count is
  capped so each wall's stack stays below 0.4 of the minimum gap. Numerical schemes (linearUpwind U, upwind turbulence), relaxation and solver settings are not from Genua (not stated there).
- Inlet nuTilda = 5 nu (SA), k = 1.5 (Tu U)^2 and omega from the 1 cm length scale (SST), Re_theta,t from the Langtry-Menter Tu correlation (about 999) and gammaInt = 1 (LM): standard
  practice, not from Genua. Cl is reported as downforce coefficient (`liftDir (0 -1 0)`), chord reference, per unit span (extrusion 2 mm).
- The quoted experimental Cl values are secondary (via Genua, from Zerihan & Zhang 2001) and include no transition-free/tripped distinction; the full Cl(h/c) curve and Cp were not digitised.
