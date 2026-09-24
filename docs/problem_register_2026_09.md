# 問題台帳 — 2026-09-22

作業スライス単位の記録（`p0_openfoam_closed_loop_2026_09.md`、
`stage_t_optimizer_diagnosis_2026_09.md`、`docs/evidence/*.json`）を、
**問題単位**へ横断整理したもの。正本ロードマップは`phase_plan.md`であり、
実行順序はそちらが決める。

## 要約

T→S→Vのパイプラインは実機OpenFOAMで一周し、Stage Tは初めて実設計を生成した。
その後、DF0--DF6のcompiler、transform、受理制御、抽出、検証algebra、robust prototypeが
実装された。PQ0.1/PQ0.2 は projected-volume、parent/trial oracle、Path B bracket、rollback、
resume を実 OpenFOAM の bounded closed loopとして統合し、PQ3は3 accepted stepを得た。
ただし、これはPath B下のcapability evidenceであり、production gradient、抽出可能な終端候補、
Stage V downforce referenceはまだ資格化されていない。

一方、**このアーキテクチャが成立する条件そのもの（安い代理モデルが、実際の optimizer
reachable set で応答値と候補順位を十分に保存すること）は、現時点で資格化されていない。**
WP6-2 の8形状では downforce の解像可能な反転がなく、候補別bandによる再判定後も25組で
反転0だった。P18は固定形状diagnosticとして閉じたが、production optimizerの一般的な
裏付けには使えない。PQ1は細 source grid で Path B に進んだが5% gateは未達である。
現在の主要blockerは、P6の残るdesign/source-grid coupling、P16のdownforce Stage V数値不確かさ、
P19のprojected-volume/geometry-field意味論、P20のStage S entry測定である。

ただし初期の否定的所見は、**未資格の参照（P12）と未収束の随伴（P13）の上に乗っていた**ため、
Brinkman方式一般のNo-Goへ昇格させてはならない。

2026-09-12の測定により、観測されている失敗群は1本の連鎖で説明できることが分かった。
**抗力寄与の約93%が`beta < 0.1`の45,316セルから来ており、全ランを通じて`beta > 0.62`の
セルが存在しない。** すなわちStage Tが最適化してきた「空力」は物体ではなく希薄な靄が
生んでいた。詳細は下記「統一的説明」。

## 一覧

重大度は「アーキテクチャの主張を無効化する度合い」で付けた。

| # | 問題 | 重大度 | 状態 |
| --- | --- | --- | --- |
| P1 | 代理モデルの順位が body-fitted へ転写しない | 最重大 | **条件付き肯定観測、一般資格は未成立（2026-09-20, WP6+WP6-2）**: WP6 の厚さ軸ではdownforce反転。WP6-2の8形状ではV1/V2とも解像可能な反転ゼロ、tau=1.000。一方、17形状合成poolのmachine verdictは両応答とも`unresolved`。reachable-set/min-widthへの一般化はP18を閉じてから判定する |
| P2 | 設計が二値化しない | 最重大 | **solver fieldの登録済み離散指標は達成、抽出可能性は未成立（2026-09-22, PQ3.3）**。`beta_solver` mean_nd 0.00388 / max 0.94395。ただしglobal指標は空領域で希釈され、最終b=16は0 accepted。P19/P20を閉じて再判定 |

> **2026-09-23 quantification:** both terminal candidates re-grey during the campaign: the v9 (b=16) terminal measures `mean_nd 0.109` and the v11 (b=128, margin mask) terminal `0.0555` against the 0.01 bound although the b=128 continuation started at 0.0058. The extractability guard only prevents occupancy collapse; the acceptance policy has no discreteness criterion. Clearing P2 requires a registered discreteness gate in the Phase 2 acceptance (or a penalty), not a threshold change. The PQ4.1 self-intersection reason from v1 was a detector barycentric bug (fixed, P20); the corrected v2 keeps discreteness and clearance as the real failures, and clearance is structurally addressed by the v10/v11 margin mask.
>
> **2026-09-23 v12 update:** the transform-measured acceptance gate is now
> implemented and its bounded entry preflight passes from v10 checkpoint 5.
> The first three trial sizes are rejected before CFD for exceeding 0.01;
> alpha 0.125 passes at `mean_nd 0.00973685`. P2 remains open until a complete
> v12 terminal candidate also passes PQ4.1; one feasible step is not evidence
> of extractable geometry or Stage S readiness.
>
> **2026-09-23 v12/v13 result:** v12 preserved the new bound for one accepted
> step, then every registered sign-step alpha violated it; this was a direction
> and ladder failure, not convergence. A projected raw-gradient direction on
> the local discreteness tangent passed the v13 real-OpenFOAM one-step
> discriminant, improving downforce from `2.32152697653` to `2.45647595951`
> while keeping `mean_nd=0.00975157`. P2 remains open until this behavior is
> sustained and the resulting terminal geometry passes the complete PQ4.1
> extraction/handoff gate.
>
> **2026-09-24 v14/v15 and v15 campaign update:** v14 sustained the tangent
> policy for five additional accepted steps (`DF=2.61268983854`,
> `mean_nd=0.00994531219`, projected volume `0.07052783246`) and then stopped
> when a transform-feasible, Path-B-positive alpha 1.0 trial worsened downforce
> by `2.9093771e-4`. PQ4.1 on the last accepted state shows iso 0.5 passing
> discreteness, extraction profile and volume fidelity, but failing clearance.
> V15 runs from a deterministic support-box trim with a reset convergence
> history, unchanged D/V thresholds and a bounded response-level alpha ladder;
> its entry preflight passed at alpha 1.0 (`DF 2.00516803057 ->
> 2.01655864594`, `mean_nd=0.00348178008`, projected volume
> `0.06216404077`, support violations 0). The bounded v15 learning campaign
> then accepted 10/10 fresh attempts (all at alpha 1.0, so the alpha-below-1
> response backtracking path was not exercised) and stopped at
> `paused_learning_budget` with raw downforce `2.10035503533`, projected
> volume `0.06406567400358908`, active projected discreteness
> `0.003213044195919047` and zero support violations; the registered
> convergence window was not observed. This is a budget stop — not terminal or
> converged — and the campaign evidence alone does not establish Stage S readiness.
> PQ4.1 on the v15 final accepted checkpoint
> (`docs/evidence/pq4_1_v15_state_stage_s_entry_2026_09.json`) then selects
> `rho_projection` iso 0.5 (range 0.4/0.5/0.6, first-that-passes) and the
> complete composite `stage_s_entry_v1` gate returns `ready_for_stage_s=true`:
> discreteness, extraction profile (measured watertight, manifold,
> non-self-intersecting), volume fidelity, volume constraint, width/gap,
> lineage hashes and the `stage_v_clearance_v1` clearance preflight all pass;
> iso 0.4 fails feature shrink, iso 0.6 fails volume fidelity. This measured
> pass is at a paused-budget checkpoint (not a converged terminal state); it
> removes the clearance blocker isolated on v14 but does not close P2, P17
> (no solver-execution reconfirmation) or the remaining P20 scope, and no
> Stage S baseline is registered by this record. The v15 checkpoint's composite
> readiness gate is passed; P2 remains open under its stricter terminal-state
> closure rule, and Stage S baseline registration remains pending.
>
> **2026-09-24 v16 update:** the v16 b=128 continuation (registered from the
> unchanged v15 checkpoint 10, carryover accepted count 10 and the last three
> metrics, cap-stationarity exit and independent terminal repeat enabled)
> accepted 87 steps (cumulative 97) and stopped fail-closed at attempt 88:
> the alpha-1.0 Path B bracket failed as `not_a_descent_direction`
> (`d_adj=-0.04161669`, `d_fd=+0.01716448`). Final accepted state: raw
> downforce `2.65056396128`, projected volume `0.0719735014` (94.30% of Vmax),
> active projected discreteness `mean_nd=0.0025088808`, zero support
> violations; last three objective deltas `5.52e-4/1.53e-4/7.33e-4`, so the
> registered window was not met and no independent terminal repeat ran. P20 is
> closed (calibrated gap/width metrics, volume-calibration correction and
> detector audit), and PQ4.1 on the v16 checkpoint with the repaired gate
> selects iso 0.5 and returns `ready_for_stage_s=true`
> (`evidence/pq4_1_v16_state_stage_s_entry_2026_09.json`). This is a bounded
> response/gradient stop, not a converged terminal; P2's stricter
> terminal-state closure rule and P17's solver-execution reconfirmation remain
> open, and the Stage S baseline registration is the next authorized decision.
| P3 | Stage Tの格子が対象を解像していない可能性 | 高 | 未検証 |
| P4 | 「宣言された問題」と「解かれている問題」の乖離 | 高 | **bounded reduced problemでは解消（2026-09-22, PQ0.1/PQ0.2/PQ3）**。downforce-only + projected-volumeのsolved set、実oracle、bracket、trialを統合。target physics、robust constraints、production backendへの一般化は未資格 |
| P5 | native ISQPが降下方向を与えない | 中 | 診断済・Python移管で回避 |
| P6 | continuous adjoint と discrete primal FD のsolver-side不整合 | 高 | **Path B（2026-09-22）**。source grid細分化+tight residualでFD/adjoint比は1.1504/1.1134/1.1441へ改善しepsilon-stable。refined-source mesh gateはpass。canonical-only refinementは1.1172/2.2454/1.8916でcoupling依存を示した。5% gate未達、第三source gridは登録済み未実行 |
| P7 | 注入が`rho`のみ更新し他配列が陳腐化 | 中 | **解消（2026-09-20）**。C3 identity契約が検証できるときは4配列を同世代で一斉更新、検証できない場合は`owns no filter/projection profile`でfail-closed |
| P8 | move limitにフロアがなくno-opを受理 | 低 | 修正着手中 |
| P9 | Stage Sが範囲ゼロ成分を除去しない | 低 | 未修正 |
| P10 | Stage Sの形状更新（level-set/HJ）が存在しない | 設計上 | 未実装 |
| P11 | Brinkman浸透層が格子で解像されていない | — | **P2の症状として閉じた**（測定済） |
| P12 | Stage V参照が未資格（mesh失敗・solver未収束） | 最重大 | **P15の960-cell候補V0–V3は解消**。他候補・target physicsは未資格 |
| P13 | 最適化ループの随伴・primal実行契約 | 最重大 | **bounded pathでは解消（2026-09-22, PQ0.1/PQ0.2）**。accepted primal再利用、parent adjoint fail-closed、trial primal-only、real bracket/rollback/resumeを実測。勾配精度そのものはP6としてopen |
| P14 | 射影がPythonとOpenFOAMで二重にかかる | 高 | **解消**（注入場との差 1.9e-09） |
| P15 | 最適形状が2セル厚で格子が表現しきれない | 最重大 | **当初因果は反証**。V3でもdownforce grid gateは未達 |
| P16 | Stage Vが解像できる最小差 | — | **scheme因子まで更新（2026-09-21）**。`linearUpwind`でdrag drift 0.364%は2% bound内。downforce driftは0.010374で0.005未達、三格子非単調でGCIなし。次は登録済みdomain/boundary因子 |
| P17 | 候補面とStage V外周境界のclearanceが未検査 | 最重大 | **fail-closed gate実装済み（2026-09-20）**。固定domain束縛+宣言margin preflightで誤候補がmesh前に棄却される。実際のsolver実行での再確認は未実施 |
| P18 | WP6-2のminimum-width適用範囲と不確かさ登録が証拠内容と一致しない | 最重大 | **固定形状diagnosticとしてclosed（2026-09-21）**。候補別bandで8-shape downforceはV1/V2 pass、25組・反転0。17-shape poolは両応答`unresolved`。optimizer-generated shape、絶対値、grid-independent claimは範囲外 |
| P19 | volume targetとStage S geometry fieldの意味論が一致しない | 最重大 | **open（2026-09-22, PQ3.3後）**。backendはraw `rho_design`平均をtargetにし、handoffはRAMP後`beta_solver`を0.4--0.6で抽出。採用制約・geometry基準は`rho_projection`。PQ3.3a再materializeとprojected-volume backendが必要 |
| P20 | Stage S entryの幾何測定が一部fail-openまたは誤計算 | 高 | **closed（2026-09-24）**。self-intersection直接測定とfail-closed化、component gapのface-to-face校正、minimum/quantile契約分離、volume calibrationのshape label訂正、clean/defect/cap回帰testを実装。v15 PQ4.1 passは修理前gateの記録であり、次のPQ4.1は修理後gateで再判定する |

