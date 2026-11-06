# GRAD-00 (#23): does swapping WaterLily's convection scheme λ make the forward-AD tangent bounded? — draft rev 0

要約（日本語）：WaterLily の issue #358 は、QUICK の内側の bound `10c−9u` を外すか、cds／vanLeer にすると ForwardDiff の導関数が中心差分と一致する、と報告しています。本リポジトリの DIAG1〜5 と GRAD-TA1 は QUICK とその tie 平均版しか試していません。GRAD-00 は、凍結済みの GRAD-TA1 スクリプトの λ だけを差し替えて、v17 flow_24 の FD-08 の 4 方向で tangent の有界性と FD との一致を測る、探索的で安価な実験です（Kaggle T4 で 10 GPU 時間以下）。#62 の NO-GO 分岐として 2026-10-16 に事前に置かれた「滑らかな対流スキーム」の試験であり、DIAG の追加ではありません（phase_plan への記録はユーザー決定 (d)）。成功しても、勾配が主線に乗るのは定常領域に限られます（GEN-01 rev 3.1 §3.6）。

Status: **draft rev 0 (2026-11-01), not run.** Class when run: `EXPLORATORY_COMMITTED` (#23 is off the critical path; R5 unchanged). Rows in `docs/exploratory_index.md` before each run. Cap: 10 GPU h on Kaggle T4 (or the LOCAL-GPU-01 backend once it passes), no extension.

## 1. Question and hypotheses

- **Q.** With the convective scheme replaced, is the forward-mode tangent of the registered measurement (candidate-only force, window [80, 120] tU/L, flow_24, v17, Float32) bounded over the whole window, and does its window-mean tangent agree with the central finite difference of the same measurement under the same scheme?
- **H1 (from issue #358).** The unbounded growth is caused by the branching inner bound `median(10c−9u, c, d)` of `quick`; removing it, or using `cds` or `vanLeer`, gives a bounded tangent that agrees with FD.
- **H2 (from DIAG5 and GRAD-TA1).** The growth is not only the limiter: tie-averaging the limiter derivative removed one mode but another grew (`GRAD_TA1_BLOCKED`), so a different non-smooth kernel (the μ₀ threshold, the sign-consistency branch in `measure!`) may still produce growth. GRAD-00 can refute H1 but not fully confirm it.
- **Not asked.** Anything at Re above 80, anything about the unsteady regime, reverse mode (Enzyme PR #285), or Float64.

## 2. What is reused (by hash, not edited)

- `scripts/waterlily_grad_ta1_2026_10_15.jl` (frozen by GRAD-TA1) as the template: the G2 bridge semantics (flow_24, `sim_step!` with remeasure, warm-up step, force sample every 8 steps, −(pressure+viscous), drag = Fx, downforce = −Fz, window [80, 120], φ(α) = φ₀ + α d, Dual width 1, watchdog every 100 steps, BLOCKED at a non-finite or > 1e30 tangent, 8× wall abort). GRAD-00 copies it to `scripts/waterlily_grad00_lambda_2026_11.jl` and changes only: the λ argument per arm, the output labels, and the addition of the two FD primals per direction (section 4).
- The v17 canonical state and the four FD-08 v2 directions (`D0_interface_offset`, `D1_filtered_seed11`, `D2_filtered_seed2026`, `P1_upstream_lobe`) with their registered raws and SHA-256s, and the FD-08 formal ε plateau per direction (`docs/evidence/fd08_v2_formal_2026_10_07_amend3`).
- `scripts/verify_grad_g2_terminal.py` for the index/terminal checks (unchanged name `g2_run_index.json`).

## 3. Arms (one λ per arm; each arm is one kernel)

| arm | λ passed to `WaterLily.Simulation(...; λ=λ)` (routing checked as in GRAD-TA1 Amendment 2) | expectation |
| --- | --- | --- |
| A `quick` | WaterLily 1.8.0 `quick` | replication control: BLOCKED as in DIAG5 (onset ≈ step 838 for D0) |
| B `quick_nobound` | `quick_nobound(u,c,d) = median((5c+2d−u)/6, c, d)` exactly as in issue #358 (the inner `median(10c−9u, c, d)` bound removed, outer limiter kept; defined in `scripts/quick_nobound.jl` and included into `WaterLily` like `quick_tie.jl`) | H1: bounded, agrees with FD (#358, Float64 spinning cylinder: 0.4137 vs 0.4138 at t = 2, 0.4795 vs 0.4796 at t = 4) |
| C `cds` | WaterLily 1.8.0 `cds(u,c,d) = (c+d)/2` (confirmed present at tag v1.8.0 in `src/Flow.jl`) | H1: bounded, agrees with FD (#358: 0.2437 vs 0.2437); the primal is less dissipative and may be less stable at flow_24 (recorded) |
| D `vanLeer` | WaterLily 1.8.0 `vanLeer` (confirmed present at tag v1.8.0; it branches on `c ≤ min(u,d) || c ≥ max(u,d)`) | H1 (#358: 0.5101 vs 0.5101) |
| E (side arm) `quick` on WaterLily 1.10.0 | a separate Julia project `julia/CFDSDFWaterLily110/` with the same job; v1.9.0 made `median` branch-free (`max(min(a,b), min(max(a,b), c))`) and v1.10.0 says "the QUICK limiter no longer branches", but the inner `10c−9u` bound is still present in v1.9.2, v1.10.0 and master | descriptive: does the branch-free median change the behaviour without removing the bound; feeds user decision (j) on the version pin |
| F (precision arm) | arms A and B in **Float64 on the CPU** (Mac, 10 threads) for directions D0 and D1 only, registered window; issue #358 shows Float32 derivatives move by 20 % under ±10 ulp changes of ν, and #351 runs WaterLily's own AD test in Float64 | separates Float32 round-off noise from the limiter mechanism; cap 60 CPU h on the Mac (a Float64 flow_24 run is estimated at 1-2 h there; the 4070 Ti's FP64 rate is 1/64 of FP32 and is not used for this arm) |

Arm order: A, B, C, D, then E and F. Arms are independent kernels so a BLOCKED arm does not stop the others. The project's bodies are static in these runs (placement fixed), so the moving-body pressure-solver source that b-fg suspects in #358 is not in scope.

## 4. Runs per arm and readouts

Per arm and per direction: 1 plain primal (the λ changes the primal flow, so the plain run is re-done per arm), 1 Dual run (tangent), and 2 primals at ±ε (the FD-08 plateau ε of that direction) for the central difference under the same λ. Per arm: 1 + 4 × 3 = 13 flow_24 runs ≈ 13 × 110 s ≈ 25 min on a T4 (Dual runs cost 2-3× a plain run; budget 1 h per arm, 5 arms ≈ 5 GPU h, cap 10).

Readouts: watchdog (max |tangent| over u and p every 100 steps, argmax cell), force history with tangents, window-mean tangent of fx and fz per direction, the central FD of the window means, the primal window means of the arm vs arm A (how much the scheme changes the flow), onset step and cell if BLOCKED, wall and VRAM.

## 5. Labels (descriptive; exploratory)

Per arm and direction: `BOUNDED` (finite, < 1e30 through step N_end) or `BLOCKED` (onset step recorded). For BOUNDED directions: `AGREE` if sign(tangent) = sign(FD) and |tangent/FD − 1| ≤ 0.1 for both fx and fz (the 0.1 is the FD-08 5 % profile doubled for the Dual/FD pair; descriptive), `DISAGREE` otherwise, `NOT_EVALUABLE` if |FD| < 3 × the FD-08 plateau spread.

Per arm: `BOUNDED_ALL` (4/4 BOUNDED), `PARTIAL`, `BLOCKED_ALL`.

**Pre-written rule for the next step (fixed now, exploratory results do not set thresholds).** If at least one of arms B-D is `BOUNDED_ALL` with `AGREE` in ≥ 3 of 4 directions, a GRAD-01 registration draft is written: Carter weak and strong checks at a steady Re (v18 at Re_L 250 after RE-01's Stage 0 shows it steady), with thresholds taken from GEN-01 rev 2 §3.4's committed OC, not from GRAD-00's numbers. Otherwise #23 stays parked and GEN-01's main line is unaffected (it is gradient-free by design).

## 6. Relation to PROC-01, #23 and R5

- Exploratory: its labels feed no gate or flag; they feed one pre-written branching rule (section 5) on whether to draft a registration.
- #23's 2026-10-16 decision ("no further DIAG rounds") targeted diagnoses of the implemented scheme. GRAD-00 is the pre-declared "smooth convection scheme" branch of #62's NO-GO path (phase_plan 2026-10-16), applied to #23. Recording it as such in phase_plan is user decision (d) in GEN-01 rev 3.1 §10.
- R5 is unchanged: no gradient backend enters the critical path; GRAD-00 runs beside RE-01 Stage 0 on the Kaggle GPU quota.

## 7. Procedure

1. The pinned WaterLily 1.8.0 `src/Flow.jl` defines exactly three schemes, `quick`, `vanLeer` and `cds`, and `Flow`/`Simulation` take `λ` as a keyword (routing through the constructor as GRAD-TA1 Amendment 2 found); write `scripts/quick_nobound.jl` and the arm script; CPU dry run (`G2_BACKEND=cpu`, 20-step preflight per arm: primal bit-equal to arm A only for arm A's own repeat, finite tangents for every arm).
2. Exploratory_index rows (one per arm) before pushing; one kernel per arm; download, `verify_grad_g2_terminal.py`, archive under `docs/evidence/grad00_lambda_2026_11/` with `SHA256SUMS`.
3. Write the result note `docs/issues/23_grad00_result_2026_11.md` once (labels, the section-5 rule applied, what was not tested).

## 8. What is not claimed

A bounded tangent at Re 80 on flow_24 says nothing about Re_c 3e3, about the unsteady regime (where time-averaged sensitivities of chaotic flow diverge regardless of the scheme), about reverse mode, or about optimisation use (that is GRAD-01 and the Carter contract).

## Amendment 1 (2026-11-06, after Codex WP3 attempt 1, draft PR #86)

1. **ε and spread are now defined.** Rev 0 wrote "the FD-08 plateau ε / plateau spread"; the amend3 evidence records no quantity under that name (it records six-point Model A calibration fits and three formal interior ε per direction). Per direction d: **ε_d = the largest of the three FD-08 v2 formal interior ε** (`formal_analysis.json` comparisons, 24/24 PASS; 3.9716 mm, identical for the four directions, and the smallest relative errors of the three); **spread_d[fx] = the Model A calibration standard error of the drag gradient `se_g_n_per_m`, spread_d[fz] = the same for downforce** (`formal_criteria.json` calibration_binding.fits). Values and source SHAs: `docs/evidence/grad00_lambda_2026_11/reference.json`, generated by `scripts/grad00_reference_from_fd08.py` (`--check` recomputes and compares). Fixed before any GRAD-00 run. The NOT_EVALUABLE floor 3 × spread is 0.007–0.031 N/m against FD-08 gradients of 0.064–0.385 N/m, so every direction is evaluable if the λ swap leaves the gradients of that order (an expectation, not a criterion).

   | direction | ε [mm] | spread fx (drag SE) [N/m] | spread fz (downforce SE) [N/m] | FD-08 g drag / downforce [N/m] |
   |---|---|---|---|---|
   | D0_interface_offset | 3.9716 | 0.00334 | 0.0206 | −0.104 / 0.801 |
   | D1_filtered_seed11 | 3.9716 | 0.00234 | 0.00332 | −0.064 / −0.106 |
   | D2_filtered_seed2026 | 3.9716 | 0.00479 | 0.00299 | −0.170 / −0.092 |
   | P1_upstream_lobe | 3.9716 | 0.00588 | 0.0102 | −0.214 / −0.385 |

2. **vanLeer (arm D) preflight finding and the optional arm D′.** On CPU (1.8.0, Float32 and Float64) the Dual run of arm D is non-finite within 20 steps; scalar reproduction `vanLeer(Dual(1,1), Dual(1,2), Dual(1,3))` → NaN (ForwardDiff's comparison of Duals with equal values falls through the extremum test and divides by `d − u = 0`; source lines recorded in the WP3 validation). Arm D is kept as written (it will block at preflight on the T4 too, deterministically, costing minutes) and labelled by the rule. An **optional arm D′ `vanLeer_safe(u,c,d) = ForwardDiff.value(d) == ForwardDiff.value(u) ? c : vanLeer(u,c,d)`** (a value-only tie guard; in plain arithmetic the stock extremum branch already returns c at a tie, so the primal is bit-identical to vanLeer) is pre-registered: rendered with the others, **run only if neither B nor C is BOUNDED and AGREE on all four directions**; it carries the same labels and joins B–D as a candidate for `GRAD01_DRAFT_ALLOWED`. If D′ is not run its arm is `NOT_RUN`, which is not `INCOMPLETE`.
3. **Evidence-class notes from attempt 1.** E (the WaterLily 1.10.0 side project) is a whole-version comparison (the `uλ`/`u0` API, projection weights, Poisson tolerance defaults, boundary conditions and force reduction all differ), so E cannot isolate the effect of the median bound and stays descriptive. F runs on CPU with ForwardDiff 1.4.6 against 1.4.5 on the T4, so F keeps a CPU Float32 control and the analyzer records backend and runtime versions as confounds. The 5-run `verify_grad_g2_terminal.py` is not applied to the 13-run arms; the WP3 analyzer has its own index/SHA checks.
4. **Budget from TA1** (plain 138.9 s on the T4): 9 primals + 4 Dual runs at 2–3 × plain ≈ 39–49 min per arm plus setup/JIT ≈ 1 T4 h per arm; A–D′ ≈ 5 h, E +1 h; the cap stays 10 GPU h. Kernel timeout 10800 s as TA1 (an upper bound, not a target).
5. The CPU 20-step preflight results of attempt 1 (A/B/C/E/F pass, D non-finite) are software-capability evidence (EXPLORATORY_COMMITTED), not BOUNDED/AGREE labels, and say nothing about the T4 or about the registered window.
