# Opus source review 2 of WP4 (PR #89, 0741a474), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions: `docs/topo2d00_registration_2026_11_01.md` Amendment 7 and `04_topo2d_waterlily.md` Amendment 6.

# WP4 source review, round 2 (verification): feat/gen01-w1-04-topo2d-waterlily @ 0741a474, Draft PR #89

Read-only. Worktree `/Users/sota/projects/FomulaTMU/CFD2026_09-wp-04-topo2d-waterlily`, tree clean before and after my runs.

**What I ran myself**
- `pytest -q tests/topo2d00`: **278 passed** (65 s).
- `julia --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl <scratch>`, with no TOPO2D/W4 environment: **86/86** (57.7 s). E1/E2 remeasure identity over 9 and 14 steps; WP1 resume uses the branch's own `gen01/Checkpoint.jl`; `tuple_union_isbitstype` holds for E1/E2/E3; the Δt-collapse job exits 42 with a NUMERICAL receipt; WP2 is recorded as `NOT_INTEGRATED_CUR_ONLY`.
- `SHA256SUMS` in `wp04_validation_amend5/`: 70/70 OK, and every listed file is tracked.
- Scratch scripts: 27 adversarial label cases, 400 random payloads (analyzer vs checker), DOMAIN probes, and an AR(1) Monte Carlo through `prerun_window.estimate`.

## Round-1 findings

| ID | Status | Evidence |
| --- | --- | --- |
| **B1** | **CLOSED** | See below. |
| **M1** | **CLOSED** (CPU) | See below. |
| **M2** | **PARTIALLY CLOSED** | The machinery exists, but the estimator usually fails to produce a window. See N2. |
| **M3** | **CLOSED** | See below. |
| m1 | CLOSED | W NUMERICAL + cap → NUMERICAL; MESH_FAILED cell + cap → NUMERICAL; NUMERICAL cell + INCOMPLETE cell → NUMERICAL; INCOMPLETE or DEGENERATE alone → INCOMPLETE. Analyzer = checker. |
| m2 | CLOSED | `job_environment` (`scene_campaign.py:134-144`) drops the three prefixes before `scrub_env`/common/run env. The polluted-env smoke kept 840×824. |
| m3 | CLOSED | E3 `nose_thickness` metadata (registered 0.129/0.069; measured 12.61 %/6.85 %) and the figure caption. |
| m4 | CLOSED | 86/86 with no sibling env; the command and environment policy are recorded. |
| m5 | CLOSED | Four paths reserved with `open("x")`, with rollback. |
| m6 | CLOSED | `require_verified_geometry` is called in `formal_context` and `load_formal_inputs` (`:767-775`). |
| m7 | CLOSED | Re-hash, Cp integration, per-surface content distinctness, summary check at 1e-12. |
| m8 | CLOSED | `check_timestep` (`Topo2D.jl:227-237`) floor eps·max(1,t_grid), about 7e-3 at 520 c₁/U. A real-job exit 42 is tested. |
| m9 | CLOSED (CPU) | `isbitstype` holds for E1/E2/E3. |
| NOTE 3 | CLOSED | Stop key = (configuration, Re, height, role), at `:494` and `:668`. |
| Open polygon | CLOSED | Stated in the schema and in the Python and Julia docstrings. |

**B1 detail.**
- The per-Re rule (`analyze.py:580-588`, `check.py:539-547`) uses as required intervals W Δ12 and Δ23 at that Re, plus R Δ12 and Δ23 for every qualified cell (worst case).
- The combination rule (`analyze.py:627-638`, `check.py:603-610`) is exactly Amendment 5 §1.
- Round-1 cases re-run: (a) UNRESOLVED, (b) DISCORDANT, **(c) CONCORDANT_PARTIAL** (discordant Re either 1000 or 3000), (d) INCOMPLETE, (d3) TR_UNQUALIFIED, (e) refused, (f) NUMERICAL, (g) TR_UNQUALIFIED / CONCORDANT.
- All 9 labels are reachable in both. PARTIAL is also reachable through a Δ23 flip at one Re.
- 400 random payloads: 0 label mismatches, 0 numeric diffs.

**M1 detail.**
- `static_step!` calls `sim_step!(sim; remeasure=false)` (`Topo2D.jl:239-247`).
- Bit-identity against a reference path that keeps remeasure=true covers u, p, Δt, force rows and window means for E1 and E2.
- The fingerprint contract now includes `remeasure=false` and `timestep_floor`.
- Checkpoint resume is still bit-exact: fields, rows and windows, through WP1.

**M3 detail.**
- `wstat` and `paired_w` set σ = max(A, σ_B) as point values, with a t(.95, P−1) interval. No UCL or Bonferroni remains.
- DOMAIN at P=2 detects a shift: a 0.003 shift gives z = 3.67 → DOMAIN_SENSITIVE; zero shift gives CONSISTENT. Analyzer = checker.
- The Fieller test for RESOLUTION_LIMITED uses max(A,B)²/P variances with the raw paired covariance and df 3. That is PSD-safe and conservative (the effective correlation can only fall).

## New findings

