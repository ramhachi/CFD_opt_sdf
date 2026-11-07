# Opus source review 1 of WP2 (PR #84, afac79ed), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim (the CPU cylinder probe script is in the reviewer's scratchpad, not committed). Decisions: `docs/force00_force_readout_gate_2026_11_01.md` Amendment 1 and `02_force00.md` Amendment 3.

# Source review: WP2 FORCE-00 (feat/gen01-w1-02-force00, HEAD afac79ed, Draft PR #84)

Read-only. Paths are relative to `/Users/sota/projects/FomulaTMU/CFD2026_09-wp-02-force00`. I re-ran the following myself: the Julia self-test (78/78 PASS, 39 s), `pytest tests/test_force00_gate.py` (44/44), a `cmp` of the job `.diff` against a fresh `git diff --no-index` (identical), `git diff e3dcdf61 -- julia/CFDSDFWaterLily/src` (empty), and SHA checks of every `final/` record against the HEAD sources (all match). I also ran one probe of my own, described under B. All 110 changed paths are additions, and no pre-existing file is modified.

## Findings

### MAJOR

**M1 (D). With the registered evidence, the gate can never adopt a readout, and its single write is spent on an INCOMPLETE result.** See `scripts/force00_gate.py:432-433, 446-450, 457-465`.
- `sigma_d_n is None` appends to `missing`, and any non-empty `missing` makes the whole gate return INCOMPLETE with `adopted_readout = NONE`. I confirmed that UNC-01 `analysis.json` `grids.flow_32.differences` has no `v18__camber_m19.7` entry. So once F1–F3 are complete and C1–C4 all pass, the result is still INCOMPLETE/NONE. `test_incomplete_runs_and_missing_sigma` asserts exactly this outcome.
- Spec §4 puts C5 outside the PASS rule (PASS = C1+C2+C3+C4). C5 is "descriptive; reported", and the code's own `test_c5_descriptive_large_change_does_not_block_adoption` treats it that way. Amendment 1 asks for C5 to be INCOMPLETE, not for adoption to be blocked.
- `write_gate` writes `gate.json` whatever the status. Running the gate once before F3 finishes, or with a σ still missing, therefore locks the evidence root permanently at INCOMPLETE.
- `except (FileNotFoundError, KeyError)` (`:395`) routes reference KeyErrors into the same path.
- Fix:
  - Keep C5's status (INCOMPLETE without σ) inside `criteria.C5`, but leave it out of the adoption-blocking set.
  - Refuse to write `gate.json` (exit non-zero) while any C1–C4 input is missing.
  - Or obtain an owner decision naming the σ_d source.

  This must be fixed before the gate is frozen or run. It does not affect the GPU runs.

### MINOR

**m1 (B/D). The CV box is an unregistered free parameter, and the gate does not require it to be consistent.** The job takes `FORCE00_CV_BOX` from the environment. Neither the spec nor the code fixes a box for flow_24 or flow_32. `read_run` (`force00_gate.py:258-262`) checks only the inset, so the 8 F1 phases, the F2 phases, or the F3 parent/candidate pair could each use a different box. That would contaminate C3 (phase SD) and C5 (paired differences) for R_cv. Fix: register one box per grid, and require identical lower/upper bounds per (run, grid) in the gate.

**m2 (C/D). GPU-run provenance is not tied to the implementation.**
- The job summary does not record the SHA of `gen01/Force00.jl`, the job, or the dispatcher, and `read_run` does not check them.
- U1 is tied to the checkout (`validate_uniform_provenance`), but F1–F3 are not. GPU numbers from a pre-fix `Force00.jl` would be accepted.
- Fix: add the three SHAs to the summary and require that they match the U1 record. This changes only the job, so U1 stays valid.

