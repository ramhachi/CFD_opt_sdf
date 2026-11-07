# Opus source review 1 of WP5 (PR #87, cb4df650), 2026-11-06

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions taken on it: `docs/topo2d00_registration_2026_11_01.md` Amendment 1 and `05_tr00_rans.md` Amendment 1.

# WP5 source review (TR-00 / TOPO-2D-00 RANS side), branch feat/gen01-w1-05-tr00-rans @ cb4df650

Read-only. I confirmed that the branch only adds files: 32 added, 0 modified against e3dcdf61. `pytest -q tests/topo2d00` gives 119 passed in 41 s, with gmsh present. I ran the adversarial inputs from scratch scripts and did not modify the repository.

## A. Spec fidelity

**BLOCKER A1: the RANS mesh is built on a faceted body, and nothing guards against it.** `t2d_multibody_case.py:221-223` makes one gmsh line per input segment. T2-0 spline-resamples the section at 1 mm (`t20_case.airfoil_points`), but the design memo records that this spline was deliberately removed here. The WP4 geometry actually rendered into the kernels has these properties:
- `flap1` has 36 vertices with a median segment of 12.9 mm.
- The flap leading edge (x/c 0–0.025) has kinks of 55°, 41°, 34° and 26°, on segments of 2.3–5 mm.
- The main leading edge has about 15° kinks.

I measured this from the `rendered_kernels_and_inputs.tar.gz` geometry. TR-00 compares the result with the smooth experimental body. A flap nose with 55° corners at Re 4.6e5 confounds exactly the slot and flap loading that Δ(1→2) measures. Even so, the rendered TR-00 kernels are marked `ready_for_execution: true` (archived plan).
- Fix: make WP4 produce a dense, smooth polygon (or resample with a spline shared with WP4).
- Fix: in `load_geometry`, reject any non-cap turning angle above a few degrees and any segment longer than ds.
- Fix: re-render the kernels.

**MAJOR A2: the convergence rule is not the registered one, and the documentation contradicts the code.**
- Registration §3 calls for T2-0c's rules (block plateau; UNSTEADY only above 0.5 % raw-tail std).
- `collect_rans.py:154-186` instead uses T2-0d `steady_stats`, which requires a raw-tail std below 1e-3, and `:319-320` requires `settled` for `usable`.
- The case manifest still records T2-0c's `unsteady_raw_tail_relative_std: 0.005` (`t2d_foam_case.py:26-30`).

Adversarial inputs: Cl = 2 + a period-2 alternation (0.3 % raw std), a period-7 sine (0.28 %) and Gaussian noise (0.2 %). All three pass the plateau, and T2-0c would accept them as VALID. The collector labels all three `limit_cycle / VALID_PERIODIC` and `usable=false`, so they export as `NUMERICAL`. White noise is therefore misreported as a limit cycle, because T2-0d's `urans_stats` is applied in iteration space.

Such cases are never continued, since `run_rans.py:146-159` triggers continuation only on the plateau, yet they are unusable. Either align the collector with T2-0c or amend the registration, and in either case make the manifest and the collector agree.

**MAJOR A3: the boundary-layer stack depends on the configuration.** `t2d_multibody_case.py:205-209` caps the layer count with the minimum over the ride height and the inter-body gaps. That count is then applied to every wall and to the ground block. Using `T.layers`:

| family | E1 | E2_sharp (gap 11.4 mm) | E2 thick (gap 8.5 mm) |
| --- | --- | --- | --- |
| med30 | 7 layers (7.75 mm) | 5 layers (4.46 mm) | 4 layers |

fine30 drops to 3 layers when the gap is below 8.05 mm, which is plausible for E3. This is a systematic mesh change inside the Δ(1→2) contrast. The 8-realisation interval does not capture it, and the report does not disclose it.
- Fix: fix the layer count per family from the study-wide minimum gap.
- Fix: assert that `n_layers` is equal across configurations in the collector.