**N1. MAJOR, registration level (freeze prerequisite): DISCORDANT can come from an unresolved E1↔E3 ordering.**
- Amendment 5 §1 marks a Re DISCORDANT when "the E1/E2/E3 ranking differs", but only Δ12 and Δ23 are required intervals.
- When Δ12 and Δ23 have opposite signs (E2 best), the full ranking depends on the E1↔E3 point means. Both implementations follow the registration literally (`analyze.py:585`, `check.py:544`).
- Constructed case (h′): all four required intervals are resolved with matching signs. The E1→E3 interval is [−0.00026, 0.00046] in W and [−0.0077, 0.0067] in R, with opposite point order. The result is DISCORDANT at both Re, so the study is **DISCORDANT** on noise.
- This is plausible in practice: the E3 half-flaps are 17.7× thickened and have sub-t_min noses.
- Fix: compare the ranking only on pairs resolved on both sides, or make E1↔E3 required when the order is non-monotone (UNRESOLVED if it is not resolved).

**N2. MAJOR, registration plus code (freeze prerequisite): the pre-run estimator usually refuses on a stationary series.**
- Synthetic AR(1): mean 0.17 N/m, τ = 1 c₁/U, dt = 0.05, known S0 = σ²·dt·(1+φ)/(1−φ). 200 seeds per row.

| W_true (c₁/U) | refused: burn-in | refused: W > 400 | W median when accepted | W median from max of point S0 |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 26.5 % | 8 % | 150 | 100 |
| 100 | 26.5 % | 28 % | 250 | 150 |
| 150 (budget assumption) | 26.5 % | 45.5 % | 300 | 175 |

- Results were similar with a 30 % transient and with τ = 3.
- Causes:
  - (a) "Within ±SE of the later block means" (`prerun_window.py:70`) accepts a stationary candidate only when |t_{n−1}| ≤ 1/√(n+1), which is P ≈ 1/3. Only three candidates are effective (start 300 has one later block), and there is no fallback.
  - (b) S0 is the maximum of five per-length χ² 90 % UCLs (`:83`). At L = 80 there are only 3–4 df, a factor of 3.8–5.1, so W is about 2× the true value.
  - (c) `parent_window` **refuses** W > 400 (`scene_campaign.py:290`), but Amendment 5 §4 says "capped at 400".
  - (d) Once WP2 is integrated, the first sample falls after step 1. The start-0 candidate is then always skipped, so B ≥ 100.
- Consequence: the campaign cannot start in 35–72 % of stationary cases. Even when it starts, a window of about 2× pushes the WaterLily total past the 40 GPU h cap.
- The existing tests are deterministic arithmetic only.
- Fix: register an acceptance band with a fallback for B, and an S0 rule with adequate df (or point S0). Then either clip W to 400 or register what happens on refusal.

**N3. MINOR (fix before or with integration): the DOMAIN control diverges between analyzer and checker.**
- An incomplete DOMAIN row is judged by the analyzer (DOMAIN_SENSITIVE) but is NOT_JUDGED by the checker.
- A DOMAIN state that timed out (readouts None) or has a single phase makes the analyzer **refuse the whole analysis** (`analyze.py:618-621`, `select_runs`). The checker skips it.
- A descriptive control must not block the label. Align on the checker's behaviour and add a test.

**NOTES**
1. The seven thickened scene SHAs changed. This is metadata only: polygons, probe stations, dx, ground and height are identical to fae6c0a8, and the three sharp scenes are byte-identical. WP5 must re-bind the scene SHAs.
2. Per-sample `force_row` still evaluates the polygon SDF over the full domain (pressure and viscous force per body) every 8 steps. Add "ms per force sample" to the GPU smoke.
3. Secondary h = 80 rows (16 runs) are validated but produce no analysis output.
4. The E1 reference uncertainty is dropped when E1 uses `cl_curve`. This is literal to Amendment 1 §6 (double-element only).

## Regressions (fae6c0a8 → HEAD)
- The job script is unchanged. The `Topo2D.jl` diff is remeasure, the Δt guard and metadata only.
- Harness tool files are byte-identical to e3dcdf61.
- Against integration, `git diff ed4a05a6 HEAD` is additions only.

## Report honesty
- 278 tests and 86/86 reproduced.
- Full suite: 3482 + WP1 197 (195 `test_local_gpu*` + 2 reverify) + WP3 203 + WP4 278 = **4160**, with 74 skips as at base. Not re-run by me; the log reads 4160/74/0.
- The GPU runbook matches round 1's conditions. Nothing is claimed beyond CPU.
- One overstatement: the README presents the cap refusal as registered, but the registration says "capped" (N2c).

## Verdict

**INTEGRATE_AFTER_FIXES.**
- The round-1 code findings are fixed faithfully, and analyzer = checker holds across adversarial and random inputs. The job and harness boundaries are unchanged.
- **Before or with integration:** N3.
- **Freeze prerequisites (registration amendment, then code and tests):**
  - N1: the rank comparison on unresolved pairs.
  - N2: burn-in band and fallback, S0 df/UCL rule, cap vs refusal, and B with WP2's first sample.
- **Add to the GPU smoke:** force-sample timing (NOTE 2).