P11–P14は2026-09-12の外部監査（`problem_resolution_plan_2026_09.md`）が指摘し、
本台帳の作成者が実測で確認した。**P12とP13は、既存の最適化結果と順位検定結果を
証拠として採用できなくする。**

修正済み: 力の単位・参照量の不一致、Stage Vがv2 specから駆動できない問題、
勾配の符号規約の曖昧さ、勾配と宣言応答の非束縛。

---

## P18 — WP6-2 evidence-applicability gap（固定形状diagnosticとして解消）

### 症状

`work/fixed_shape_ranking_2026_09/reachable_set_ranking_manifest.json` の purpose は
T1 voxel 0.05 m の3セル、すなわち `>=0.15 m` を検定対象とする。一方、同じ manifest の
`definition.reachable_set` は `>=0.10 m` と記録する。さらに
`analytic_candidate_shapes.py` の複合形状には、0.10 m厚のsecondary element、0.05 m spanの
endplate、0.05 m chord / 0.12 m thicknessのgurney partが含まれる。

8形状の downforce 順位がV1/V2で一致し、解像可能な反転がなかった観測は有効である。しかし、
`evidence/reachable_set_cross_fidelity_ranking_2026_09.json` の17形状統合poolは、反転ゼロという
副所見を持ちながら最終machine verdictがdownforce/dragとも`unresolved`である。同reportの
extraction sensitivityは空であり、ゼロを測定したことを意味しない。一部候補のV1->V2
downforce driftも、他候補から継承した0.0147を上回る。

### 影響

WP6-2は「この固定形状集合で順位反転を観測しなかった」とは言えるが、
`minimum_solid_width`が全局所featureに厳密に適用されたoptimizer reachable setの資格、
absolute response constraintの精度、将来のoptimizer-generated geometryの順位保存を証明しない。
したがってP1を最終closeせず、条件付き観測として保持する。

### 解消条件

