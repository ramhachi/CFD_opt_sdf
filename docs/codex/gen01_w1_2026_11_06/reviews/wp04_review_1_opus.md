# Opus source review 1 of WP4 (PR #89, fae6c0a8), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions: `docs/topo2d00_registration_2026_11_01.md` Amendment 5 and `04_topo2d_waterlily.md` Amendment 5.

# WP4 source review (TOPO-2D-00, WaterLily side): branch feat/gen01-w1-04-topo2d-waterlily @ fae6c0a8, Draft PR #89

Read-only adversarial review. Commands I ran myself: `pytest -q tests/topo2d00` gave **219 passed** in 52 s. `julia … scripts/topo2d_selftest.jl` gave **43/43** in 33.7 s (default invocation, no WP1/WP2 env). I also ran independent scripts for geometry, transcription, SDF agreement, adversarial labels, regeneration determinism and CPU timing. `git diff --name-status e3dcdf61` shows only additions (223 files). The registered job, `julia/CFDSDFWaterLily/src`, `src/cfd_sdf`, the harness tool files, `tests/conftest.py` and the Project/Manifest files are byte-identical. `SHA256SUMS` under `wp04_validation_amend3/` verifies 48/48. The full-suite log shows 3701 passed, 74 skipped, 0 failed.

Counts: **1 BLOCKER** (registration-level), **3 MAJOR**, **9 MINOR**, **8 NOTE**.

## BLOCKER

**B1. Amendment 4's `CONCORDANT_PARTIAL` case is still unreachable under the precedence it keeps.** Code: `analyze.py:511-522`, `check.py:486-496`; registration Amendment 4 §2.
- At the second Re, if the W and R Δ(1→2) intervals are both resolved with opposite signs, the two E1/E2 orderings are opposite. If both rankings are resolved, `RANK_AGREE` is false with both sides resolved, which is `DISCORDANT` by §5.
- To keep "RANK_AGREE true wherever both sides are resolved", one side's ranking must be unresolved. Its adjacent interval then contains 0, which is `UNRESOLVED` by the same amendment.
- Demonstrated by case (c) below: analyzer and checker both return `DISCORDANT`.
- The reachability test Amendment 4 requires therefore cannot be written. The code correctly implements reading R1, where every interval used by any rule is "required".
- Fix in the registration before freeze. Define "required interval" (Δ12 only, or every adjacent rank pair). Then either restrict the DISCORDANT rank clause to "both Re", or drop PARTIAL. Update analyzer, checker and tests together. This is not a code bug.

## MAJOR

**M1. The static scene is re-measured every step** (`Topo2D.jl:228,233` call `sim_step!` with the default `remeasure=true`; recorded in the fingerprint at `:166`).
- Each `measure!` evaluates the O(N) polygon SDF at every cell, plus ForwardDiff near the body. E3 has 1962 vertices.
- My CPU timing at the formal 842×826 grid, one thread: `measure!` costs 1.16 s vs `mom_step!` 0.74 s for E1 (1.6×), and 2.89 s vs 0.71 s for E3 (4.1×).
- On CUDA the polygons are by-value `NTuple`s (`:149`): about 15.7 KB for E3 in every measure kernel, with dynamically indexed reads (spill risk).
- Each state is also a fresh Julia process, so GPU compile time is charged to `solver_wall_time_cap_s`.
- Budget risk: 0.23 T4 h per run is assumed, and the caps are 14 h per Re kernel. Missing them gives `INCOMPLETE`.
- Fix: use `sim_step!(sim; remeasure=false)` after construction. Body and ground velocity are static, so results should be bit-identical. Add a CPU bit-identity test, update the fingerprint field, and measure ms/step in the GPU smoke.

**M2. Parent pre-run window machinery is missing** (registration §5 and §7; `scene_campaign.py:248-282`).
- The campaign has no E1 pre-run state.
- No code implements the burn-in rule or the S0 spectral estimate.
- `formal_context` accepts any hash-bound JSON carrying `mean_downforce`, `s0_upper` and `burn_in`. Units are undefined (coefficient vs N/m; S0 in c1/U). `parent_window` only checks burn ≥ 80 and applies the formula.
- Result: the frozen window would rest on hand-entered numbers. Needed before freeze, not for a smoke.

**M3. σ_d uses upper confidence limits, which the registration does not state** (`analyze.py:168-197`, `:381`).
- The registration (§5; RE-01 §3.4) says "the larger used". The code uses the 97.5 % χ² upper bound for A and a Bonferroni-split bound (tail 0.025/2P) for B, then also applies a t-quantile.
- The WP4 prompt asked for "上側信頼限界", so this is authorised by the prompt but not by the registration.

| Use | P | A inflation | B inflation |
| --- | ---: | ---: | ---: |
| Main contrasts | 16 | ×1.55 | ×3.55 |
| Confirmation (feeds RESOLUTION_LIMITED via Fieller, df 3) | 4 | ×3.73 | ×2.87 |
| DOMAIN control | 2 | ×31.9 | ×2.57 |

