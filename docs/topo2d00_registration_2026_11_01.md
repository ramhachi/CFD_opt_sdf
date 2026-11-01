# TOPO-2D-00 and TR-00: does the element-count preference of a 2D ground-effect wing at Re_c 1e3-3e3 (WaterLily) agree with 2D RANS at Re_c 4.6e5? — registration draft rev 0

要約（日本語）：GEN-01 rev 3.1 の「最も安く決定的な試験」です。Zhang & Zerihan（2003）の 2 要素の地面効果翼（主翼素は T2-0 で使った Tyrrell 026、フラップは同論文の形状）から 1／2／3 要素の 2D 系列を作り、WaterLily の 2D（Re_c 1e3 と 3e3、配置位相 16）と、T2-0 の 2D RANS パイプライン（Re_c 4.6e5、Kaggle CPU、TR-00 で公開データに対して適格化）とで、要素を増やしたときの downforce と drag の差 Δ(1→2)、Δ(2→3) の **符号と順位が一致するか**を、先に書いた一致規則で判定します。不一致なら「低 Re で見つけた要素数の選好は FSAE の Re に転写しない可能性が高い」ことを、計算機の購入も MW-01 の登録も前に記録します。この文書は登録の草稿で、凍結も実行もしていません。幾何の数値のうち「要確認」とあるものは調査 F の結果で埋めます。

Status: **draft rev 0 (2026-11-01), not frozen, no run.** Intended class: `REGISTERED_FROZEN` (one three-angle plan review, one source review, freeze before any run, written-once analysis). Parent issue #80 (GEN-01); feeds user decision (i) and the MW-01 registration. Compute: WaterLily 2D on Kaggle T4×2 or the LOCAL-GPU-01 backend (≈ 15 GPU h), 2D RANS on Kaggle CPU through the T2-0 pipeline (≈ 100 CPU runs of minutes to an hour each). Caps in section 9.

## 1. Question, hypotheses and claim ceiling

- **Q.** For a 2D single-element ground-effect wing and its 2- and 3-element derivatives at fixed ride height and incidence, do the increments of downforce and drag from adding an element have the same sign and the same ranking in (a) WaterLily implicit LES at Re_c 1e3 and 3e3 and (b) RANS at Re_c 4.6e5 on a pipeline qualified against Zhang & Zerihan's measured single- vs double-element difference (TR-00)?
- **H1 (transfer).** The sign of Δ(1→2) agrees (adding a flap raises downforce and drag at both Re). **H2 (ranking).** The order of the three configurations by downforce agrees. **H3 (physics, expected failure mode).** At Re_c 3e3 the trailing-edge boundary layer (≈ 5c/√Re ≈ 0.09c) is thicker than the slot, so the slot effect is weaker or absent and Δ(1→2) is smaller in relative terms than at 4.6e5 (W-N3).
- **Claim ceiling.** 2D, one section family, one ride height and incidence per element count, no transition modelling beyond what TR-00 qualifies, WaterLily iLES outside its published validation range for airfoils (descriptive caveat), RANS qualified only for the sign and ratio of the single-vs-double difference. A concordant result says the element-count preference is *not refuted* by the high-Re model; it is not an FSAE claim, not physical downforce, and not 3D.

## 2. Geometry series (frozen by hash before the plan review)

