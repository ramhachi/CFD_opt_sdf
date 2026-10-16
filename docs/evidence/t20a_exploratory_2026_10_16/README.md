# T2-0a: 2D ground-effect wing RANS on Kaggle CPU (issue #57), exploratory

Registration status (PROC-01): **EXPLORATORY_COMMITTED**. Evidence class when run: capability and descriptive numerical evidence only. It never feeds a
qualification flag, threshold, gate or `shape_update_allowed`; all flags stay false. It is listed in `docs/exploratory_index.md`, failures included
(that index is append-only and was not edited by the implementation; the row is added when the kernel has run).
Current state of this directory: **implementation only, nothing has been run** (no OpenFOAM, no Kaggle submission; the mesh and file generation are tested locally).

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

## What is in the repository

| file | role |
| --- | --- |
| `data/t20/tyrrell026s_genua2009.dat` | Tyrrell026S table (numbers + citation header) |
| `data/t20/reference_genua2009.json` | Genua's OpenFOAM Cl (Table 6, 23 cases at free stream/0.224/0.09; appendix Table 1: Cl and Cd of 14 cases at 7 heights), mesh specs (Tables 2-3) and the quoted experimental Cl (0.766 / 1.286 / 1.371), each with the thesis table and PDF page |
| `scripts/t20_case.py`, `scripts/t20_foam.py` | case generator (gmsh 4.15.2 mesh + OpenFOAM v2512 dictionaries + manifest) |
| `infra/kaggle/kernel_t20a_cpu/` | kernel template (`PIN_SOURCE_COMMIT`/`PIN_PINS`) and metadata (title == slug `cfd-opt-sdf-t20a-cpu`, CPU, internet, private) |
| `scripts/build_t20a_kernel.py` | renders the kernel for a source commit and verifies every pinned file against it |
| `scripts/analyze_t20a.py` | tabulates the kernel output next to Genua and the experiment |
| `tests/test_t20_case.py`, `tests/test_t20a_kernel.py` | local tests (no OpenFOAM) |

## Registered run (before the result is visible)

Kernel `ramhachi888/cfd-opt-sdf-t20a-cpu`, OpenFOAM v2512 from the hash-locked recipe of the XFID X3 runner (lock of the Round 5 environment reproduction, sha256
`b5e59f8a...6746`; explicit alias sourcing for the `foamVersion`/PS1 pitfall of `docs/issues/45_result.md`), `pip install gmsh==4.15.2`, one submission.
1. Smoke stage first (fail-closed): the three models on coarse meshes at h/c 0.448, 200 iterations. Any infrastructure failure ends the kernel with `ERROR.json` before the list.
2. Case list (13 cases): h/c in {0.671, 0.448, 0.224, 0.134, 0.09} x {sa-wf, sst-wf} on `med30` (4 mm surface spacing, first cell 0.6 mm, Genua's Med30), and sst-lm
   (`kOmegaSSTLM`, wall resolved, `wr2`: 2 mm, first cell 0.01 mm, 40-41 layers, growth 1.12) at h/c in {0.224, 0.134, 0.09}.
   Iterations: 5000 (wall functions), 10000 (wall resolved); `residualControl` p 1e-6, U 1e-7, turbulence 1e-6.
3. Four independent cases concurrently (4 vCPU), per-case solver timeout 2.5 h (wall functions) / 5 h (wall resolved), kernel budget 10.5 h.
4. Per case: forces history (`coefficient.dat`, `force.dat`), final and tail-mean Cl/Cd, iterations, wall time, residual-convergence and force-plateau flags (last 20 %
   of iterations, relative std and drift < 0.5 %: descriptive, not a gate), `checkMesh` log, gmsh mesh (gz), case dictionaries, artifact manifest. `DONE` is written last.

Local mesh sizes (cells, one-cell extrusion; gmsh output varies by a few cells between runs): coa30 7.1k-9.4k, med30 13.8k-15.9k, fine30 26.0k-28.7k, wrc 10.7k-13.0k,
wr2 63.5k-67.8k across h/c 0.09-0.671; gap cells across the minimum gap 18 (med30) and 85 (wr2) at h/c = 0.09.

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

- **Nothing OpenFOAM-side has been executed**: dictionary syntax (v2512 `model` keyword in `momentumTransport`/`turbulenceProperties`, `forceCoeffs`/`forces` options, regex keys in
  `fvSolution`), `gmshToFoam` on the prism/hex extrusion, the patch-type fix for `empty`/`wall`, `kOmegaSSTLM` availability and its boundary conditions, wall-function behaviour on the moving
  ground, and the gmsh PyPI wheel on the Kaggle image (the runner installs GL libraries if the import fails) are all untested. The smoke stage is the first execution.
- **Mesh not bit-reproducible.** Dictionaries, manifest inputs and the airfoil geometry are bit-reproducible; gmsh 4.15.2's boundary-layer path changes the triangle core by a few cells between
  runs (not threads, `Mesh.RandomFactor` or the algorithm choice; cause not isolated). The mesh file written is canonical (sorted) and each run's `mesh.msh` and SHA-256 are kept.
- Genua's meshes (ANSA, fictitious wake surface, 7.9k-141k cells) are not reproduced: this is a gmsh quad-layer + triangle core mesh with a fan at the sharp TE, and the layer count is
  capped so each wall's stack stays below 0.4 of the minimum gap. Numerical schemes (linearUpwind U, upwind turbulence), relaxation and solver settings are not from Genua (not stated there).
- Inlet nuTilda = 5 nu (SA), k = 1.5 (Tu U)^2 and omega from the 1 cm length scale (SST), Re_theta,t from the Langtry-Menter Tu correlation (about 999) and gammaInt = 1 (LM): standard
  practice, not from Genua. Cl is reported as downforce coefficient (`liftDir (0 -1 0)`), chord reference, per unit span (extrusion 2 mm).
- The quoted experimental Cl values are secondary (via Genua, from Zerihan & Zhang 2001) and include no transition-free/tripped distinction; the full Cl(h/c) curve and Cp were not digitised.
