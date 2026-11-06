# WP6 GEOM-S1 phase A design (Amendments 1 and 2)

Current instructions are in the Amendment 2 migration addendum below. It supersedes the original source paths, baseline-run procedure and Git-delivery commands retained here as attempt-2 history. Use `cfd_gen.scene`; the host owns all staging/commit/push/PR actions. Current results belong in `wp06_report.md` and `wp06_validation.json`.

Start: `08e0ea38`; branch: `feat/gen01-w1-06-geom-s1`. Phase B is a separate PR after phase A. The old attempt is preserved byte-for-byte in `wp06_attempt1_blocked/`.

## Contract and scope

Read `00_README.md` first, AGENTS, the requested source/contracts and research F/E, STATE and branching rules; long historical documents were read by the applicable sections allowed by Amendment 1. `phase_plan.md` remains the sole roadmap authority. No existing gate, v2 parser, harness, WaterLily job, pinned source, evidence or author-managed specification is changed. This is solver-free software/contract evidence, never Birth-1 primal qualification or a revision of GEOM03_NO_GO / SRCMAP02_INCONCLUSIVE.

Negative phi means solid; exact zero is fluid for occupancy. Scene JSON uses SI metres/radians, explicit component IDs and stable ordered lists. Hashes bind canonical JSON, fixed STL bytes and the field algorithm/version. Scene and sampled-state identities are distinct. Design-lattice occupancy/volume is reported with its grid, not as continuum volume or P22-v2's v17-specific cap.

## Representation

New files: `src/cfd_sdf/scene/{__init__,primitives,scene,events,gates}.py`; deterministic tests in `tests/scene/`; design/report/validation records here. Reuse NumPy, SciPy, trimesh, `SDFDesignState`, existing occupancy/topology/morphology definitions. No dependencies are added.

`PlateElement(id, x, z, chord, thickness, angle=0, camber=0, reflex=0, span=1, y=0)` shares one x-z section for points with final dimension 2 (x,z) or 3 (x,y,z). Flat tips use the exact extrusion composition. The undeformed stadium uses precisely v18's formula and requires gradient-norm error <=1e-8 away from medial/kink sets.

Amendment 1 requires the **v18 zero set**, rather than identical deformed field values. Its permitted raw first approximation fails the new 2%-of-thickness band requirement when camber/reflex attain their limits together: a rational boundary witness at C/c=.06,R/c=.04,t/c=.1,h/c=.025 proves error >.0342t. Consequently deformed distance values will use the same polynomial surfaces with a more accurate closest-surface projection, retaining the zero set. This is an implementation choice within the amended zero-set contract; the original field remains an independent comparison/control, not an acceptance oracle for distance values. The sampling/approximation error must be checked against a dense independently parameterised zero set. Do not relax the requested tolerances or hide this combined-amplitude case.

`EndplatePlate` is a vertical rectangular plate; `BoxBody` declares centre/radii/exponent and its distance semantics explicitly. `MeshBody` uses triangle unsigned Euclidean distance and solid-angle winding sign (phi<0 inside), rejects non-watertight/inconsistent meshes and ambiguous winding; source STL SHA is mandatory. Document #53's unqualified target signer and the opposite sign of trimesh's signed-distance helper.

`Scene(components,fixed,ground)` evaluates min union, labels by deterministic argmin, derives a padded lattice from finite component bounds and caller h/phase, and converts to existing SDFDesignState. Infinite ground is a z half-space, excluded from finite-body bounds. Union sign is correct; overlapping interiors need not be exact signed distance. General overlapping design elements are rejected; intentional endplate joints and explicit merged elements are separately declared.

## Proposals and gates

Events return finite deterministic scene proposals with explicit IDs/provenance. They do not run CFD, choose a winner, mutate history, or debit an evaluation budget. Seed libraries/positions, one-element knockout, near-pair merge, consecutive-checkpoint thickness history, and a split-warm-start N=1..N_max sequence have synthetic tests. Primitive identity and sampled solid-component changes are checked separately. Birth-0 checks intended seed identity, occupancy, position, volume and invalid policy examples; Birth-1 is **software preparation only**.