- The DOMAIN control is effectively powerless.
- These factors move the probabilities of `UNRESOLVED`, `RESOLUTION_LIMITED` and the manipulation check. The Fieller test also mixes inflated variances with a raw covariance.
- Decision needed: register the multipliers, or revert to point σ.

## MINOR

- **m1. Label precedence** (`analyze.py:434-436`). Cell severity is applied at study level, so a NUMERICAL run plus `cap_hit` gives `INCOMPLETE` (case f). §5's ordered labels (unchanged by Amendment 3) give `NUMERICAL`. The consequence is the same. `MESH_FAILED` → `INCOMPLETE` is an undeclared mapping.
- **m2. Runner environment is not hermetic** (`scene_campaign.py:442`). It uses `dict(os.environ, …)`, so inherited `TOPO2D_RESUME`, `_CHECKPOINT`, `_CHECKPOINT_ONLY`, `_DIMS`, `_TOP_FACTOR` and `CUDA_VISIBLE_DEVICES` reach the job. The campaign's `job_env_common`, `job_env_keys` and `scrub_env` are ignored. Failures surface late; in smoke mode `TOPO2D_DIMS` silently changes the grid. Scrub `TOPO2D_*`, `W4_*` and `CUDA_*` first.
- **m3. E3 half-flap noses have no thickness floor.** Their original maximum thickness (6.70 mm) is below t_min (7.45 mm). Width is below t_min over the first 12.9 % of chord, and below (2+√2)Δx over the first 6.9 %. For E1/E2 elements the figure is ≤ 0.8 %. These noses sit in the slots, and `phase_core_checks` excludes them. The report does not quantify this. Disclose it, or extend the floor forward when t_max < t_min.
- **m4. "59/59" needs extra environment.** It requires `TOPO2D_WP1_TEST_SOURCE` and `TOPO2D_WP2_TEST_SOURCE` pointing at sibling worktrees (`topo2d_selftest.jl:160-181`); the default run is 43/43. The command recorded in `cpu_execution.json` omits that environment. In this branch formal runs fall back to cur-only and the CPU serialisation checkpoint; GPU checkpointing is refused.
- **m5. Missing registered outputs.** `tr00.json` and `SHA256SUMS` (§9) are not written by `analyze.py`.
- **m6. Unverified geometry can be frozen.** The formal path (`formal_context`, `scene_record`) does not refuse `verification: UNVERIFIED_OCR` sources (`geometry.py:466`).
- **m7. The TR-00 reference is trusted, not recomputed.** The analyzer takes `delta_cl` and `digitizing_uncertainty` from the RANS file (`analyze.py:115-116,327-328`). It does not recompute them from the frozen digitisation records (Amendment 1 §6 sum rule). Distinctness is checked at byte level only (Amendment 3 §6 asks for content).
- **m8. No Δt-collapse guard.** A finite blow-up that shrinks Δt ends as `STATE_TIMEOUT` → `INCOMPLETE` instead of `NUMERICAL` (`Topo2D.jl:232`).
- **m9. The CUDA construction is never exercised.** There is not even a CPU-side `isbitstype` check of the Tuple-based union.

## Angle A (geometry), verified independently on all 10 scenes

- **Sampling.** Segments 0.1332–0.9929 mm; adjacent ratio ≤ 2.898; maximum off-cap turn 3.445°. The two exempt vertices are exactly the TE corners (90°, or 102/74° and 121/59° on sharp arms). No duplicate vertices, no duplicated closing vertex. The closing edge is included.
- **Placement.** Overlap 9.000 and gap 12.000 at every joint, with the stated TE-midpoint and suction-minimum definitions. Main-element minimum z equals the declared height (100 or 80). Combined chord and incidence are recorded (E2: 379.428 mm, 14.437°; E3: 374.679 mm, 14.595°).
- **Thickening ratios** match the report: 4.5947, 8.8667, 17.7334, 3.0632, 5.9111.
- **Transcription.** The `.dat` rows equal the OCR transcript literally. For Table 3 this holds after removing 7 duplicated OCR excerpt rows. Every row carries `UNVERIFIED`. E1 uses Table 3, whose true incidence is 3.45°, the same as the single-element tests.
- **Determinism and SHAs.** Rebuilding E1, E2_h80, E3, E2_fine and E3_sharp reproduces the committed JSON byte for byte, and repeated NPZ writes are identical (this macOS host only; cross-platform float identity not shown). The campaign's scene SHAs match the files: 125 states = 96 main + 8 confirmation + 16 at h = 80 + 1 determinism + 4 DOMAIN.

## Angle B (SDF and job)

- **SDF agreement.** Python and Julia agree exactly in Float64 on 53,415 adversarial points: vertices, edge midpoints including the closing edge, horizontal rays through vertices, points near the closing edge, and interior camber points. In Float32 cell units the maximum error is 2.8e-5 mm, with no sign flips.
- **Matches the registered semantics:**
  - Column header identical to the registered 13, then `cur|nds|cv`, then per-element columns.
  - Sign `−(p+v)`; drag = Fx, downforce = −Fz; Cl = 2F/L.
  - Exact endpoint-clipped trapezoid window and half-window drift.
  - `sample_every` = 8.
  - WP2: `validate_force_box` once, then `force_readouts(…; validate_box=false)`, NaN when absent.
  - WP1 identity is mandatory; `step` counts every `sim_step!`, so `length(Δt) == step+1`.
  - Exit 42 writes a receipt and stops that configuration only at that Re.
  - Timeout and aggregate-cap receipts; `cap_hit` → `INCOMPLETE`.