| config | elements | source | notes |
| --- | --- | --- | --- |
| E1 | main element only | Tyrrell 026 (Genua 2009 Table 1 listing, `data/t20/tyrrell026s_genua2009.dat`, as in T2-0) | ride height h/c 0.224 (the only height where T2-0c's steady RANS passed every gate), incidence as the T2-0 listing |
| E2 | main + flap | Zhang & Zerihan (2003) double-element layout: flap profile, flap chord, gap, overlap and flap angle **to confirm (research F)**; the main element is the same Tyrrell 026 | the published configuration at a tested ride height; if the flap coordinates are not published, the flap is a scaled Tyrrell 026 section with the published chord/gap/overlap/angle and this is disclosed |
| E3 | main + 2 flaps | **constructed** (no published 3-element ground-effect dataset is known): the E2 flap split into two elements of equal chord sum, same total deflection, gap and overlap by the same rule as E2 | descriptive-leaning; its RANS side is qualified only through E1/E2 |

**Thickening rule for WaterLily.** Every element is thickened to t ≥ t_min = 4h at the WaterLily grid (GEN-01 rev 3.1 §3.2 default until the RES-00 ladder; the classic BDIM floor is ≈ 3.7h at ε = 1) by a normal offset of the camber line that keeps the leading-edge radius and the trailing-edge location; the same thickened geometry is used on the RANS side (so the two solvers see the same bodies). The sharp-trailing-edge originals are run on the RANS side as well, as the descriptive arm `E*_sharp` (the TR-01b idea), to measure what thickening alone does at 4.6e5.

**Grid.** WaterLily 2D with h = c/120 (c = chord of the main element) so that the flap (chord ≈ 0.3-0.5c) has ≥ 36-60 cells; the slot ≥ 4h. Domain as T2-0 (2c upstream, 5c downstream, 6.8c above the ground), moving ground as a BDIM half-space at V = U. Placement phases: 16 sub-cell (x, z) shifts with mirror pairs (JOB-02 machinery extended to z). Confirmation grid h = c/180 for E1 and E2 (4 phases each).

## 3. Solvers

| side | solver | Re_c | settings |
| --- | --- | --- | --- |
| W | WaterLily 2D (Julia 1.12.6, WaterLily 1.8.0 pinned; backend per LOCAL-GPU-01 or Kaggle T4) | 1e3 and 3e3 | U = 1, ν = c/Re_c in solver units, Float32, `exitBC`, slip top, moving ground; window and burn-in from a Stage-0-type formula (section 5); force readout = the FORCE-00-adopted readout (if FORCE-00 has not passed, R_cur is used and FORCE-00's measured spurious force is reported as a caveat) |
| R | OpenFOAM v2512 `simpleFoam`, T2-0 pipeline (`scripts/t20_case.py` family; gmsh meshes, Kaggle CPU because of LOCAL-OF-01) | 4.6e5 | SA-WF (primary) and SST-WF (second model) on the fine30 family and a second mesh family (`med30` or a new base realisation), 8 mesh realisations per (config, model, family) through the known gmsh run-to-run variation (each realisation's mesh SHA recorded); 5000 iterations with T2-0c's convergence and continuation rules; a non-settling case is a result (`NUMERICAL` for that cell) |

## 4. TR-00: qualification of the RANS side (registered inside this study, judged first)

- **Reference.** Zhang & Zerihan (2003): measured C_L of the single element and of the double element at the chosen ride height and incidence (values, Re, trip **to confirm, research F**). The reference's own uncertainty, if published, is the band; if not, the band is the T2-0b G2 experience (mean absolute error ≈ 4-5 % on single-element C_L) stated as an assumption.
- **Rule.** TR-00 passes for a (model, family) if the RANS Δ(E1→E2) in C_L has the sign of the measured difference and its ratio to the measured difference lies in [0.5, 2] with its 90 % interval over the 8 realisations. The sharp-edged originals are used for TR-00 (the published geometry); the thickened E1/E2 then run on the qualified pipeline.
- **Consequence.** Only (model, family) cells that pass TR-00 are used in the concordance test; if none passes, the RANS side is `UNQUALIFIED` and TOPO-2D-00 ends `TR_UNQUALIFIED` (the question cannot be asked yet; nothing is claimed about transfer).

## 5. Statistics

- **WaterLily differences.** Paired same-phase differences Δ_W(1→2), Δ_W(2→3) over the 16 phases; σ_d from the pairs (estimator A) and from the within-run batch-means SE (estimator B) with the larger used; the per-config window is set by the RE-01 Stage-0 formula applied to a parent-only pre-run of E1 at each Re (burn-in rule, S0 spectral estimate, window = the smallest multiple of 50 c/U with SE ≤ 1.5 % of the E1 downforce, cap 400 c/U); these are engineering parameters fixed by formula, not thresholds.
- **RANS differences.** Δ_R over the 8 realisations per (model, family), 90 % t-intervals; the worst case over qualified (model, family) cells is the RANS verdict (W-N12).
- **Concordance rule (fixed now).**
  - `SIGN_AGREE_12`: the 90 % intervals of Δ_W(1→2) and Δ_R(1→2) in downforce both exclude 0 and have the same sign (evaluated at both WaterLily Re).
  - `RANK_AGREE`: the ranking E1 < E2 < E3 (or whatever the RANS ranking is) by downforce is the same in WaterLily, with every adjacent pair resolved (intervals exclude 0) on both sides.
  - `DRAG_SIGN_AGREE_12`: same for drag.
  - `RETENTION_12`: the ratio [Δ_W/J_W] / [Δ_R/J_R] (relative increments) with a Fieller interval; reported, not judged.
- **Labels (ordered, exhaustive).** `INVALID` (freeze or identity violation) → `TR_UNQUALIFIED` → `NUMERICAL` (a required cell did not settle or a WaterLily run was non-finite) → `INCOMPLETE` (cap hit) → `RESOLUTION_LIMITED` (the W confirmation grid changes the sign of Δ_W(1→2) or its interval ratio leaves [0.5, 2]) → `UNRESOLVED` (a required interval includes 0 on either side) → `DISCORDANT` (SIGN_AGREE_12 false at both Re, or RANK_AGREE false with both sides resolved) → `CONCORDANT_PARTIAL` (sign agrees, rank does not, or agreement at one Re only) → `CONCORDANT`.

## 6. What each label means for GEN-01 (pre-declared)

| label | consequence |
| --- | --- |
| `CONCORDANT` | MW-01 may be registered with element-count freedom as a primary estimand; TR-01 keeps its 3D transfer role |
| `CONCORDANT_PARTIAL` | MW-01 registered; the element-count estimand is secondary (descriptive) at the Re where agreement failed |
| `DISCORDANT` | recorded as "the element-count preference at Re_c ≤ 3e3 does not transfer to Re_c 4.6e5 in this model"; MW-01 may be registered only as low-Re methodology (user decision (i) is taken with this on the table) |
| `UNRESOLVED`, `RESOLUTION_LIMITED` | one repeat allowed with the pre-declared change only (longer window / finer confirmation grid, caps permitting); otherwise reported as is |
| `TR_UNQUALIFIED`, `NUMERICAL`, `INCOMPLETE` | no transfer statement; the RANS pipeline question returns to M4 (#66) |

## 7. Runs and budget

| side | runs | cost |
| --- | --- | --- |
| W pre-run | E1 at Re 1e3 and 3e3, 1 phase, long window (window formula) | 2 × ≈ 0.4 T4 h |
| W main | 3 configs × 2 Re × 16 phases, window from the formula (150 c/U assumed) | 96 × 0.23 T4 h ≈ 22 T4 h (≈ 11 h on T4×2, ≈ 14 h on the 4070 Ti) |
| W confirmation | E1, E2 at Re 3e3, h = c/180, 4 phases | 8 × ≈ 0.8 T4 h ≈ 6 T4 h |
| R TR-00 | E1_sharp, E2_sharp × 2 models × 2 families × 8 realisations | 64 runs × 10-60 min (fine30 ≈ 13-21 min per 5000 iterations) |
| R main | E1, E2, E3 (thickened) × qualified cells × 8 realisations | ≤ 96 runs |
| caps | WaterLily 40 GPU h; RANS 160 CPU h (Kaggle: 5 concurrent 4-core sessions) | no extension; `INCOMPLETE` beyond |

## 8. Controls

- **Determinism.** One W run repeated (byte class per the backend's gate); one R realisation re-meshed (gmsh variation is the realisation noise by design).
- **Domain.** E2 at Re 3e3 with the top boundary 1.5× higher, 2 phases (DOMAIN control, descriptive → `DOMAIN_SENSITIVE` if Δ_W(1→2) changes by more than 3 pooled SE).
- **Readout.** If FORCE-00 has passed, Δ_W is computed with both readouts and reported.
- **Manipulation.** E2 vs E1 must differ in C_L by > 3 SE on both sides (else the increment is below the floor and the label is `UNRESOLVED`).

## 9. Freeze, review, stop rules, outputs

- Freeze 1 (before any run): this text, the geometry files and their SHA-256 (E1-E3 thickened and sharp), the WaterLily job and the RANS case generator SHAs, the window formula, the phase set, the realisation count, the concordance rule and label table, the caps.
- Reviews: one three-angle plan review (the study's only one under PROC-01), one source review of the new code (2D job, thickening, geometry generation, analyzer).
- Analysis: `scripts/topo2d00/analyze.py` written once with an independent `check.py`; outputs `analysis.json`, `analysis.md`, `tr00.json` under `docs/evidence/topo2d00_2026_11/` with `SHA256SUMS`.
- Stop: caps; `TR_UNQUALIFIED` stops the R main runs; a non-finite W run stops that config at that Re (recorded), the others continue.

## 10. Open items to fill before the plan review

- Zhang & Zerihan (2003) double-element geometry, test conditions, measured C_L values and uncertainty (research F).
- Whether E3 should instead reuse a published 3-element layout (none known).
- The WaterLily 2D job: dims, `exitBC`, ground as a moving half-space, force readout (FORCE-00), 3-axis phases; the thickening generator and its tests.
- Whether the RANS side can run the thickened sections on the fine30 family without new mesh tuning (blunt trailing edges change the gmsh fan).