**m3 (A/B). The default `box=nothing` path is not fail-closed, and closure relies on a proxy check.**
- In `Force00.jl:36-40, 60-88`, the default region `inside(p; buff=2)` closes only if the body's band never reaches the faces at index 3 or N−1.
- If the body touches the domain edge, or the scene includes a ground half-space (as the job's combined body does), each grid column picks up a spurious ±p, and nothing checks for this.
- With an explicit box, closure holds by construction only if μ₀ = 1 on both end faces of every line. That is currently inferred from a sampled scene SDF ≥ 4, which, as the docstring itself admits, is not a certificate for a non-metric GridSDF.
- Fix: make `box` mandatory outside the tests. Assert `μ₀ == 1` exactly on the box-boundary normal faces; that is the exact closure precondition, independent of SDF quality. Any change to `Force00.jl` requires re-running U1, which takes about 2–3 minutes.

**m4 (B/E). R_cv has no check on a solved flow, and its C2 result carries no information.**
- Under p ≡ 1 and u = u⁰ = 0, R_cv is exactly 0 by construction: pressure cancels on a closed box and every other term vanishes. So "R_cv max 0.0" and a C2 PASS for R_cv say nothing about the body.
- The affine/quadratic self-test is a sound analytic check of each discrete term: the face-midpoint quadratic errors cancel between opposite faces. But it is kinematic only and never touches the BDIM solver.
- My probe (`/private/tmp/claude-501/-Users-sota-projects-FomulaTMU-CFD2026-09--claude-worktrees-github-local-status-review-66bea1/71276ae4-ff30-4473-8ce0-489d7e53d1c8/scratchpad/probe/cv_box_probe.jl`, CPU) closes most of this gap. Setup: 2D cylinder, D = 16, Re 100, 1500 warm-up steps, then 800 sampled steps.
  - R_cv mean drag was 12.823, 12.829 and 12.826 across three nested boxes, a spread of 0.05 %. So signs and time levels are self-consistent.
  - R_cur was 11.400 and R_nds 11.397. R_cv is therefore +12.5 % above R_cur, the same direction as #293.
  - The instantaneous lift differs by about 12 % between boxes, but this averages out over the window.
- Suggestion: add a short box-independence test like this to the self-test. Also note that at coarse resolution, R_cv may land near the 15 % HOLD band in C4.

**m5 (D). F3's R_cur is not byte-regressed, although the references exist.** Registered FID-01 WaterLily CSVs exist for the parent and `camber_m19.7` at k7–k10 (`docs/evidence/fid01_2026_10_21/wl/kernel_output/fid01_f32k{7..10}/states/*/flow_32.forces.csv`). Adding them to the C1 rows is cheap and would catch a wrong state or phase in F3.

**m6 (C). Per-sample timing has changed.** `wall_seconds` and `peak_vram_bytes` now include the readout overhead. `force_readouts(...; body=candidate)` also recomputes the legacy pressure and viscous forces that the job has just computed (`job:177-181` vs `Force00.jl:249-255`). This is harmless for C1, which compares only the CSV, but the timing fields are no longer comparable with registered runs. Either state this, or pass the job's `total` through.

### NOTE

- **n1 (B). Time levels are correct.** Forces are still sampled after `sim_step!`, i.e. after `mom_step!` (`job:173-181`, unchanged). At that point `u⁰` is the start-of-step velocity and `Δt[end−1]` is the step actually taken; `Δt[end]` is the next CFL step.
  - The fluxes use the end-of-step u and the stored corrector pressure p₂. p₂ is the projection pressure of the predictor state, not the step-effective (p₁+p₂)/2.
  - The storage term is centred at n+½. The resulting first-order offset averages out over the window, as the probe confirms. This is the same as the #293 recipe.
- **n2 (D).** The gate requires `gpu_name == "Tesla T4"`. That is consistent with C1's byte-identity requirement, but the spec also allows "or LOCAL-GPU-01". In practice, F1–F3 must run on Kaggle T4.
- **n3 (D). Adversarial inputs:**
  - A shuffled header with a correct SHA raises ValueError, and `gate.json` is not written.
  - Shuffling the 13 legacy columns while keeping the header gives a C1 FAIL.
  - Swapping the nds and cv data columns is undetectable (inherent).
  - A closure exactly at the threshold PASSes (`<=`).
  - C4 at exactly 15 %: 11.5 vs 10.0 gives PASS, but a readout that is exactly 1.15× in every phase evaluates to 0.15000000000000002 and gives HOLD. The boundary is fuzzy by one ulp.
  - A sign flip gives FAIL_SIGN, which the spec does not define but is a defensible choice.
- **n4 (E).**
  - The self-test's linear-pressure check (`selftest.jl:41-42`) checks the sign only. An exact magnitude check by summation by parts (the ∇p-weighted sum of 1−μ₀) is cheap.
  - `test_cpu_validation_reports_are_not_discovered` is close to tautological: the gate never recurses, and `evaluate` never writes.
- **n5.** The sphere radius of 0.5 m is hard-coded in the gate (`force00_gate.py:238`) and is tied to the Julia constant only through a source hash.
- **n6 (C).** The copied job keeps the LOWDIM-02A header, usage message and `W4_JOB_DONE` text (`job:1-3, 31, 394`). For F1 launched through the dispatcher at flow_24, the DONE file still says "LOWDIM-02A flow_32".
- **n7.** The absolute 1e-12 closure bound does not scale with body size. U2 at R32 already reaches 9.1e-13, because round-off grows with the number of band cells. The gate itself uses relative thresholds, which is correct.
- **n8 (A). GPU compile is unverified.**
  - At risk are in-kernel `WaterLily.interp` (with `@view(varr[..,i])` and `size(varr)[1:D]`), Type arguments, and Float64 arrays on T4.
  - These patterns mirror WaterLily's own GPU-supported code (`interp.(x, Ref(u))`, `loc(0,I,Tp)`), and all reductions use backend `sum`, `maximum` or `minimum`, with no scalar indexing.
  - A failure would appear either in `validate_force_box`, before the warm-up step, or at step 8. It would not appear hours into a run.

### Verified correct

- **A.** `_force00_nds` is exactly the #369 form: in 1.8.0, `μ₀[I,i]` is the lower face of cell I (`loc(i,I) = I−1.5−½eᵢ`), so the difference is the cell's outward area vector, with the same sign as the legacy `n·kern`. Values are promoted to Float64 before subtraction. The viscous term is `−2ν S·nds` over the same region, the body force is `−(p+v)`, drag = +Fx, downforce = −Fz. With the validated box, closure holds for any candidate, including Candidate C's blended μ₀ next to the ground. U1/U2: R_nds max 9.10e-13 over 104 placements, against R_cur 20.0 / 33.5 (2.1 % of planform area).
- **B.** CV flux and storage signs are correct, the normal component is interpolated to the face exactly, and 2D/3D are both supported. `validate_force_box` fails closed on the 2-cell domain inset, on scene SDF < 4 at any face point (ground included), on candidate support outside the box, and on empty or non-finite support.
- **C.** The `.diff` is the exact delta: extra columns, the box environment variable, the include, the arity of `interpolate_force_row`, and the box fields in the summary. Window, phase, hash checks and cadence are unchanged. The regression compares the registered job against the variant (not a self-comparison): both give 13-column SHA `c48e92cb…`, and all flow arrays are byte-identical afterwards. The flow_24 dispatcher reproduces the registered `waterlily_xfid_candidate_c_job.jl` computation.
- **E.** The tests are behavioural. Determinism holds (`058acdc8…` twice). Full suite 3528/74/0 (JUnit: 44 gate tests + 2 input tests). The report states clearly that F1–F3 and the #293 7–9 % question are unmeasured.

## Verdict

**INTEGRATE_AFTER_FIXES.** The mathematics and the solver-side code are sound. The R_nds form, the staggering, the signs, Float64 accumulation, CV term signs and time levels, and the job delta and its byte regression all check out. My solved-flow probe shows R_cv is self-consistent across boxes to 0.05 %.

Fixes before the gate is frozen or run:
- **(1) M1, required:** remove C5 and σ absence from adoption blocking, and do not write `gate.json` while C1–C4 inputs are missing.
- **(2) m1:** register one box per grid and make the gate require identical boxes across phases and pairs.
- **(3) m2:** record the SHAs of `Force00.jl`, the job and the dispatcher in the job summary, and check them in the gate.
- **(4) m3:** require a box, plus an exact `μ₀ == 1` check on the box faces (then re-run U1).
- **Recommended:** m5 (F3 byte regression) and m4 (box-independence self-test).

**GPU (F1–F3) as is: yes, safe to run for solver integrity and the R_cur regression.**
- The readouts are read-only, `flow.f` is restored, and on CPU the 13 columns and all flow arrays are byte-identical.
- The new kernels have not been compiled on a GPU. Any failure would surface before step 1 or at step 8, so the cost is a short wasted session, not wrong data.
- Conditions:
  - Choose and record one `FORCE00_CV_BOX` per grid, and use it for every phase and both states.
  - Launch flow_24 through `waterlily_force00_dispatch.jl`.
  - Run on Kaggle T4 only.
  - Do a short single-phase smoke run first.
  - If m2 or m3 change the job or `Force00.jl`, apply those changes before the GPU runs, so the GPU outputs come from the final code.