- **Phase mechanism.** It applies the same delta to the ground and every element (R2 sequence with mirrors). The env name is shared with JOB-02 (NOTE n6).

## Angle C (campaign)

Matches the brief: `kind: scene` with path and SHA; 3 kernels. Formal admission requires a freeze, pins, a `PASS` LOCAL-GPU gate (C1/C2/C5/C6), a CUDA runtime and the parent-formula window. CPU smoke cannot be promoted: smoke, backend and memory are all checked. There is no harness GPU-smoke path.

## Angle D: adversarial inputs (analyzer = checker in every case, 0 diffs)

| Case | Input | Label |
| --- | --- | --- |
| (a) | Interval contains 0 at Re 1000 only | `UNRESOLVED` |
| (b) | Ranks disagree, both sides resolved | `DISCORDANT` |
| (c) | Sign agrees at Re 3000; Re 1000 resolved with opposite sign | `DISCORDANT` (Amendment 4 intends PARTIAL; see B1) |
| (d) | 7 distinct + 1 duplicate mesh SHA in E2, all cells or one cell | `INCOMPLETE` |
| (d3) | Same, in E2_sharp, all cells | `TR_UNQUALIFIED` |
| (e) | RANS file with mixed observables (thick or sharp arm) | refused (`ValueError`) in both |
| (f) | NUMERICAL + cap | `INCOMPLETE` (see m1) |
| (g) | Reference increment far from the RANS increment (out-of-band ratio) | `TR00_FAIL` → `TR_UNQUALIFIED`; with digitising uncertainty > 5 % → `TR00_PASS_SIGN` → `CONCORDANT` |

The checker imports nothing from the analyzer. Outputs are written once (`open("x")` with rollback).

## Angle E: tests and report

The 219 tests are behavioural: forgery, ordering, cap and failure transport, geometry defects. Untested or unimplemented: the remeasure equivalence, the parent pre-run, `tr00.json`, the CUDA construction, and a reachable PARTIAL. The report's claims are evidence-scoped (CPU capability only), apart from m4 and the unquantified m3.

## NOTE

1. The true Euclidean slot after thickening is 8.57 mm (4.6Δx) for E2 and 8.40/8.93 mm (4.5/4.8Δx) for E3. Rev 0's "≈ 6 cells" and the report's 6.45 cells refer to the nominal vertical gap. This is relevant to H3.
2. "N/m" is nominal (ρ = 1 kg/m³, U = 1 m/s). All configurations use common-c1 coefficients.
3. A numerical stop of configuration E2 at one Re also skips E2's h80 and DOMAIN extras: the stop key ignores height and role.
4. The domain behind the last TE is 3.35 c1 for E2/E3 vs 4 c1 for E1 (x ∈ [−2, 5] c1 from the main LE, as in T2-0).
5. Determinism is judged byte-level on readouts and the CSV SHA. It is reported, not part of the label.
6. `W4_CANONICAL_ORIGIN_M` is an absolute SDF origin in the registered job but a sub-cell delta here. Same sign of motion.
7. The leakage check covers bulk stations at 16 phases. LE and TE caps are excluded, as disclosed.
8. The WP5 loader rejects open polygons (0/20 readback), and the schema bytes differ from WP5's. Both are integration items under Amendment 4 §1.

## Verdict

**INTEGRATE_AFTER_FIXES.** The geometry, SDF, job semantics, harness boundary and analyzer/checker pair are careful, fail-closed, and match the registration wherever it is unambiguous.
- **Fix before or with integration:** M1 (`remeasure=false` plus a bit-identity test), m2 (scrub the runner environment), m4 (record the self-test environment).
- **Freeze prerequisites, tracked:** B1 (registration rewrite of the PARTIAL/required-interval rule, then a code and test update), M2 (pre-run estimator and record schema), M3 (register or drop the upper-limit σ), and m1, m3, m5, m6, m7.

**GPU smoke (CPU→GPU): yes, with conditions.**
- Invoke the job directly; there is no harness GPU-smoke path.
- Use `--project=julia/CFDSDFWaterLilyT4`, `TOPO2D_BACKEND=cuda`, `TOPO2D_SMOKE=1`, and `W4_SELECTED_GPU_UUID` set to the device actually present.
- Clean environment: no `TOPO2D_CHECKPOINT`, `TOPO2D_RESUME`, `TOPO2D_DIMS` or `TOPO2D_TOP_FACTOR` left set.
- Write output to scratch, never `docs/evidence`.
- Run E1, then E3 (largest tuple), at the formal grid for a few hundred steps. Record: compile time, acceptance of the ~15.7 KB kernel parameter, ms/step for measure vs mom_step, and finite forces close to the CPU values.
- Label the result capability-only: not LOCAL-GPU-01, not TOPO-2D-00 evidence.