Scene gate reports all failures/unmeasured items and refuses missing required inputs. Thickness/gap defaults 4h are development defaults only; registered values must come from RES-00. R3 uses the documented node-aligned h/4 trilinear body, strict erosion, opening and defect thresholds on both solid and void. This does not adopt or revise the old R3 study. Topology/cavity/joint checks declare their sampling connectivity. Rules envelope is explicit caller/ProblemSpec data with rule-source provenance: the v2 CFD domain is never inferred to be an FSAE box. Ground/domain clearance and forbidden/root masks are distinct checks. Rejection occurs before any solver and costs zero CFD evaluations.

## Julia and resolution

JSON is the phase-A interchange contract; WP4 owns Julia job changes. Julia evaluates the same section expression/projection and extrusion directly in an AutoBody callable, then SetBody(min,...); it must not substitute trilinear design-grid interpolation. Fixed-count polynomial projection operations can be ported to GPU; runtime/parity/performance remain to be checked in WP4. WP4 polygon distance is an independent approximated surface; until available compare the undeformed pair of PlateElements with v18 to 1e-3c (including a stricter equality check).

There is no r_c on the WaterLily main line (Amendment 1); B will declare parameter bounds and increments. h sets design sampling and development feature floors, not a displacement filter. RES-00 determines the registered t/h and g/h limits and phase/error behaviour; no CFD or BDIM qualification is claimed here.

## Validation and delivery

Write tests before each implementation slice; run the relevant tests, then `pytest -q tests/scene`. A detached worktree at `/private/tmp/wp06-base-08e0ea38` runs the full base suite, without stash. After implementation run compileall and the full final suite once, compare exact failing node IDs, and run diff-check. Preserve commands, logs, SHA256 and scope separately from conclusions. Perform independent code/math review and fix material findings.

OpenCode MCP is absent; CLI 1.19.3 cannot open its sandbox-external log and the writable-XDG model query returns `Provider not found: opencode-go`. Native workers are used without changing credentials/configuration or using paid APIs. The original worktree index.lock remains denied despite the shared git root; `GIT_INDEX_FILE=/private/tmp/wp06-index` permits the requested git-mv using the **same worktree/branch/shared gitdir**, without a clone. Retain intended-path staging isolation for delivery; report any remaining index/ref limitation truthfully.

## Validation-discovered source-closure conflict

The distance amendment is implemented and tested. A NEW, independent integration constraint was observed in the CPU whole-suite run: `scripts/analyze_grid02.py:112-113` dynamically adds every current `src/cfd_sdf/**/*.py`, while `:165-167` requires those names in the immutable historical freeze. The same reader/freeze passes in detached `08e0ea38` and rejects precisely the five required new scene files in this tree. This is independent of their contents. Committing can satisfy the separate committed-at-HEAD test, but cannot add keys to a historical freeze. Do not edit pinned sources/evidence, monkeypatch or skip these checks to claim the base failure set is unchanged. Preserve the implementation for review on Draft PR #82; no phase B/ready until an explicit source-closure compatibility decision. Reproducer: `wp06_source_closure_preflight.py` and JSON.


## Amendment 2 migration addendum (2026-11-06; before edits)

Start HEAD: `9aa93169`; branch: `feat/gen01-w1-06-geom-s1`. Move only the phase-A scene package from `src/cfd_sdf/scene/` to the new top-level `src/cfd_gen/scene/` namespace. `src/cfd_sdf/**/*.py` and `julia/CFDSDFWaterLily/src/*` are enumerated by historical source freezes; their existing source bytes remain unchanged, and no compatibility exception or old-namespace shim is introduced. Scene-local relative imports remain local. The three parent-relative imports of the reused design modules must become absolute `cfd_sdf.design` imports after relocation; this is the sole necessary source-byte change beyond paths. Tests and the band-diagnostic reproducer change their scene imports and the diagnostic source path only. The old source directory, including generated bytecode, must be absent.

Add only a minimal `src/cfd_gen/__init__.py` and the requested namespace README. Preserve the previous attempts and source-closure diagnostic as historical evidence. No algorithms, existing gates, frozen evidence, v2 parser, harness or phase-B code are changed. Verify all moved source bytes against start HEAD, allowing exactly the three import-line substitutions, and run the small scene slice before the final suite.

For this amendment the host (Claude) owns staging, commit, push and Draft PR #82 delivery; Codex performs filesystem moves/edits only and never uses git mutation/index/ref commands. The parent runs compileall and exactly one final whole suite with `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`, comparing its failure nodes with the host-provided base `e3dcdf61` (3482 passed, 74 skipped, zero failures); no new base run, CPU-profile plugin or historical-test exception is used.
