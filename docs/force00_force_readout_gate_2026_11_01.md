# FORCE-00: the force readout of the WaterLily line must close under uniform pressure — engineering gate, draft rev 0

要約（日本語）：WaterLily 1.8.0 の圧力の面積分（`pressure_force` ＝ ∮p n ds）は一様な圧力で閉じず（issue #369）、表面がセルを切る位置に依存する見かけの力を出します。報告では R=8〜32 の円で 2.7e-3〜2.9e-2、R=16 の球で 0.29 で、本プロジェクトの利得の判定尺度（親の力の 0.1〜0.5 %）と同じ桁です。FORCE-00 は、本プロジェクトの物体（v18 の板、W2a の球）でこの誤差を測り、閉じる読み出し（運動量の control-volume 法、または提案中の `nds` 修正）を実装して、一様圧力での閉包・配置位相への依存・既存の親の値との関係を登録した基準で確かめる工学 gate です。MW-01 以降の登録 study は合格した読み出しを使います。凍結済みの SCREEN-01／FID-01 の結果は再評価しません。

Status: **draft rev 0 (2026-11-01), not run.** Class when run: engineering capability gate (`EXPLORATORY_COMMITTED` rows; one independent source review of the implementation before the first GPU run). Cap: 5 GPU h (Kaggle T4 or the LOCAL-GPU-01 backend) plus CPU work on the Mac. It changes no qualification flag and does not reopen any frozen result.

## 1. Question and scope

- **Q1 (measure).** On the project's bodies and grids, how large is the spurious force of the current readout under a uniform pressure field, and how does it vary with the sub-cell placement phase?
- **Q2 (fix).** Does a corrected readout close under uniform pressure to a registered tolerance on the same bodies, and what does it do to the parent's downforce and its phase SD?
- **Not asked.** Whether the flow solution itself is correct (issue #369 states the flow is unchanged; only the readout is affected), anything about Re, or whether past registered gains change (not re-evaluated here; see section 6).

## 2. Readouts under test

| readout | definition | status |
| --- | --- | --- |
| R_cur | `-(WaterLily.pressure_force(sim) + WaterLily.viscous_force(sim))` as in `julia/CFDSDFWaterLily/src/Forces.jl` (1.8.0 `∮nds` with the BDIM kernel) | the registered readout of every study so far |
| R_nds | the `nds` redefinition proposed in issue #369 (telescoping change of μ₀ per cell), back-ported into the project package without changing the pinned WaterLily (a project-side function, not a fork) | to confirm the exact form from the issue/PR (research F); if it is not well-defined for 1.8.0, this arm is `NOT_RUN` |
| R_cv | control-volume momentum balance on a box enclosing the candidate body only (not the ground): F = −∮_S [ρ u (u·n) + p n − τ·n] dS − d/dt ∫_V ρ u dV, evaluated on cell faces of the box, time-averaged over the window (the volume term averages to a small residual; recorded) | new; the standard alternative (WaterLily issue #293 reports an 8.4 % mean-drag difference between the two on a cylinder) |

## 3. Runs

| run | where | what | readouts |
| --- | --- | --- | --- |
| U1 | Mac CPU (no flow; geometry only) | p ≡ 1, u ≡ 0 on the v18 parent at flow_24 and flow_32 lattices, 32 placement phases (the FID-01 Halton shifts incl. mirror pairs; z phases added) | ∮p nds per phase for R_cur and R_nds; the exact answer is 0 |
| U2 | Mac CPU | the same for the W2a sphere fixture (R in cells 8, 16, 32) | comparison with the numbers in issue #369 (circle 8.5e-3, 2.7e-3, 2.9e-2; sphere R16 0.29 in its units) |
| F1 | GPU (Kaggle T4) | UNC-01 U01 parent (v18, flow_24) at 8 phases, full window; all three readouts sampled every 8 steps | window means, phase SD per readout; R_cur must equal the registered UNC-01 values byte for byte on the T4 (regression) |
| F2 | GPU | flow_32 parent at 4 phases (the SCREEN f32a phases 13-16) | same; R_cur regression against f32a |
| F3 | GPU | one FID tier-A pair (parent vs `camber_m19.7`) at 4 phases, flow_32 | paired differences under each readout (descriptive: does the correction move a registered-scale difference by more than σ_d?) |

## 4. Criteria (fixed now; computed once by a frozen `scripts/force00_gate.py`)

| criterion | rule |
| --- | --- |
| C1 regression | R_cur on F1/F2 equals the registered T4 values byte for byte (else the harness path changed: `FAIL`, stop) |
| C2 closure | for the corrected readout(s), max over phases of |∮p nds| under p ≡ 1 ≤ 1e-4 × (projected area × 1) on U1, and ≤ 1e-3 relative on U2 (a sphere's projected area), i.e. at least 100× smaller than R_cur's measured spurious force; a readout that does not meet this is `FAIL_CLOSURE` |
| C3 phase dependence | phase SD of the corrected parent downforce on F1 ≤ R_cur's phase SD (one-sided F-test at α 0.05 is not required: descriptive with both SDs reported); a corrected readout with a larger SD is `FAIL_PHASE` |
| C4 sign and scale | on F1 the corrected downforce has the same sign as R_cur and lies within 10 % of it (a larger shift is not a failure but blocks adoption until explained: `HOLD`) |
| C5 difference preservation | on F3 the paired difference under the corrected readout differs from R_cur's by less than UNC-01's σ_d for that mode (descriptive; reported) |

**PASS** for a readout = C1 pass, C2 pass, C3 pass, C4 within 10 %. If both R_nds and R_cv pass, R_cv is adopted (no dependence on an unmerged upstream change) and R_nds is recorded; if only one passes, it is adopted; if none, MW-01 is not registered until a readout passes (GEN-01 rev 3.1 §8).

## 5. Implementation notes (ponytail)

- R_cv needs the box faces' u, p and the viscous stress; WaterLily exposes `sim.flow.u`, `sim.flow.p` and `ν`; the stress on Cartesian faces is a central difference. Implement as one function in `julia/CFDSDFWaterLily/src/Forces.jl` with a `box` argument (cells inset ≥ 2 cells from the domain boundary and ≥ 4 cells from the body); unit test on an analytic uniform-pressure field (zero) and on a prescribed linear velocity field (known flux).
- U1/U2 need no simulation: build the body, set `p .= 1`, call the readouts. Deterministic, seconds on the Mac.
- The readout is sampled alongside R_cur in the job (an extra CSV column set), so registered R_cur regression is checked in the same run.

## 6. Consequences

- Registered studies from RES-00 and MW-01 on use the adopted readout, named in the registration.
- SCREEN-01, FID-01, UNC-01 and RE-01's R1 keep their frozen readout; this gate's result is recorded as a known artefact source for them. A descriptive re-read of frozen outputs with the corrected readout may be done later as a separate exploratory item, never as a re-judgement.
- RE-01 (#78): its Stage 0 charter should name the readout it uses; if FORCE-00 passes before RE-01's R1 registration, R1 may adopt the corrected readout (an RE-01 amendment, user decision (f)).

## 7. Procedure

1. Implement R_cv (and R_nds if defined) with tests; one independent source review (blockers fixed before any GPU run).
2. Exploratory_index rows; U1, U2 on the Mac; F1-F3 on the GPU; archive under `docs/evidence/force00_2026_11/` with `SHA256SUMS`.
3. Run `scripts/force00_gate.py` once; write section 8 (append-only).

## 8. Results (to be filled once)

(not run)