[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
の旧DF0計画に従い、次を満たす。

1. union partsを含む実形状からlocal feature size、gap、componentを計測する。
2. 宣言policyと計測値の不一致をmachine-readableにする。
3. extraction sensitivityを測定するか`not_measured`として判定から除外する。
4. candidate/response固有のgrid uncertaintyを登録する。
5. required pairsとaggregate verdictを事前登録した新reportで再判定する。

歴史的 evidence JSON は書き換えない。P18 closureは新しいmanifestとevidence artifactで記録する。

### Closure（2026-09-21）

[`p18_closure_record_2026_09.md`](p18_closure_record_2026_09.md) と
`evidence/wp6_2_rejudgment_manifest_2026_09.json` に事前登録し、候補別band
`max(inherited band, |V2-V1|)`で再判定した。

- reachable 8-shape downforce: V1/V2とも`pass`、25 resolvable pairs、反転0
- reachable 8-shape drag: `unresolved`、反転0
- combined 17-shape downforce/drag: ともに`unresolved`、反転0
- analytic anchorを同一gridで比較する固定形状programでは、density-to-surface extractionを
  経由しないためextraction termは`not_applicable`とした。ゼロ測定ではない。

従ってP18は固定形状diagnosticとして閉じる。8形状の観測は保持するが、optimizer-generated
shape、absolute calibration、grid-independent rankingへは拡張しない。将来のproduction
claimはPQ1/PQ3/PQ5の新しいevidenceから作る。

---

## P19 — volume targetとStage S geometry fieldの意味論不一致（最重大・open）

> **2026-09-23 closure:** PQ4.1 ran the complete composite gate on the first
> converged terminal candidate with the registered semantics: the optimizer
> target and limit, the Phase 1/2 backends, the handoff and the geometry
> extraction all use `rho_projection`; `beta_solver` is retained as the solver
> audit field. The verdict is recorded
> (`docs/evidence/pq4_1_terminal_stage_s_entry_2026_09.json`):
> `ready_for_stage_s=false` on discreteness (`mean_nd 0.109` vs `0.01`),
> a measured self-intersecting extracted surface and the clearance margin.
> P19 is closed as a semantic mismatch; the residual failures are tracked
> under P2/P17/P20. No Stage S baseline is registered.

> **2026-09-23 D0-D3 post-v5 update:** the equality volume target 0.018 was
> measured as the objective blocker at the stopped b=8 parent: the registered
> corrected step improved only 2.71e-7 while the objective-only proposal
> improved +0.13399 under the original `V<=Vmax` inequality (D1 bounded
> discriminant, 10 fresh primals). The minimal change
> (`objective-oc-inequality-v1`, D2 manifest) replaces the equality correction
> in Phase 2, keeps 0.018 as the Phase 1 formation target, rejects
> machine-scale corrected updates and guards extractability. The v6 entry
> preflight passed at b=8 and b=16 (one step each). P19 is NARROWED but remains
> open: the projected-volume semantics are now consistent across target,
> backend and geometry basis, while the extraction-coherence qualification
> still depends on the terminal candidate and the PQ4.1 composite gate. No
> Stage S-ready claim, and the long v6 campaign has not started.

> **2026-09-23 v6/v7 cycle update:** under the inequality policy with the
> volume-cap correction, the b=8 level accepted 36 steps total across the two
> cycles (same-level downforce 0.579818003757 -> 3.82622378522) and now sits
> exactly on the projected-volume cap with a machine-scale stopping attempt.
> The registered convergence window was not met; no convergence claim. P2
> (binarization/extractability) and P19 remain open pending a pre-registered
> cap-stationarity exit, the b=16 campaign and the terminal PQ4.1 evaluation.

> **2026-09-23 preflight v5 current status:** The v4 b=8 failure reason was not
> auditable because its per-alpha ledger was dropped on exception, and b=8
> inherited the b=4 restoration rho instead of the objective-accepted rho.
> Preflight v5 (`docs/evidence/pq3_3b_preflight_v5_2026_09.json`) corrects that
> lineage, records every alpha, and calibrates baseline spread with two distinct
> uncached OpenFOAM primals. b=4 accepts alpha=1.0; b=8 reaches projected
> volume 0.018 in three restoration steps. Every b=8 trial improves canonical
> J and raw downforce, yet all centered Path B brackets fail before FD because
> their minus perturbation crosses a design bound. Adjoint/FD direction signs
> at b=8 are therefore **unmeasured**, not known to disagree. b=16 remains
> unreached; preflight_pass is false and manifest v3 stays `registered_blocked`.
> Preflight v6 (`docs/evidence/pq3_3b_preflight_v6_2026_09.json`) freezes exact
> design box-face cells during the Phase 2 proposal and volume correction while
> retaining the centered Path B rule. b=4, b=8 and b=16 each have an accepted
> alpha=1.0 real trial with projected volume 0.018 and matching negative
> adjoint/FD directional signs. This closes the **single-step preflight
> feasibility question**, not P19: the registered multi-iteration convergence,
> terminal upper-bound re-evaluation and Stage S handoff are still unmeasured.
> The later v4 campaign converged at b=4, then stopped after eight accepted
> b=8 objective steps because the ninth-step centered objective difference was
> below its registered noise floor. A separate same-state diagnostic supported
> a wider centered epsilon with the original noise floor unchanged. The
> registered v5 continuation resumes from the verified b=8 checkpoint; b=16,
> terminal qualification and Stage S readiness remain unmeasured. See
> `docs/evidence/pq3_3b_campaign_v4_outcome_2026_09.json` and
> `docs/evidence/pq3_3b_bracket_recovery_v1_2026_09.json`.
> The v5 continuation then accepted three additional b=8 steps (11 total)
> before all alphas failed the registered improvement gate. Its three-step
> objective stability window did not pass; b=16 and terminal evaluation were
> not reached. The alpha=1 trial improvement was only `2.7124e-7` against
> `1e-6`; smaller corrected updates were essentially zero. This may indicate
> constrained stagnation or proposal cancellation, but it is not a KKT or
> Stage S qualification. See
> `docs/evidence/pq3_3b_campaign_v5_outcome_2026_09.json`.


### 症状

PQ3.3の`VolumeTargetBackend`は、objective gradientが非ゼロのcellをactiveとみなし、
move box内で`mean(rho_design_new)=target`となるscalar multiplierを二分探索する。一方、
採用された制約と形状占有率は`V(rho_projection)`である。PQ3.3ではraw design targetを維持しても、
`b=0 -> 8 -> 16`でprojected volumeが`0.02745 -> 0.01469 -> 0.01302`へ低下した。

さらにcandidate materializationは、RAMP後の`beta_solver`をfixed-grid artifactの
`rho_projected`へ書き、0.4/0.5/0.6でcontourした。採用計画のgeometry fieldはRAMP前の
`rho_projection`である。RAMP q=100では`beta_solver=0.5`が
`rho_projection≈0.9902`に相当するため、現sweepは意図した0.5等値面より大幅に厳しい。

### 影響

- PQ3.3の`discrete_candidate=true`はsolver fieldのglobal mean_nd/max/volume upper-boundだけを
  表し、抽出可能なgeometryを意味しない。
- 0.4 contourの66% volume errorと0.5のempty revoxelizationは実測だが、
  `rho_projection` geometryの同じthreshold verdictではない。
- 現時点の`ready_for_stage_s=false`はfail-closedに維持するが、抽出不能の原因を
  projection continuationだけに確定できない。

### 解消条件

[`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md)の
Work A/C/Dに従う。

1. 既存PQ3.3 candidateから四場を再計算し、別名・別hashで保存する。
2. `rho_projection`をgeometry sourceとして再sweepし、RAMP threshold mappingとmask一致を確認する。
3. volume targetを`V(rho_projection)`へ変更し、宣言active mask、attainable bracket、最終残差を
   fail-closedに検査する。
4. b/q levelごとにparentを再計算し、最終b=16でaccepted/converged stateを得る。
5. terminal candidateを元のprojected-volume upper-bound問題で再評価する。

既存PQ3.3 evidenceは上書きせず、誤ったartifact IDとfield semanticを訂正artifactで参照する。

---

## P20 — Stage S entryの幾何測定不備（高・closed 2026-09-24）

> **2026-09-24 closure:** the remaining scope is implemented and tested.
> `component_boundary_gap_m` replaces the center-to-center EDT with the exact
> axis-aligned cube face distance (`sqrt(sum(max(0, |delta_i| - spacing)^2))`),
> calibrated on analytic axis-aligned and corner-touch fixtures; the declared
> `minimum_solid_width_m` / `minimum_void_width_m` are now compared against the
> true minimum medial-axis thickness (`thickness_ridge_m_min`), while
> `ridge_width_p5_m` stays a separately named quantile that is never
> substituted; the volume-calibration shape labels are corrected by the
> append-only `pq4_volume_fidelity_calibration_correction_2026_09.json`
> (original SHA-256 referenced, measurements unchanged, profile now references
> the correction); and the direct self-intersection detector has a
> false-positive/true-positive/cap audit (clean box/icosphere/torus → `none`,
> a crossing pair → `fail`, over-cap → `not_evaluated`). The detector's AABB
> stage was made memory-safe (per-axis boolean overlap instead of the
> `(n, n, 3)` float64 broadcast). The v15 checkpoint-10 PQ4.1 pass predates
> this repair and remains a pre-repair record; a new PQ4.1 judgment on the next
> terminal candidate uses the repaired gate.
>
> **2026-09-23 partial repair:** two fail-opens are fixed with regression
> coverage: a measured self-intersection now gates the extraction profile
> (`_manifold_reasons`, `mesh_self_intersects`), and the applied discreteness
> threshold is recorded in the composite sub-verdict.

### 症状

PQ4.0は`ready_for_stage_s`を全sub-gateの論理積に戻し、local extraction passによる上書きを
防いだ。この合成論理は正しい。一方、個別測定には次が残る。

1. self-intersectionはmeshと同じmeshのboolean intersectionを呼び、自己交差を検出しない。
   `not_evaluated`もglobal reasonへ追加されない。
2. component間gapは`distance_transform_edt(~material)`をmaterial cell上で読むため0となる。
3. `thickness_ridge_m_p5`を`minimum_solid_width`として扱い、ProblemSpecのminimum意味論と
   一致しない。
4. volume profileが参照する校正artifactはsurface-distanceを測ったもので、登録volume閾値を
   支持しない。

### 影響

現行gateがfalseを返した判断は保守側なので保持できる。しかし、将来trueを返す場合の
幾何資格が十分にfail-closedとは言えない。したがって現行PQ4.0実装だけでStage S entryを
許可しない。

### 解消条件

1. 実self-intersection測定を導入し、必須なのに測定不能ならfailとする。
   → 2026-09-24: 直接triangle-triangle narrow phase、`not_evaluated`を
   `require_self_intersection_measured`でfail化。clean/defect/capの回帰testを追加。
2. component境界間の実距離を測り、analytic multi-component fixtureで校正する。
   → 2026-09-24: `shape_feature_metrics.component_boundary_gap_m`（axis-aligned
   exact、corner touch 0）。`tests/test_stage_s_entry.py`の解析fixtureで校正。
3. minimumとquantile metricを区別し、ProblemSpecに対応するmetricを登録する。
   → 2026-09-24: 宣言minimumは`thickness_ridge_m_min`と比較し、
   `ridge_width_p5_m`は情報用のquantileとして別名記録。
4. binary analytic shapesでsource/surface/revoxelized volume errorを測ってprofileを再登録する。
   → 2026-09-24: 測定はPQ4.0a artifactに存在。shape label欠陥をappend-only
   correction `pq4_volume_fidelity_calibration_correction_2026_09.json`で訂正し、
   profileがcorrectionを参照。
5. clean/defect/unavailable-dependencyの回帰testを追加する。
   → 2026-09-24: clean primitives、crossing pair、triangle cap、gap/width校正を
   `tests/test_stage_s_entry.py` / `tests/test_extraction_qualification.py`に追加。

P20 closure後の新candidateだけをPQ4.1の`ready_for_stage_s`判定に使う。

---

## P1 — 代理モデルの順位が転写しない（最重大・未解決）

### 症状

Stage T（固定格子Brinkman）で最適化した2候補を、body-fitted RANSで3解像度検証した。
B/A比は次のとおり。

| B/A比 | Stage T | coarse (5.5k) | medium (30k) | fine (180k) |
| --- | --- | --- | --- | --- |
| drag | 2.582 | 0.849 | 0.901 | 0.905 |
| downforce | 3.882 | 3.167 | 0.896 | 0.918 |
| L/D | 1.503 | 3.728 | 0.995 | 1.015 |

- **dragの順位は全格子で反転**（Stage Tは「Bの方が2.58倍大きい」、実際は約10%小さい）
- downforceの順位は最粗格子でのみ一致し、細かい2格子で反転
- L/Dは medium/fine で2%以内＝区別不能。Stage Tは1.5倍と主張

### なぜ重大か

このアーキテクチャは「安い代理で探索し、高い検証で確かめる」ことで成立する。
絶対値の一致は不要だが、**順位が保存されなければ、代理で最適化しても実性能は
改善しない。**

### 確認済みの除外

乱流モデルの交絡は棄却した。層流と`kOmegaSST`のdrag係数はcoarseで0.016%、
mediumで0.006%しか違わない。Re~300では渦粘性が無視できる。つまり先行の
`kOmegaSST`比較は無効な検定ではなく、**有効な検定の否定的結果**である。

### 原因候補（未分離）

**2026-09-12の外部監査（`problem_resolution_plan_2026_09.md`）を受けて訂正した。**
当初「原因候補は2つに絞れた」と書いたが、これは強すぎる。二値化（P2）とStage T解像度
（P3）は**主要仮説**であって確定した2択ではない。少なくとも次がまだ混ざっている。

1. 灰色密度と中実STLの物理的不一致（P2）
2. Stage T格子と46,080→8,192セル平均化（P3）
3. `betaMax`の有限値と格子依存性（P11、下記）
4. cell-to-point変換・等値面抽出・再voxel化による形状差
5. **Stage V参照自体が未資格**（P12、下記）
6. 契約違反（P13、下記）

なお**dragの反転は最粗格子でも起きる**ため、P3単独では説明できない。

### この結果の格付け（重要）

参照側のStage Vは`checkMesh`が全ケースで1項目失敗し、solverは収束条件を持たずに
500反復で打ち切られている（P12）。したがって本項は**「未資格の参照に対して観測された
重要な否定的所見」**であり、Brinkman方式一般のNo-Goへ昇格させてはならない。

### 根拠

`docs/evidence/cross_fidelity_ranking_2026_09.json`、`work/stage_sv_laminar/result.json`

### 追記（2026-09-12）— 二値化候補による順位検定（肯定的所見、証明ではない）

P2の修正（罰則付き補間・射影の一本化・随伴の資格化）を経て、初めて中実な設計で
上記の検定をやり直した。参照側もqualified Stage V（`checkMesh`・明示的
`residualControl`・force stationarityをハードゲート化）へ更新した。

#### 何を検定したか

RAMPで二値化した3候補をV0/V1/V2で通した。`opt_q100_step2_try0_r12`は**3格子すべて
で失格**した。`checkMesh`の「Cells with small determinant (<0.001)」（24/98/303セル、
V0/V1/V2）は事前登録プロファイルが免除しない項目であり、係数は他2候補の5〜8倍で
採用不能。したがって**有効なペアは1組だけ**残った。

#### 結果

| grid | step0 Cd | step2 Cd | step0 downforce | step2 downforce |
| --- | ---: | ---: | ---: | ---: |
| V0 | 1.2505 | 1.2610 | 0.5179 | 0.5361 |
| V1 | 1.3480 | 1.3607 | 0.5902 | 0.6129 |
| V2 | 1.3634 | 1.3786 | 0.6680 | 0.6899 |

Stage Tは両応答ともstep2の方が大きいと予測する（drag 2.231→2.706、downforce
1.078→1.594）。qualified Stage Vは**3格子すべてで同じ向き**に一致した。

これは灰色候補での所見と**符号が逆**である。灰色候補ではdragの順位が全格子で
反転していた（B/A比0.849/0.901/0.905、Stage Tは2.582）。この反転はqualified化
後も変わらないため（`work/stage_sv_qualified_laminar/result_summary.json`）、
先行の否定的所見は「間違った対象を比べていた」ことによる**本物の観測**だったと
確認できる。

#### この結果が持つ限界（弱めてはならない）

- **ペアは1組のみ。** 3候補目が失格したため、意図していた2組の符号のうち1つしか
  存在しない。
- **margin（差）は離散化誤差を超えない。** step2−step0のdownforce差は0.018〜0.023、
  一方で各候補自身の格子間drift（V0→V1、V1→V2）は約0.077。向きは3格子一貫だが、
  大きさは未確定である。
- **downforceは格子収束していない**（Gate 3不合格、閾値5e-3に対し約0.077）。収束を
  確かめるはずのV3（約128万セル）は灰色候補のqualified再実行
  （`work/stage_sv_qualified_laminar/result_summary.json`）で500反復に達しても
  収束せず、`residualControl`（U 1e-6、p 1e-5）に対しp残差が約1.9e-4〜6.2e-4
  （19〜62倍）、U各成分は16〜148倍で頭打ちになり、正しく却下されている。
  Cdは収束する（V1→V2で約1.1〜1.3%、上限2%以内）。
- **等値面抽出は体積を失う**（抽出/設計体積比0.881、0.884、0.919、1〜2セル厚の
  物体）。これは真の抽出誤差であり、今回はもう灰色ではないのでgreynessの症状
  ではない。
- ラン内定常性ノイズは約1e-6と小さく、律速要因ではない。律速は離散化である。

#### 結論

一物体、一流動条件（Re〜300、層流）、一有効ペア、一台のマシンによる
cross-fidelity証拠であり、target physicsでもbenchmarkでもなく、いかなる
solver backendも資格化しない。**このアーキテクチャの中心的前提は反証されて
おらず、肯定的所見を得たが、実証されたわけではない。** 決着には次の3点が要る。

1. mesh失格候補の救済（2組目の符号を得る）
2. 離散化誤差を上回るmarginを持つペアの取得
3. downforce応答の格子収束

根拠: `docs/evidence/binarized_ranking_2026_09.json`、
`work/stage_sv_qualified_ramp_binarized/result.json`、
`work/stage_sv_qualified_laminar/result_summary.json`

### 追記（2026-09-20）— 決定実験（WP6, fixed-shape program）

P1の最終判定実験が完了した。10個の事前登録された解析二値形状（迎角系列、厚さ系列、
スパン、zオフセット、鈍頭箱）を、(a) same-grid T1固定格子Brinkman代理
（binary、q=0恒等、alphaMax 2500、転送なしと射影なし）と (b) anchor STL直接的な
qualified Stage V（V1+V2全20実行qualified、固定domain）で評価した。宣言済み
不確かさ帯（downforce abs 0.0147、Cd rel 0.034 — P16の実測値をそのまま継続使用）で
Gate 4を適用した。

| 応答 | 判定 | 実測 |
| --- | --- | --- |
| downforce | **no_go** | V2で解像可能な1組の反転: `plate_a20_nd` vs `plate_a20_t05`（代理 +0.2316、参照 +0.0343 → 符号逆）。代理は参照が飽和する厚さ軸の差を約7倍に誇張する |
| drag | **unresolved（符号全一致）** | 37/37の解像可能ペアで代理・参照の符号が一致（rho 0.9758, tau 0.9111）。順位の入れ替わりは全てノイズ帯以下のクラスタ内 |

主な測定事実:

- 反転は実形状・same-grid・転送なし・抽出なしの最も管理された条件で起きた。
  抽出感度E-blockではiso 0.50がanchorと0.0013で一致し、0.45/0.55で±0.03なので、
  幾何経路の交絡はこの実験にない。
- 厚さクラスタの参照差は0.014–0.034で宣言帯と同オーダー（V1/V2で方向は一貫、
  V2でのみ解像）— **参照自体がこの軸の差の解像限界に近い。**
- P11（alphaMax・saturation・靄）はこれらの形状では無視できる（alphaMax 250 vs
  2500の力差≤8%、solid帯leak ≤2%、beta<0.1の力寄与 ~1e-6）。
- **P1の結論**: 代理モデルの順位保存は、downforce応答の**厚さ因子で反証された**。
  P15で観測された2セル厚問題と整合する、格子と解像度に内在する構造的限界である
  ことが、初めてクリーンな条件下で確認された。optimizerを調整してこの結果を逆転させ
  てはならない（WP6の停止規則）。治療対象は最適化器ではなく、downforce軸に対する
  Stage T代理の定式化（または置換）である。

根拠: `evidence/fixed_shape_cross_fidelity_ranking_2026_09.json`、
`work/fixed_shape_ranking_2026_09/`

### 追記（2026-09-20）— WP6-2 と P18 による適用範囲の訂正

次の8形状を用いたWP6-2では、V1/V2のdownforce順位が完全一致し、解像可能な反転はなかった。
これはWP6の厚さ軸no-goが全形状軸へ直ちに一般化しないことを示す肯定的所見である。

ただしP18の監査により、これを「minimum-width policy内の最終資格」とした先の結論は撤回する。
manifestの幅定義、複合partの局所寸法、候補固有grid drift、未測定のextraction sensitivityが
整合しておらず、17形状poolのmachine verdictも両応答で`unresolved`である。従ってP1の現在状態は
**条件付き肯定観測、一般資格は未成立**である。歴史的なWP6/WP6-2数値は保持し、DF0の
候補別band再判定で8-shape観測だけを固定形状diagnosticとして閉じた。

根拠: `evidence/reachable_set_cross_fidelity_ranking_2026_09.json`、
`evidence/wp6_2_rejudgment_2026_09.json`、P18 closure record。

---

## P2 — 設計が二値化しない（最重大・修正着手中）

### 症状

| 候補 | rho最大 | >0.9 のセル | グレー帯 (0.1,0.9) |
| --- | --- | --- | --- |
| A | 0.62 | 0 | 624 |
| B | 0.55 | 0 | 624 |

### 何が起きているか

Stage Tが最適化しているのは**半透過な多孔質体**（最大でも55%しか塞いでいない）。
Stage Sはその0.5等値面から**中実の物体**を切り出し、Stage Vはその中実体を解く。
両者は物理的に別の対象であり、力の順位が転写する理由がない。

### 原因

OpenFOAMケースの`optimisationDict`が`function linear`を指定しており、Heaviside射影が
恒等写像になっている。

**監査を受けた訂正**: これは sharpening を無効にする欠陥であり寄与原因である。ただし
「設計変数が0.5を越えることを数学的に禁止する」わけではない。tutorialは`tanh; b 20`を使う。

さらに実測で判明した二重射影（P14）がある。Python側が射影した`rho`（最大0.55）を注入しても、
OpenFOAM側の`regularise true`が削り、**ソルバが実際に見る`beta`は最大0.436、0.5超はゼロ**で
あった（`work/stage_t_python_loop_v2_floor/iter_004_attempt_00`）。つまり
**Stage Tが解いた場とStage Sが輪郭化した場は数値的に別物**である。

### 対処と結果（2026-09-12）

射影だけでは足りない。**罰則付き補間が本質である。**

```text
f(rho)  = rho / (1 + q(1 - rho))          RAMP、q > 0 で中間密度が割高になる
f'(rho) = (1 + q) / (1 + q(1 - rho))^2
```

併せて次の3点を同時に行った。

1. 罰則付き補間（RAMP）をPython側で適用
2. 射影所有者をPythonへ一本化し、OpenFOAM側を`regularise false`にする（P14）
3. 収束した随伴と宣言応答に束縛された勾配を使う（P13、C1）

同一格子T1（46,080セル）での実行結果:

| 指標 | 修正前 | 修正後 |
| --- | ---: | ---: |
| ソルバが見る`beta`の最大 | 0.436 | **1.0** |
| 注入した場とソルバの場の差 | 最大0.11 | **1.9e-09** |
| 中間帯 [0.1, 0.9) のセル数 | 624 | **0** |
| 随伴の収束 | false（1反復） | **true**（約1,000反復） |
| 予測ΔJ / 実測ΔJ | 0.21 | **0.80–0.97** |

目的関数はどのq系列でも全ステップ受理・単調改善した。

| q | downforceの推移 |
| --- | --- |
| 8 | 0.151 → 0.448 → 0.887 → 1.471 |
| 30 | 0.494 → 0.849 → 1.381 → 1.736 |
| 100 | 0.884 → 1.078 → … |

漏れの帯別測定では`[0,0.1)`が1.017（流体）、`[0.9,1)`が0.031（固体）で、
**その間の帯がすべて空**である。すなわち設計は流体と固体だけで構成されている。

**これによりP2は解消される見込みである。** Stage Sが0.5等値面で切り出す物体と、
Stage Tが力を計算した物体が、初めて同一になった。これはP1を検定する前提条件であった。

Stage Sハンドオフ側には非離散度 `M_nd = mean(4ρ(1−ρ)) ≤ 0.01` かつ `max ρ ≥ 0.9` の
ゲートを設けてあり、グレーな密度場は下流へ渡らない。

根拠: `work/ramp_interp/optimize_history.json`、`scripts/stage_t_ramp_interp.py`

---

## P3 — Stage Tの格子が対象を解像していない可能性（高・未検証）

Stage Tの格子は8192セル。body-fittedのcoarse格子は5534セルで、**両フィデリティが
一致するのはまさにその解像度**である。細かくすると一致が消える。

ただしdragの反転は最粗格子でも起きるため、これ単独では P1 を説明できない。

検証方法: Stage Tを細かい固定格子で回し、力が収束することを示す。未実施。

---

## P4 — 宣言された問題 ≠ 解かれている問題（高）

同じ根を持つ複数の問題。**ハッシュで同一性は縛れていても、実行経路が宣言した代数を
消費しなければ意味は一致しない。**

### P4a — `downforce`が目的関数でなく等式制約（未修正）

`examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base/system/optimisationDict`が
`downforce`を`isConstraint true; target 0;`と宣言し、`drag`を唯一の重み付き目的として
いた。実際に解かれていた問題:

```text
minimize   drag
subject to downforce == 0
           volume fraction == 0.462
```

材料を置けば必ず鉛直力が出て制約違反になるため、最適化器は体積ゼロに留まる。
40サイクル実行しても beta histogram は `[8080, 2, 110, 0, 0, 0]`、平均0.0070のまま
固定点に収束した。**これはリポジトリ自身のテンプレートである。**

### P4b — 体積制約が原理的に充足不能（未修正）

`topOVolume`の目的関数は `J = (1 − ⟨β⟩_V − percentage) / percentage`、制約は
`weight·J ≤ 0`。`⟨β⟩_V`は**メッシュ全体**の平均、`percentage`は**流体率の上限**である。

`percentage 0.462`、`weight 1` は「固体が全メッシュの53.8%以上」を要求する。
しかし`fixedZeroPorousZones`が8192セル中5283セル（64.5%）を強制流体にしているため、
設計可能な2909セルが全て固体でも固体率は最大35.5%。

```text
min J = (1 − 0.355 − 0.462) / 0.462 = +0.396 > 0
```

観測値 `J = 1.1497`（⟨β⟩=0.007）は上式と厳密に一致する。

### P4c — 勾配の符号が規約と逆（ガード済）

`topOSens`は`+downforce`の微分であり、プロジェクト規約の`J = −downforce`に対する
`dJ/dρ`とは逆符号。補正前のFD比は8行すべてで約−1（平均−0.9931）。この配列を
`dJ/dρ`として消費すると設計が逆方向へ動く。artifactの規約文字列を明示化した。

### P4d — 勾配が宣言された応答に束縛されていない（ガード済）

P0で使用したProblemSpecは`drag`応答と`minimize_drag`目的のみを宣言していたが、
検証した勾配はOpenFOAMの`downforce`目的のものだった。
`transfer-openfoam-gradient-to-canonical`に`--response-id`を必須化し、specで宣言された
応答であることを検証するようにした。記録済みartifactはガード導入前のもの。

### P4e — 実際のReynolds数が宣言の約1/20000（未修正）

| | Stage Tケース | ProblemSpecの宣言 |
| --- | --- | --- |
| 流速 | 1.0 m/s | 30.0 m/s |
| 動粘性 | 1e-2 m²/s | 1.47e-5 m²/s |
| Re（L≈3m） | 約300（層流） | 約6.1×10⁶（乱流） |
| 参照面積 | 0.64 m² | 1.2 m² |

このまま両忠実度を比較すると別物理を比べることになる。今回のクロス忠実度検定は
Stage T側の実条件に合わせて実施した。

### 追記（2026-09-22）— PQ0 実装後の production-path 監査

PQ0で `CompiledProblem.volume_constraint`、`DesignTransform`、`solved_set` audit は実装された。
ただし次を実コードで確認した。

1. `fixed_grid_optimizer.py` の one-step path は projected-volume value/gradient を追加するが、
   `stage_t_loop.py::make_oracle_from_compiled` は primitive response constraints だけを組み立て、
   `compiled.volume_constraint` を nonlinear loop の `OracleResult` に追加しない。
2. nonlinear acceptance test の `volume_budget` は、実 volume occupancy ではなく downforce
   response を制約項として使うため、この欠落を検出しない。
3. `work/p0_closed_loop/project.yaml` は drag minimization と downforce maximization の二目的を
   無制約で足し合わせる。PQ0 audit の `declared_equals_solved=true` はこの fixture について
   正しいが、次の downforce+projected-volume reduced problem の成立を示さない。
4. projection output と OpenFOAM beta に同じ artifact 名 `rho_projected` が使われ、volume と
   solver interpolation の意味を metadata なしに区別できない。

従って P4 は未解決である。PQ0.1 では新しい abstraction を作らず、既存 compiler/transform/loop
を接続し、downforce-only objective と projected-volume inequality で
`declared_equals_solved` を再監査する。

### 追記（2026-09-22）— bounded reduced problemでのclosure

PQ0.1は上記の接続を実装し、downforce-only objectiveとprojected-volume inequalityの
`declared_equals_solved=true`を新しい実artifactで確認した。PQ0.2はparent/trial/bracket/
rollback/resumeを実OpenFOAMで実行し、PQ3は同じ経路で3 accepted stepを得た。従ってP4は
**このreduced problemのbounded pathでは解消**とする。

native ISQPの歴史的template、target-Re/full-vehicle physics、robust constraints、将来の
production backendまで解消したという意味ではない。projected-volume targetとgeometry fieldの
新しい不一致はP19で別に追跡する。

---

## P5 — native ISQPが降下方向を与えない（中・回避済）

P4a/P4bと`function linear`を修復すると、native経路でも実形状は生成される
（R7: 1072面、downforce 0.636 → 1.029）。しかしどの実行も収束しない。
Armijo line searchを入れると毎サイクル「line search reached max iterations」となる。

**監査を受けた訂正**: line search失敗は観測済みだが、「探索方向そのものが非降下」と断定するには
方向微分の実測が要る。現時点では「line searchが機能しない」までが観測事実である。

体積感度は抗力感度の約1/4000（cellあたり平均 8.5e-5 対 0.75）でQP内で不可視。
Lagrange乗数がISQPのペナルティ係数`c = 2`に固着するのは、elastic変数のKKT条件
`λ ≤ c` により実行不能性を示す署名である。

**決定: 最適化はPythonへ恒久移管。OpenFOAMはprimal/adjoint評価器に限定する。**
同じ勾配に対するOC更新は12反復で単調前進した。

---

## P6 — continuous adjoint / discrete primal FD 不整合（高・solver側へ局在）

### 現在の判定（2026-09-22）

凍結設計、identity profile、登録済み24-run campaignで再測定した結果、過去の「約10%」より
大きく、方向依存の mismatch が再現した。

| direction | FD / analytic | 相対誤差 |
| --- | ---: | ---: |
| gradient-aligned | 1.2178 | 21.8% |
| random seed 11 | 1.3764 | 37.6% |
| random seed 2026 | 1.5680 | 56.8% |

各方向でepsilonを変えたspreadは0.4%未満。`g_canonical = P.T g_source` とdot-product identityは
machine precisionで一致し、24 runの最大設計変化は`2.98e-8`だった。primal residualを
`5e-7`から`5e-9`へ厳しくしてiterationが91から114へ増えてもratioは0.04%未満しか変わらない。
従ってtransfer、設計の更新、primal residual toleranceは原因から除外され、原因はこの構成の
OpenFOAM continuous-adjoint sensitivityとdiscrete primal responseの間に局在する。

その後、source grid を32x16x16から64x32x32へ細分化し、perturbation primal residualを
`5e-9`へ締めて再実行した。

| direction | 粗grid比 | 細grid比 | 細grid epsilon spread |
| --- | ---: | ---: | ---: |
| gradient-aligned | 1.2179 | 1.1504 | 0.00043 |
| random seed 11 | 1.3764 | 1.1134 | 0.00003 |
| random seed 2026 | 1.5678 | 1.1441 | 0.00450 |

全方向が1へ移動し、30倍のepsilon範囲で符号とplateauが安定したため、source-grid離散化は
主要寄与である。ただし5% gateは全方向で未達、base mesh gateは未測定、source gridは二段階
しかない。従って判定は **Path B bounded exception** であり、grid convergenceとは呼ばない。

次はPQ1.1でbase mesh gateとcanonical grid因子を測定し、必要な場合だけ第三source-grid levelを
事前登録する。PQ3で使う場合は提案方向ごとのcentered primal FD bracketを必須とし、経験的な
一律scale補正は禁止する。

根拠: [`p6_diagnosis_record_2026_09.md`](p6_diagnosis_record_2026_09.md)、
`evidence/fd_campaign_p6_solver_side_result_2026_09.json`、
`evidence/pq1_source_grid_refined_tight_2026_09.json`。

### 歴史的観測（現在の判定で上書きしない）

勾配方向（sensitivity）のFD比は0.990→0.994、相対誤差1.03%→0.56%で正しい。
しかし局在したランダム方向では比が約0.90で安定し、epsを1桁変えても1に近づかない。

| 条件 | ratio | 相対誤差 |
| --- | --- | --- |
| 既定許容値 | 0.896（eps 1e-3） | 10.4% |
| 主問題残差を約2桁厳格化 | 0.905 | 9.5% |
| 正則化を無効化 | 0.861 | — |

許容値の厳格化はばらつきを消したがバイアスは消さなかった（ノイズではない）。
正則化フィルタの連鎖律欠落を疑い、無効化したところratioは1から遠ざかった（0.905→0.861）。

**監査を受けた訂正**: これは連鎖律欠落に対する**反証寄りの証拠**だが、**決定的棄却ではない**。
正則化を切るとforward問題自体が変わるため交絡試験である（「フィルタが無いなら欠落項もゼロ、
よって比は1へ寄るはず」という論理自体は成立するが、他のb依存効果を排除できない）。
正則化transposeの因果的棄却には、同一forward問題の下での比較が要る。

残る候補は`P`の部分重なり再配分（refinement比が非整数：1.875、1.5）だが未検証。
切り分け手順は`problem_resolution_plan_2026_09.md`§8が定める。

この歴史的構成では運用上の影響を限定的と評価していたが、凍結設計campaignでaligned方向も
21.8%外れたため、その評価は現在のproduction判断には使わない。

---

## P7 — 注入が`rho`のみ更新（中・解消 2026-09-20）

`inject-canonical-state-into-fixed-grid-contract`は`rho`だけを上書きし、
`rho_filtered`、`rho_projected`、`alpha`は前状態のまま残る。solver caseは`rho`から
生成される（`src/cfd_sdf/fixed_grid_primal.py:590`）ため現在の結果は正しいが、
他の配列を読む将来の消費者は**古い状態を黙って読む**。

### 対処（2026-09-20, WP4）

- 注入器はC3 identity契約（`rho_projected = rho_filtered = rho`、
  `alpha = beta_max * rho`）を事前状態から検証できるときだけ、4配列を同世代で一斉
  更新する。`beta_max`は記録済み`alpha/rho`比からデコードする。
- identity契約が成立しない（実際のフィルタ/射影がある）場合は、injectionを拒否して
  古い配列を持ち越さない（fail-closed）。更新はそのprofileの所有者経由で行う。
- provenanceに`derived_generation`ブロック（契約、検証値、4配列の新しいハッシュ）を
  記録する。mutationテスト: フィルタ非identity・射影非identity・alphaが単一係数でない
  場合の3件を新規追加（`tests/test_fixed_grid_canonical_state_injection.py`、606 passed）。

## P8 — move limitにフロアがない（低・修正着手中）

Python最適化ループのmove limitは棄却のたびに半減するラチェットで、下限も
リセットもない。ゼロまで縮み、`max|Δρ| = 6e-29`という浮動小数点上のno-opを
「受理」として記録した。

## P9 — Stage Sが範囲ゼロ成分を除去しない（低・未修正）

iso-surface writerは常に計算領域の境界パッチを出力する。したがって退化署名
（5120面・2822頂点・6成分 `[1024,1024,1024,1024,512,512]`・bounds=領域そのもの）は
writerの仕様であり、実設計成分があってもその中に埋もれる。Stage Sは範囲ゼロ成分を
除去すべきである。

## P10 — Stage Sの形状更新が存在しない（設計上・未実装）

Hamilton-Jacobi更新、再初期化、shape gradientからの法線速度、曲率制御のいずれも
`src/`に存在しない。現状のStage Sは一発のiso-surface/SDF生成のみである。

## 統一的説明 — 2026-09-12（測定で確立）

P1、P2、P11、P14、およびStage Sの失敗は、**独立した問題ではなく1本の連鎖**である。
`work/brinkman_scoping/`の測定が、この連鎖の主要な環を直接押さえた。

計測値（■）と推論（□）を区別して示す。

```text
■ function linear（alpha = alphaMax·rho）の下では、同じ材料量を薄く広げるほど
  目的関数が良くなる。すなわち靄が最適解である
      ↓
■ 最適化器はそれに忠実に従い、物体を作らず靄を広げた
      ↓
■ 抗力寄与の約93%が beta < 0.1 の45,316セルから来る
   （alphaMax 2500/10000/40000 で 93.0/92.8/92.9% と不変）
■ 全ランを通じて beta > 0.62 のセルが存在せず、[0.7,1.0] は常に空
      ↓
■ 0.5等値面は、その力を生んだ実体と対応しない
      ↓
■ Stage Vは中実体を解くため、力も順位も一致しない
```

**2026-09-12の機構検証により、連鎖の先頭2環は推論から実測へ昇格した。**
同一の材料量 `∫rho dV` を固定し、コンパクトな物体から段階的に薄く広げて測定した。

| 状態 | セル数 | rho | downforce（linear） | downforce（RAMP q=100） |
| --- | ---: | ---: | ---: | ---: |
| 中実体 | 624 | 1.0 | 0.277 | **0.2595** |
| | 1,294 | 0.48 | 0.400 | 0.0222 |
| | 2,070 | 0.30 | 0.546 | 0.0077 |
| | 2,988 | 0.21 | 0.787 | 0.0040 |
| 靄 | 4,056 | 0.15 | **1.200** | 0.0025 |

線形補間では**靄が中実体の4.3倍**のスコアを出し、薄く広げるほど単調に改善する。
罰則付き補間では完全に逆転し、**中実体が約100倍勝つ**。

したがって最適化器は壊れていなかった。**目的関数が靄を最適解にしていた**ので、
忠実にそれを見つけていただけである。射影（tanh）を足しても b=4 で停滞したのは、
射影が押し上げる一方で目的関数が押し戻していたためである。

根拠: `work/ramp_interp/mechanism_check.json`、`mechanism_check2_a250_q100.json`

### beta帯別の漏れ（決定的）

| beta帯 | セル数（T0典型） | 平均 \|U\|/U_ref | 解釈 |
| --- | ---: | ---: | --- |
| [0, 0.1) | 約8,000 | 103–105% | **流体**。流れて当然 |
| [0.1, 0.3) | 71–107 | 0.6–0.9% | 既に十分塞いでいる |
| [0.3, 0.5) | 72–103 | 0.23–0.36% | 良好 |
| [0.5, 0.7) | 0–33 | 0.27% | 1ランのみ到達 |
| [0.7, 0.9), [0.9, 1.0] | **全ラン0** | — | 一度も生成されていない |

初期に報告した「top decileで最大90%の漏れ」は誤りであった。decile閾値が0.001–0.04であり、
流体セルを固体として数えていた。**Brinkman penalizationは beta ≳ 0.1 で既に機能しており、
alphaMax=2500で十分である。**

### 帰結

- **P11はP2の症状であり、独立した欠陥ではない。** ただし beta 0.7–1.0 帯は一度も
  生成されていないため、その帯での挙動は単調傾向からの外挿である。二値化により
  設計がその帯へ入ったら再確認する。
- **修正の優先順はP2が最上流。** 「二値化していない」は形状抽出の問題であるだけでなく、
  **目的関数値そのものが物体ではなく靄から来ている**という、より深い問題である。
- alphaMaxを上げても力が収束しないのは、グレーセルではなく**beta<0.1の裾**が
  支配しているためである。surrogateの欠陥ではなく設計場の性質である。

根拠: `work/brinkman_scoping/result.json`（`part5_beta_binned_reanalysis_supersedes_decile_framing`）、
`binned_leakage_results.json`

## P11 — Brinkman浸透層の格子解像（P2の症状として閉じる）

固体はBrinkmanの運動量シンク `alphaMax · beta` で課している。その浸透長は

```text
ell_p = sqrt(nu / alphaMax) = sqrt(0.01 / 2500) = 0.002 m
```

一方T0格子のセル幅は0.075–0.1 mであり、**セルは浸透層の37〜50倍大きい**。
流れを止めるはずの層が格子上に存在しない。

この比だけを見ると「Stage Tの固体は実際には透過体ではないか」という懸念が生じる。

**測定結果: この懸念は否定された。** 上記「統一的説明」のbeta帯別表のとおり、漏れは
beta ≳ 0.1 で既に平均1%未満であり、`alphaMax = 2500`で十分に塞いでいる。
浸透層がセルより小さいことは、界面を解像できないことを意味するが、**塞ぐこと自体は
できている。**

alphaMaxを上げても力が収束しないのは、抗力寄与の93%が`beta < 0.1`の裾から来ている
ためであり、penalizationの失敗ではなく設計場が靄である結果である。

したがって**P11はP2の症状として閉じる。** 唯一の留保は、beta 0.7–1.0帯が一度も
生成されていないため、その帯での挙動が単調傾向からの外挿である点。二値化で設計が
その帯へ入った時点で再確認する。

診断手順は`problem_resolution_plan_2026_09.md`§6.4。実測は`work/brinkman_scoping/`。

## P12 — Stage V参照が未資格（最重大・修正中）

body-fittedの全6ケースで次を確認した。

- `checkMesh`が`Failed 1 mesh checks.`（concave faces: coarse 48、fine 147–171）
- `SIMPLE: no convergence criteria found. Calculations will run for 500 steps.`
  実際に500反復で打ち切られ、収束宣言は出ていない

したがって既存証拠が示すのは「6ケースが完走しforce fileを生成した」ことまでである。
meshが有効、solverが収束、forceが格子独立、Stage Vが決定的参照——いずれも未成立。

**P1の否定的結果はこの参照の上に乗っている。** dragの3格子一貫反転は重要な観測として
保持するが、参照側の数値誤差を修復または上限評価するまで一般的No-Goへ昇格させない。

## P13 — 最適化ループの随伴・primal実行契約（最重大・bounded pathで解消）

`scripts/stage_t_python_loop.py:162`が`adjoint_iterations=1`を渡し、
`fixed_grid_primal.py::_patch_optimisation_dict`がテンプレートの`nIters 4000;`を
`nIters 1;`へ置換する。実ケースは`drag_adjoint_converged: False`、
`downforce_adjoint_converged: False`を記録しているが、ループの抽出処理は
`primal_converged`と有限性しか見ずに`topOSens`を消費した。

P0ベースラインの勾配は随伴713/1143反復で収束していたが、**最初の受理ステップ以降の
勾配は同じ資格を持たない。**

影響の切り分け:

- 候補A・Bの**目的値は本物**（各ステップを収束primalで再評価している）
- しかし「検証済み勾配が設計を駆動した」という主張は支持されない
- 順位検定は2形状の比較なのでこの欠陥に依存しないが、P12の影響は受ける

### 追記（2026-09-22）— 旧fail-open修正後に残るadapter問題

未収束adjointをgradientとして消費する旧問題はfail-closed gateで解消した。一方、PQ0後の
`make_oracle_from_compiled()` では `evaluate_values` と `evaluate_gradients` が同じ
`primitive_evaluator(state)` を呼ぶ。後者へ渡す `values` payloadは使われないため、実adapterが
そのまま接続されるとaccepted parentのprimalを再実行し得る。

さらに `OracleResult.adjoint_converged` はtrialでも必須boolで、payload欠落時の既定値は
`True` である。primal-only trialにadjointを要求する一方、欠落を合格にするため意味が矛盾する。

PQ0.1では次へ分離する。

- parent primal artifactを入力にadjointだけを実行し、欠落/不一致はfail-closed
- trialはprimal-onlyでadjoint statusを`not_applicable`
- accepted trial artifactを次parentで再利用
- API call countではなく実solver invocation IDで重複を検査

### 追記（2026-09-22）— PQ0.1/PQ0.2 closure

上記4項目はPQ0.1で実装され、PQ0.2の実OpenFOAM smokeでparent artifact reuse、trial
primal-only、bracket、rollback、resumeを確認した。従ってP13はbounded reduced pathについて
解消する。continuous-adjointとdiscrete primal FDの量的一致は別問題であり、P6のPath Bを
維持する。

## P14 — 射影が二重にかかる（高・未修正）

Python側が`beta = h_b(rho)`を作る一方、OpenFOAMケースは`regularise true; function linear;`の
ままである。実際の評価鎖は次になる。

```text
canonical rho -> Python射影 -> 保存的平均P -> OpenFOAM raw alpha
              -> OpenFOAM Helmholtz正則化 -> solver beta -> alphaMax·beta
```

実測（`work/stage_t_python_loop_v2_floor/iter_004_attempt_00`）:

| | 最大値 | 0.5超のセル |
| --- | --- | --- |
| Python側が注入した`rho` | 0.55 | あり |
| **ソルバが見た`beta`** | **0.436** | **0** |

Stage SはPython側の場を輪郭化するため、**Stage Tが流れ場に使った場とは別物**である。
対処は射影所有者をPythonへ一本化し、OpenFOAM側を`regularise false`にすること
（`problem_resolution_plan_2026_09.md` C3）。

## P15 — 最適形状が2セル厚で、格子が表現しきれない（最重大）

### 症状

罰則付き補間により設計は二値化したが、生成される物体は**約2セル厚のスラブ**である。
`thin_fraction_within_1cell_of_surface` は0.83–0.97、すなわち固体の83–97%が自身の表面から
1セル以内にあり、実質的に内部が存在しない。

結果として次が同時に起きる。

- `checkMesh`の「行列式の小さいセル」で全格子失格（24/98/303など）
- 力の積分が壊れる（Cd 7.5–17.8。健全な候補は1.2–1.3）
- **ダウンフォースが格子収束しない**

### 三つの独立な証拠

| 角度 | 測定 |
| --- | --- |
| 差分比 | Cd比 0.16–0.18（収束） vs downforce比 1.00–1.08（**非収束**） |
| 対照実験 | voxel化した8セル立方体は同一経路で`checkMesh`失敗ゼロ、開いた辺ゼロ、ドリフト面積2.00%・体積1.46% |
| メッシュ直接測定 | 実候補は濡れ面積が格子間で2.69–2.76%、体積2.25–2.32%変動。開いた辺9–60 |

**薄い物体は格子ごとに別の物体になっている。** 法線方向の力（ダウンフォース）は捉えられた
厚みを追うので収束せず、流れ方向の力（抗力）は鈍感なので収束する。観測と一致する。

### コードの問題ではない

marching cubesのスリバー洗浄（重度スリバーの90–100%除去、体積変化0.03%未満、watertight維持）を
実装しても、`checkMesh`失格は24/98/303 → 23/98/303とほぼ不変だった。
表面品質の問題ではない。

なお「抽出で体積を8–12%失う」という当初の記述は誤解を含む。`cell_threshold_volume`と
`surface_mesh_volume`の差の大半は**離散化の定義差**である（セル単位 vs marching cubesの補間）。
意味のある指標は再voxel化後の差で、厚い対照は**1.56%**、薄い候補は**7.74%**である。

### 対照立方体の測定値について

一時、対照立方体のドリフトを7.2%とする測定が報告され、上記の診断と矛盾した。原因は
**別のパイプラインを測っていたこと**である。誤った方は解析的STLの箱を直接snappyHexMeshへ
渡しており、voxel化と等値面抽出を飛ばしていた（位置も異なる）。正しい対照（voxel化→Stage S
全経路）の再測定は面積2.00%・体積1.46%で、当初の値と一致する。7.2%の測定は破棄する。

### 対処の検証結果（2026-09-13）

三つの候補を検証し、**最初の仮説は反証された。**

| 検証 | 結果 |
| --- | --- |
| robust erode（半径4セル、η_e=0.75） | **逆効果**。物体が16–36セルまで消失、表面1セル以内の固体率1.000 |
| 鋭い射影を止める（`b=0`、半径2、q=100） | **厚みを達成**。960–1,600セル、`local_p10`=4.0、median 4.0–5.66、表面率0.613–0.70 |
| 厚い候補の格子収束 | **ダウンフォースは依然非収束** |

#### 決定的な反証

ここで比較対象に採用した候補は `opt_q100_b0_step0_try0_block` である。960セルとは
physical `beta` の `n_gt_0.9=960` を指し、`local_thickness_cells_median=4.0` である。
`half_thickness_cells_median=1.0`、1次元推定slab厚は2.0セルなので、異なる厚さ指標を
混同しない。この候補は次を満たす。

| 指標 | 候補 | 対照（8セル立方体） |
| --- | ---: | ---: |
| `checkMesh` | 登録profileで全3格子合格、small-determinantゼロ | 同じ |
| 濡れ面積ドリフト | 2.25% | 2.0% |
| 体積ドリフト | 1.57% | 1.46% |
| Cdの差分比 | 0.384（収束） | — |
| **downforceの差分比** | **2.114（発散）** | — |

**幾何は格子間で安定しているのに、ダウンフォースは収束しない。**
したがって「薄い物体→格子ごとに別物体→非収束」という因果は、この候補について
**成立しない**。P15の当初の説明は限定的である。

なおraw `checkMesh`はV0/V1/V2の各格子で`Failed 1 mesh checks.`を報告している。
内容は登録済み`STAGE_V_QUALIFICATION_PROFILE_V1`が数値上限内で許容する
`Concave cells`のみで、small-determinant failureは0である。本節の「合格」はraw出力が
無警告という意味ではなく、登録profileによるqualification passを意味する。

#### 非定常仮説も棄却

鈍頭体（Cd 2.7–3.1、健全値の約2倍）に定常解が存在しない可能性を検査した。

- V2（18万セル）の残差履歴: 窓付き標準偏差が 9.6e-4 → 2.7e-7 へ単調減少。
  周期性なし、undamped driftなし、不動点へ収束
- pimpleFoamによる遷移再開（V0から5流過時間）: Cd=2.6754、downforce=0.6219 が
  7桁一致で不変。振動・後流成長なし

**限界**: 遷移検査はコストの都合でV0で実施した。粗い格子は細かい格子でのみ現れる
不安定性を減衰させうるため、V2での確証ではない。V2での遷移検査が、この判断を
暫定から確定へ変える唯一の証拠である。

#### 現時点の判断

ダウンフォースの非収束を**通常の意味での解像度不足**とする説明を作業仮説とし、
body-fitted V3のmesh、solver、force-stationarityを別々に判定した。結果は次節のとおりで、
実行qualificationは閉じたがgrid convergenceは閉じていない。

#### 正しい候補のV3結果（2026-09-20）

`opt_q100_b0_step0_try0_block`をvoxel `0.0125 m`で再実行した。V3は1,260,201セル、
minimum determinant 0.0271、small-determinant failure 0で、登録mesh profileを通過した。
`simpleFoam`は2237反復で`residualControl`を満たし、最終残差は
`Ux=1.50e-7, Uy=9.98e-7, Uz=3.01e-7, p=6.09e-7`だった。最終25%窓の力も
stationarity gateを通過した。したがってV3はmesh、solver、forceの全ゲートでqualifiedである。

| level | cells | Cd | downforce | Stage V qualification |
| --- | ---: | ---: | ---: | --- |
| V0 | 6,387 | 2.68528 | 0.61446 | pass |
| V1 | 31,710 | 3.01397 | 0.68146 | pass |
| V2 | 184,518 | 3.14010 | 0.82310 | pass |
| V3 | 1,260,201 | 3.13009 | 0.85302 | pass |

候補、V0–V3のraw/profile判定、残差、力定常性、実行時間、ignored `work/` artifactsの
SHA-256は`docs/evidence/stage_v_v3_requalification_2026_09.json`に固定した。

最細2格子ではCdの相対差が0.319%で登録上限2%を通過した。一方、downforceの絶対差は
`|0.85302-0.82310|=0.02993`で、登録上限0.005の約6倍である。V1→V2の差0.14164からは
大きく縮小したが、**downforceのstrict grid convergenceは未成立**である。

この結果は、当初の「薄い形状が格子ごとに別物になることが主因」という説明を反証し、
細分化でdownforce差が縮むという解像度仮説を方向としては支持する。ただしV3でも合格幅に
達していないため、通常の解像度不足だけを確定原因とはしない。次は全領域一様V4を自動的に
追加するのではなく、wake/壁面の局所refinement、格子収束外挿、定常/非定常モデル差を
一因子ずつ比較する。

なお副次的に判明した設計指針: **鋭いtanh射影はフィルタの長さスケールを打ち消す。**
厚い物体が欲しければ射影を鋭くしない方がよい。erode による強制は、この規模の設計では
物体を消す方向に働く。

**注意**: 単純な密度フィルタは公正に検定されていない。厚みは射影後の`beta`で測るが、
鋭いtanh射影（b=8, b=16）は遷移長`~1/b`のステップへ戻すため、フィルタの物理半径と独立に
薄い特徴が復活する。より根本的には、**密度フィルタは`rho_tilde`の勾配を縛るのであって、
超レベル集合`{beta > 0.5}`の厚みを縛らない。** これを閉じるのがrobust定式化である。

## P16 — Stage Vが解像できる最小差（判定基準）

今後のすべての順位主張は候補・response別の最新bandで判定する。次の表は固定domainへ
移る前のunion-box候補についての歴史的記録であり、現在のbandとして再利用しない。

| | ダウンフォース |
| --- | --- |
| 過去の観測ドリフト | 0.078 |
| 現候補のqualified V2→V3ドリフト | **0.02993** |
| 登録grid-convergence上限 | **0.005** |
| 検定に使ったペアの実差 | 0.0219 |
| 実差 / 現ドリフト | **0.73** |

したがって「全3格子で方向が一致した」は本物の観測だが、**差そのものは現在の最細格子間
ドリフトより小さい**。V3追加で0.078から0.02993へ改善したものの、0.0219差の順位を独立に
判別できる状態にはまだ達していない。

抗力は収束する（V1→V2で1.1–1.3%、閾値2%以内）ため、この制約はダウンフォース固有である。

### 固定domain参照への更新と一因子分離（2026-09-20）

旧V0–V3参照のunion-boxは候補と底面が約0.19 mしか離れておらず、地面干渉が未測定のまま
混入していた。宣言固定domain（bottom z=-0.6 m）下の同一候補はCd≈1.63–1.74、downforce
≈0.51–0.52となり、union-boxの絶対値・比率・Drift（0.02993を含む）は参照として移転できない。

固定domain下での一因子結果（`evidence/stage_v_fixed_domain_grid_study_2026_09.json`）:

| family | V1 | V2 | V3 | 最細DF drift | 登録bound |
| --- | ---: | ---: | ---: | ---: | ---: |
| plain | Cd 1.7395 / DF 0.5139 | Cd 1.6801 / DF 0.5093 | Cd 1.6297 / DF 0.5222 | 0.01291 | 0.005 |
| wake(level 3 box) | Cd 1.7348 / DF 0.5086 | Cd 1.6771 / DF 0.5048 | Cd 1.6282 / DF 0.5195 | 0.01470 | 0.005 |

- 6実行はすべてmesh profile・`residualControl`・force stationarityゲートでqualified
  （wake V3はendTime 3000で正しく棄却された後、endTime 6000への宣言付き継続で収束、計4259反復）。
- **wake近傍のlevel-3局所refinementは力を約0.003しか動かさず、V2→V3遷移のDF変動
  （0.013–0.017）を説明しない。** driftはwake解像度ではなくglobal refinement familyに
  付随する誤差であることが一因子比較で判明した。
- **定常/非定常比較（同一plain V2メッシュ、pimpleFoam 15 s = 5流過回数）**: 時間平均は
  定常点と一致（Δdownforce = -8.6e-5、ΔCd相対 = -0.09%、最終窓std ≈ 8e-8、シェッディング
  なし）。定常梯子点は非定常成分に汚染されていない
  （`evidence/stage_v_transient_check_2026_09.json`）。
- 定常/非定常因子は上記の比較で除外した。次はscheme因子を一因子で調べた。

### convection scheme因子（2026-09-21）

`bounded Gauss linearUpwind grad(U)`へ変え、V2→V3最細transitionを同じcandidate/domain/gateで
比較した（[`stage_v_downforce_drift_resolution_2026_09.md`](stage_v_downforce_drift_resolution_2026_09.md)）。

| family | drag relative drift | downforce absolute drift | 判定 |
| --- | ---: | ---: | --- |
| baseline upwind | 3.00% | 0.012907 | 両方fail |
| `linearUpwind` | **0.364%** | **0.010374** | drag pass、downforce fail |

全4 qualification gateは両armで通り、treatment V3は2289 iterationで収束した。dragでは
schemeが主要因で、`linearUpwind` familyは登録2% boundを満たす。downforceは改善が小さく、
baseline/treatmentとも三格子が非単調なのでGCIは出さない。現候補のhonestなdownforce
numerical bandは約0.0104で、grid-independent claimではない。

次は登録済み`evidence/stage_v_domain_boundary_factor_manifest_2026_09.json`を変更せず実行する。
その結果が出るまで、設計定式化を変えてdriftを見かけ上小さくしない。

## P17 — 候補面とStage V外周境界のclearanceが未検査（最重大）

最初のV3再実行は誤って別候補
`opt_q100_b0_step5_try1_block_keep_round`（physical `beta>0.9`が1,600セル）を対象にした。
この候補はV0/V1/V2でもsmall-determinant failureを持つため、P15の960セル候補のV3検定には
使えない。V3でも220セルが`minDeterminant=0.001`を下回り、mesh gateで棄却した。

220/220セルが`design_candidate` patchに接し、208/220セルは`top` patchにも接していた。
候補STLの`zmax=0.4 m`はblockMeshのtop `z=0.4 m`と一致し、`sideMin`との隙間も
V3の1セル幅`0.0125 m`程度しかない。現在のStage V格子は全geometryのunion boundsから
作られるため、許容領域端まで伸びた候補がCFD外周を動かし、候補面と外周が接触し得る。

一方、P15の正しい候補`opt_q100_b0_step0_try0_block`は外周から離れている。同じV3で
1,260,201セル、minimum determinant 0.0271、small-determinant failure 0となり、登録mesh
profileを通過した。この一因子比較から、先の失敗原因はuniform refinement一般ではなく、
候補固有の外周clearance違反である。

必要な修正はquality閾値の緩和ではない。Stage V case生成前に、候補面とfar-field各patchの
最小clearance、および候補が宣言されたdesign domain内にあることを物理長で検査し、違反時は
fail-closedにする。CFD外周は候補union boundsから暗黙生成せず、ProblemSpecが宣言する固定
far-field domainへ束縛する。P15の正しいV3についてはmesh passとsolver/force qualificationを
別々に記録する。

### 対処の実装（2026-09-20, WP1）

- Stage Vのouter boxを`grid.domain_bounds_m`（`(-1,-0.8,-0.6)`〜`(2,0.8,0.6)`）へ固定束縛
  する経路を`problem_spec_to_project_config` → `build_fields` → `blockMeshDict` /
  `case_metadata.json`まで通した。宣言domainがあるとき`padding_m`は0のみ許容し、extentが
  voxelの整数倍でない場合は`build_fields`がfail-closedする。
- `src/cfd_sdf/stage_v_domain_preflight.py`に、meshコマンド前に有限domain・voxel整合・
  候補in-box判定・6面の物理clearance（パッチ名 `inlet/outlet/sideMin/sideMax/bottom/top`）
  を検査するpreflightを実装した。marginは宣言されたバージョン付きprofile
  `stage_v_clearance_v1`の固定値 **0.25 m** であり、セル数由来でも結果由来でもない。
- `scripts/stage_t_filtered_ramp.py`の`mesh_sweep`と`phase_stagev_level`が
  `stage_v_domain_preflight.json`を`blockMesh`/`surfaceFeatureExtract`/`snappyHexMesh`/
  `simpleFoam`の前に書き、不合格時はSystemExitで打ち切る（solver launch artifact不発行）。
- 記録済み2候補をpreflightのみで判定した（実行なし）:
  `opt_q100_b0_step0_try0_block`（最小clearance 0.37396 m, `top`）= pass、
  `opt_q100_b0_step5_try1_block_keep_round`（最小clearance 0.19999997 m, `sideMin`）=
  fail（`clearance_below_declared_margin`）。  artifactは
  `work/filtered_ramp/wmin_0.2/stage_v_mesh/<candidate>/<level>/stage_v_domain_preflight.json`、
  証拠は`evidence/stage_v_domain_clearance_2026_09.json`。
- 検証: `compileall` + 展開済みテストの包括性向上後 **601 passed, 2 skipped**（新規
  `tests/test_stage_v_domain_preflight.py`、両記録候補のskip付きfixtureを含む）。
  これは契約・capability証拠であり、mesh品質・solver収束・target physicsの主張には
  用いてはならない。

### V14候補での再測定とV15対策（2026-09-24）

- v14の最終受理checkpointを`rho_projection`から0.4/0.5/0.6で再抽出したPQ4.1では、
  iso 0.5がdiscreteness、extraction profile、volume fidelityを通過した一方、
  `stage_v_clearance_v1`だけで不合格になった。したがって現時点のStage S blockerは、
  少なくともこの閾値ではclearanceへ局在する。
- v15は宣言domainの各面から設計セル中心を0.30 m内側へ制限するsupport boxを登録し、
  v14 checkpointのbox外design値を決定論的に0へしたbootstrapから開始する。
  この操作後のprojected volumeは`0.06202391606`、`mean_nd=0.00365951599`、
  `rho_projection>0.5`のsupport違反は0である。これはclearance合格の証拠ではなく、
  PQ4.1を再実行する前のtransform-level予防条件である。
- v15 entry preflightはalpha 1.0で合格した。start/candidateともsupport違反0で、候補の
  `mean_nd=0.00348178008`、projected volume `0.06216404077`、実trial downforce
  `2.01655864594`である。実bounded learning campaignは `paused_learning_budget`
  で停止した（10新規attempt・10受理、同一stateでのsupport違反0最終候補:
  downforce `2.10035503533`、projected volume `0.06406567400358908`、
  `mean_nd=0.003213044195919047`、収束window未成立）。support gateを通った最終候補でも、
  抽出面に対する完全なclearance preflightが合格するまではP17を閉じない。
- v15 checkpoint 10のPQ4.1では、`rho_projection` iso 0.5の抽出面が
  `stage_v_clearance_v1` preflightに合格した（iso 0.4はfeature shrink、iso 0.6は
  volume fidelityで除外）。ただしsolver実行での再確認は未実施のため、この合格は
  P17自体を閉じない（`evidence/pq4_1_v15_state_stage_s_entry_2026_09.json`）。
- v16終端（checkpoint 87、blocked stop）のPQ4.1でも、`rho_projection` iso 0.5の
  抽出面が修理後gateで`stage_v_clearance_v1` preflightに合格した。P17のclosure条件は
  変わらず、body-fitted mesh/solver実行での再確認まで閉じない
  （`evidence/pq4_1_v16_state_stage_s_entry_2026_09.json`）。

---

## 2026-09-12時点で実証できたこと（歴史的記録）

この節の表は初期closed-loop直後のsnapshotであり、現在のstatusではない。特にP6、P12、P16、
P18はその後のevidenceで更新された。現在の判断には冒頭一覧と各問題の最新追記を使う。

| 項目 | 結果 |
| --- | --- |
| canonical閉ループ | 46080 ⇄ 8192セルで成立。主問題161反復、随伴713/1143反復で収束 |
| 勾配連鎖の正しさ | 勾配方向で相対誤差0.56–1.03%（16実行、全収束） |
| cell order | `writeCellCentres`で実測導出（identityと判明、ただし初の実測裏付け） |
| Stage T最適化 | downforce 0.776 → 3.188（5受理ステップ、単調、各ステップ実計算で再評価）。**ただしP13により「検証済み勾配が駆動した」とは言えない。目的値の測定のみが有効** |
| Stage Sハンドオフ | 実形状を受理。再実行でSTLハッシュがbyte一致（決定論的） |
| Stage V | v2 specから直接駆動。3解像度、候補Bの2成分とも欠落なくメッシュ化、Cd単調収束。**ただしP12により参照として未資格** |
| 目的関数の健全性 | 空領域（ρ≡0）で drag = downforce = 0.0 ちょうど。幾何非依存のオフセットなし |

## 現在の未解決の問い（重要度順）

1. P19を修正して`rho_projection`を抽出したとき、PQ3.3のgeometry failureはどこまで
   field semanticの取り違えで説明されるか。
2. projected-volume targetとlevel内収束を使うPQ3.3bで、b=16のaccepted/converged/
   extractable candidateを作れるか。
3. P20の測定をfail-closedに直した完全Gateで、実candidateが`ready_for_stage_s=true`になるか。
4. P6はjoint canonical/source refinementまたは追加source gridで5% gateへ収束するか、
   Path Bに留まるか。
5. Stage V downforceの非単調driftは登録済みdomain/boundary因子で説明・縮小できるか。
6. baseline→T→Sの改善は、候補別numerical+extraction uncertaintyを超えるか。

## 2026-09-12時点の主張境界（歴史的記録）

監査の§13に従った当時の記録である。現在は本台帳の最新追記と
`downforce_optimization_architecture_plan_2026_09.md` §2/§14/§15を優先する。

**主張できる**

- T→S→Vの制御経路は実行できる
- 既存の灰色候補ではcross-fidelity rankingが否定的だった（未資格の参照に対して）
- 灰色密度と中実STLの不一致は明確な交絡因子である
- native ISQPをPython側optimizerへ移す判断は妥当である
- Stage V全6ケースは完走したが、mesh/solver収束ゲートを通っていない

**主張できない**

- 原因が二値化と格子の2件に確定した
- 最新の二値化最適化が正しい勾配で進んだ
- Brinkman surrogateが成立した、または成立しないと確定した
- Stage V downforceが格子収束した
- この縮約問題の結果がFSAE全車の高Re空力へ外挿できる

## 次の一手（2026-09-22, PQ3.3後）

実行順は`phase_plan.md` §11、詳細は
[`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md)
に従う。

1. PQ3.3a: 保存済みcandidateを四場へ再構成し、`rho_projection`で安価に再抽出する。
2. PQ4.0a: self-intersection、gap、minimum-width、volume calibrationをfail-closedに直す。
3. PQ3.3b preflight: projected-volume target backend、到達可能性、manifestを固定する。
4. PQ3.3b: b/q levelごとに再評価・再最適化し、最終levelのaccepted/converged stateを得る。
5. PQ4.1: 正しいgeometry fieldで完全なcomposite Gateを実行する。
6. Gate合格後のみ、drag/downforce surface FDと最大一つのStage S updateへ進む。
7. PQ2は並行実行可能。PQ5/PQ6はStage S後の独立検証・target-physics ladderとして維持する。

直近の判定点は、**PQ3.3の抽出失敗が`beta_solver`と`rho_projection`の取り違えでどこまで
説明されるか**である。これを確定する前に長時間PQ3.3bを開始しない。