**MAJOR A4: the realisation-noise premise is never checked.**
- Nothing checks that the 8 mesh SHAs per (config, model, family) differ.
- §8's "one R realisation re-meshed" control has no code: realisation is hard-limited to 0–7 at `t2d_foam_case.py:94` and `collect_rans.py:63-65`.
- With exact-polyline input, gmsh may well be deterministic. Identical meshes would give a zero-width 90 % interval, and WP4's `tr00()` would then decide `TR00_PASS_RATIO` on the point estimate alone.
- Fix: flag duplicate SHAs (fail closed or make it a required diagnostic), and add the control run.

**MINOR A5: spec gaps.**
- Ride height is reported only as h/c1. §2 asks for both normalisations: c1 for E1, and c = 380 mm for E2/E3.
- The E\*_sharp "what thickening alone does" arm has no output.
- The shared format gives the sharp arms pressure-only forces and the thick arms totals, so a naive sharp-vs-thick comparison would mix observables.
- §4 names the *double-element* digitising uncertainty for the 5 % test. `digitize_cp.py:260` adds the E1 (Table 15) reading sensitivity as well. This is conservative, but the estimator (full |d1−d2|, summed per element) is a choice the registration has not yet made.

Items correctly implemented:
- SA-WF / SST-WF.
- fine30 plus med30.
- 5000 → one continuation to 15000, judged on the last segment as in T2-0b/T2-0c.
- Common c1 = 0.2234 m and Aref = c1·0.002.
- Cl is downforce (−Fy), Cd is +x.
- Per-element and total coefficients, with closure checks.
- The pressure/viscous split is read from `forces` `force.dat` by named columns, not from forceCoeffs' (f)/(r) columns. I verified the headers in the smoke output.
- The [0.5, 2] band belongs to WP4 and is correctly not implemented here.

## B. Pins and fail-closed

- **NOTE.** No frozen file is edited. `t20_case`, `t20_foam` and the T2-0b runner helpers are imported, not copied. `run_rans.inherited_runner` executes the frozen template with an injected `PIN_PINS={}`; none of the functions it uses read the placeholders, so I found no behavioural change.
- **MINOR B1: proxy gate.** `run_rans.py:122-124` refuses to solve whenever the gmsh proxy fails. That proxy includes `skew_boundary`, which `t20_case` marks UNVERIFIED. In T2-0 the proxy was informational only. A mesh that passes checkMesh can therefore become `MESH_FAILED` and be exported as NUMERICAL.
- **MINOR B2: misclassified divergence.** `run_rans.py:150`: T2-0b's `read_coefficients` raises on non-finite rows. That exception becomes `RUNNER_EXCEPTION`, then INFRA_LOSS, then INCOMPLETE. T2-0b treated the same case as diverged.
- **MINOR B3: rendered kernels are not tied to a freeze.** `build_tr00_kernels.py:53,183-189` renders TR-00 kernels as ready even with `source_dirty=true` and UNVERIFIED_OCR geometry. Nothing binds them to a freeze; ready should require a clean tree and a frozen tree.
- **MINOR B4: hard-coded numbers without a source.**
  - `t2d_multibody_case` copies the Ball values .012/.03/ds/3, wake 0.2 and the 0.4·gap factor without comments.
  - The wall `Distance` sampling drifted from T2-0's 200 per spline to 3 per segment (`:275`).
  - `MAX_RUNS=12`.
  - `to_wp4` hard-codes 223.4 / 460000 / 100.
- **NOTE.** `continuation/system/controlDict` is written but never used: the runtime edits `controlDict` through T2-0b `_continue`. The archived dictionary therefore differs from the executed one (writeInterval).
- **NOTE.** Generator, gmsh and checkMesh failures are exported as `NUMERICAL`.
- **NOTE.** `--qualified-cell` is not machine-bound to WP4's `tr00.json`.
- **NOTE.** The shared output embeds the full measurement set twice (diagnostics and provenance).
- Correctly fail-closed: missing runs, hash mismatches (coefficient, force, mesh, geometry against the plan), unknown model/family/config, duplicates, and Cp CSV format violations.

