# FD-06 (#37): where the remaining 5–9% plateau deviation comes from

- Date: 2026-10-01. Evidence class: **diagnostic only** (CPU runs of the registered flow_24 / v17 case; short horizons
  tU/L ≤ 20; not qualified force values). The registered FD-06 T10/T11 FAIL, criteria and thresholds are unchanged.
- Data: `docs/evidence/sdf_native_fd06_diagnosis_2026_10/` (all raw CSVs, `MANIFEST.sha256`).
- Scripts: `sdf_native_fd06_frozen_flow_response.jl`, `…_frozen_flow_tiny_eps.jl`, `…_frozen_flow_analysis.py`,
  `sdf_native_fd06_jitter_cpu_probe.jl` (arbitrary-scale and white-noise perturbations, optional pressure tolerance and
  Float64 switches). Result of FD-06: [`37_fd06_result.md`](37_fd06_result.md).

## Summary

1. **The force-integral map is not the cause.** With the body normal floor (τ = 0.25) the pressure/viscous force
   integral on a frozen flow responds smoothly and linearly to perturbations, down to ε = 1e-8 m and also to white φ noise.
   Without the floor (τ = 0) it is wildly non-smooth. This fully localises the FD-05 failure to the force-integral/normal
   path and explains why the floor helped.
2. **FD-06's remaining deviation comes from the flow-solve response**, which contains an irregular, non-ε-proportional
   component of order 1e-5–1e-3 N that the registered noise rule cannot see (baseline repeats are bit-identical).
3. That component is **deterministic and independent of the pressure-solver tolerance**, is **not removed by Float64**,
   and is established within the first ~2 tU/L. Its origin is **not identified**.

## 1. Frozen-flow force integral (baseline v17, flow_24, floor 0.25 in the solve; snapshots tU/L 6 and 20)

Centered slopes of the force integral (flow held fixed), registered plateau rule on the three smallest ε, in N:

| τ | max plateau deviation, 4 responses × 3 directions |
| --- | --- |
| 0 (historical `g/|g|`) | 51–132% (same at tU/L 6 and 20) |
| **0.25** | **0.07–0.39%** |
| 0.5 | 0.05–3.9% (one D0 downforce case) |
| 1.0 | 0.04–7% and larger for D2 downforce (slope ≈ 0) |

With τ = 0.25 the slope is constant from ε = 1e-8 to 3e-5 m (D1 drag −0.150, D2 drag −0.0727 N/m). White φ noise
(seeded, every node) changes the floored force integral linearly (1e-8 m → 3e-9 N, 1e-6 m → 3e-7 N) but the unfloored one
by 2.5e-4 N at 1e-8 m, non-proportionally. The derivative **target depends on τ** (D0 drag −1.60 N/m at τ = 0.25, −1.49 at
0.5, −2.32 at 1.0): the FD oracle differentiates the floored discrete model.

## 2. Solved response (CPU, floor 0.25 in solve and force), tU/L ≤ 6

| Perturbation | Δdrag vs baseline (N) |
| --- | --- |
| D1 ε = 1e-7 m | −1.8e-7 |
| D1 ε = 1e-6 m | **+3.5e-5** (a persistent offset set within the first 2 tU/L; ≈ +33e-6 N from t = 2 to 6) |
| D1 ε = 1e-5 m | −4e-6 |
| D1 ε = +1e-4 / −1e-4 m | −1.2e-5 / +3.6e-6…+8.5e-6 |

The solved response is not proportional to ε at these scales, and the ε = 1e-6 offset is ≈ 200× what the frozen-flow slope
(−0.15 N/m) predicts. Tightening the multigrid pressure tolerance from 1e-4 to 1e-6 (twice the cost) reproduces every one of
these jumps (ε = 1e-6 m: drag +3.59e-5 → +3.55e-5 N, i.e. within 1%; downforce +3.9e-5 → +3.0e-5 N, within ~25%; the
white-noise cases of §3 agree to within 1% in drag): **not solver-tolerance noise**.

## 3. White φ noise in the solve (tU/L window 2–3, same floor, Float32)

| Noise on every node | Δdrag (N), seeds 1/2/3 | Δdownforce (N) |
| --- | --- | --- |
| 1e-8 m (10 nm) | +2.95e-4 / +4.53e-4 / +3.92e-4 | +8.3e-4 / +1.03e-3 / +9.6e-4 |
| 1e-7 m | −8e-5 / −9.3e-4 | −1.0e-3 / +2.7e-4 |
| 1e-6 m | −1.4e-3 / −5.7e-3 | −4.2e-3 / −2.3e-3 |

These are 3–10× the 0.5-mm pair signals of FD-06 (6e-5–1.7e-4 N), have the same sign for three seeds at 1e-8 m (a one-sided
jump at the baseline, not zero-mean noise), are identical at pressure tolerance 1e-6, and are absent from the floored
force integral (§1). So the sensitivity lives in the flow solve.

**Float64 does not remove it.** In Float64 the baseline itself differs (drag 0.3244 vs 0.3344 N, downforce 0.3093 vs 0.3458 N
in this window) and 1e-8 m noise shifts downforce by +0.052 N and drag by −1.0e-3…−5.2e-3 N. Round-off at the d-field is
therefore not the explanation.

## 4. FD-06 data against these findings

Fitting `pair = aε + bε³` to the 6 FD-06 combinations leaves residuals of 1e-6–5e-5 N, the same order as the irregular
solved component. The two PASS combinations (D2 drag, D0 downforce) are those with the largest slopes (0.17 and 0.78 N/m);
the four FAIL combinations have |slope| 0.06–0.11 N/m. This pattern is what a roughly constant absolute irregularity of
~1e-5 N would produce (it does not follow from ε-dependent curvature).

## Supported / not supported

**Supported (evidence-scoped, v17 / flow_24, short-horizon CPU)**
- The floor makes the force-integral map smooth and linear; the historical normal does not.
- The solved response to sub-micron φ changes contains an irregular, non-proportional component of 3e-5–1e-3 N that
  is independent of pressure tolerance and precision (32 vs 64 bit), and that the registered baseline-repeat noise floor
  (1e-8 N) does not measure.

**Not supported**
- Its mechanism. Candidates, all unverified: a degenerate baseline in which source faces lie exactly on both the design-lattice
  planes and the flow sample planes (the Float32/Float64 baselines differ by 3–10% in this window, which points to
  tie-breaking-type sensitivity), a BDIM/mask discontinuity, or high-frequency sensitivity of the discrete solve.
- That the same behaviour holds at tU/L 80–120 (the FD-06 data are consistent with it but do not prove it).
- Any qualification of the FD oracle, gradient or optimizer.

## Suggested next step (needs a decision; nothing registered)

Test the degeneracy hypothesis directly before any new contract: resample the registered source surface on a design lattice
shifted by a non-multiple of h (and, if needed, shift the flow origin by a non-multiple of its spacing) so that no source
face lies on a lattice or sample plane, then repeat the white-noise test of §3 on the solve. If the solved response then
becomes proportional (as the floored force integral already is), a new canonical state (v18) plus re-baselined W3/W4 is
justified; if not, the cause is in the flow solve itself and the oracle must tolerate an absolute irregularity (a
noise-aware plateau rule registered in a new round, with the noise measured from tiny-perturbation replicates).