## C. Numerics

- **`digitize_cp`.** Correct: Cl_down = (c_a/c1)·[∫Cp_upper d(x/c) − ∫Cp_lower d(x/c)], which is −Fz/q with +z upward. Per-surface trapezoids, enforced endpoint coverage, and rejection of local-chord abscissae are all correct.
- **MINOR C1: copied reader passes.** Reader B's CSVs as byte copies of reader A's, under new filenames, give sensitivity 0 and `exceeds_5_percent=false`. Neither the tool nor `collect_rans._pressure_reference` catches it, because the latter de-duplicates by path only (`:437-443`). Add a SHA-distinctness check.
- **MINOR C2: no sign check.** With upper/lower swapped (the Cp-plot "top curve" taken as the physical upper surface), E2 Cl = −2.5 and the increment −3.5 are accepted silently. TR-00 would fail, so the error fails safe, but it is silent. Two-point surfaces are also accepted.
- **`collect_rans`.** Restart concatenation, contiguity, total/element and pressure/viscous closure, and use of the last segment are all correct. The `topo2d00-rans-results-v1` file carries per-realisation SETTLED/NUMERICAL/INCOMPLETE status, mesh SHAs and total forces (pressure-only for the sharp arms). Per-element, pressure/viscous and convergence detail stays in `diagnostics` and in the separate `topo2d00-rans-v1` file. The schema is byte-identical to WP4's (SHA 04ebcf76…). The classification defect is A2.

## D. Tests

The 119 tests are mostly behavioural on synthetic data, including an end-to-end continuation driven through `run_rans` into `collect`. Some only pin T2-0d quirks, such as a period-20 sine being periodic while a period-40 sine is NONSTATIONARY.

Untested:
- The T2-0c/T2-0d band and noise-as-limit-cycle (A2).
- Layer-count changes across configurations (A3).
- Coarse or kinked polygons (A1).
- Duplicate realisation SHAs (A4).
- The non-finite path of the continuation trigger (B2).
- Identical-content readers (C1).

The gmsh skip (`find_spec('gmsh') is None`, matching conftest, with no new pin) is sound. Only mesh-executing tests are skipped.

## E. Report honesty

Backed by artifacts:
- 3482 / 3601 passed, 74 skipped.
- 6 Metal nodes failing identically on base and final.
- 119 passed in 106.41 s.
- Every smoke-table value (cells, checkMesh, proxy, SICN, 4 layers / 3.2208 mm, mesh SHAs).
- Wall time 235.43 s, rc 0, dpkg matches the lock.
- Force closure below 3e-8.
- Timing attribution (13–21 min belongs to xfine30; fine30 is 6–11 min, per the T2-0 summary).
- The 160 CPU h ledger caveat (`global_budget_enforced=false`, case caps summing to 400 h).

**MINOR E1.** The `merge-tree` no-conflict claim against b06452a1 has no artifact. The report also omits three things:
- the faceted WP4 geometry (A1);
- the layer-count confound (A3);
- that the collector's settled threshold (1e-3) is stricter than the T2-0c rule its own manifest cites (A2).

## Verdict

**INTEGRATE_AFTER_FIXES.** The tooling is honest, well fail-closed, reuses the pinned T2-0 code without editing it, and its force bookkeeping is correct. Even so, no TR-00 kernel should run until these are fixed:

1. Smooth or dense geometry, with a turning-angle/segment guard; re-render and block the archived ready kernels (A1).
2. Align the convergence classification with registration §3, or amend the registration; make the manifest agree; stop labelling noise as a limit cycle (A2).
3. A configuration-independent boundary-layer stack per family, asserted in the collector (A3).
4. A distinct-mesh-SHA check plus the §8 re-mesh control (A4).
5. A reader SHA-distinctness check and a ready-requires-clean-and-frozen render rule (C1, B3).

The remaining MINOR items can follow.
