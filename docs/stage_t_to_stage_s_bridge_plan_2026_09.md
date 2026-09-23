# PQ3.3 後の Stage T → Stage S ブリッジ計画

Date: 2026-09-22

Status: adopted detailed plan; `phase_plan.md` §11 に従う

Evidence baseline: commit `db20610` までの登録済み実行結果
Scope: reduced laminar downforce problem における、Stage T の終端候補作成、
密度から形状への抽出、Stage S の最初の body-fitted shape step

この文書は、PQ3.3 までの実装と実 OpenFOAM 実行から分かったことを整理し、
次の高コスト実行を開始する条件を固定する。ロードマップと進捗の正本は
[`phase_plan.md`](phase_plan.md)、問題台帳は
[`problem_register_2026_09.md`](problem_register_2026_09.md) である。

## 1. 結論

Stage T の実行経路は、研究用の限定構成として成立した。実 OpenFOAM primal、parent
adjoint、Path B の centered primal-FD bracket、trial primal、accept/reject、rollback、
checkpoint/resume、projected-volume inequality を一つのループで動かせる。PQ3 では実際に
3 step 改良し、PQ3.3 では RAMP 後の solver field が登録済みの離散性指標を満たした。

一方、**Stage S へはまだ進まない**。理由は二つある。

1. PQ3.3 の `b=16, q=100` 区間は 0 accepted / 3 rejected で、最終 transform の下で
   再最適化された終端ではない。投影体積も `0.02745` から `0.01302` へ低下した。
2. 現在の candidate materialization は、形状占有率として定義した
   `rho_projection` ではなく、OpenFOAM が使う RAMP 後の `beta_solver` を
   `rho_projected` という名前で抽出している。したがって現在の 0.4/0.5/0.6 sweep は、
   採用計画が意図した等値面を検査していない。

次の作業は、直ちに 1.5–2 時間級の PQ3.3b を回すことではない。最初に、既存の PQ3.3
候補を正しい `rho_projection` で再 materialize し、Stage S entry gate の測定実装を修正して、
安価な再判定を行う。その後にだけ、投影体積を直接制御する PQ3.3b を新しい manifest で
実行する。

## 2. 現在地

| Slice | 現在の判定 | 証拠の意味 | 残り |
| --- | --- | --- | --- |
| PQ0 | pass | compiler、transform、loop、binding の部品能力 | target physics の証明ではない |
| PQ0.1 | pass | downforce-only + projected-volume の declared/solved 一致、oracle 分離、Path B bracket | bounded reduced problem の範囲 |
| PQ0.2 | capability pass | 実 OpenFOAM parent/trial/bracket/rollback/resume | 改善 claim はない |
| PQ1 | Path B | 符号と epsilon plateau は安定、5% gate は不合格 | magnitude 補正は禁止 |
| PQ1.1 | 実行済み | source mesh gate pass、canonical/source 結合依存を測定 | 登録済み第三 source-grid level は未実行 |
| PQ3 | pass | 実 OpenFOAM で最大 3 accepted step の bounded closed loop | production optimizer 資格ではない |
| PQ3.1 | 部分達成 | solver field は離散、抽出不成立 | b=16 で 0/12 accepted |
| PQ3.2 | fail | 上限制だけでは budget を満たさず、射影で material が消える | 設計方針を PQ3.3 へ変更 |
| PQ3.3 | 部分達成 | `beta_solver` の mean_nd 0.00388、max 0.94395 | 最終段 0 accepted、投影体積低下、誤った場で抽出 |
| PQ4.0 | composite gate 実装済み | local pass が global ready を上書きしない | self-intersection、gap、width、volume calibration を修正する |
| PQ4.1 | 未着手 | 新しい正しい候補に対する完全 Gate | PQ3.3a/PQ3.3b 後 |
| PQ2 | 未着手 | Stage V downforce 数値参照 | Stage T bridge と並行可能 |
| PQ5 / PQ6 | 未着手 | 独立検証 / production・target-physics | Stage S 後 |

現行の authoritative plan は PQ0–PQ6 までを定義している。ユーザー提供の進捗にある
`PQ7` は現行 `phase_plan.md` では未定義であるため、この計画では新しい意味を割り当てない。

## 3. 実装と実行から分かったこと

### 3.1 Stage T の中心的な実行契約は動いた

PQ0.1/PQ0.2 により、過去に分離していた compiler、DesignTransform、projected-volume、
OpenFOAM oracle、acceptance controller、Path B bracket が一つの実経路になった。PQ3 の
3 accepted step は、少なくとも次を示す。

- 提案方向を実 primal で再評価できる。
- centered FD が支持しない proposal を棄却できる。
- volume 制約、rollback、checkpoint lineage を同じ candidate に結び付けられる。
- Stage T は「コードだけ存在する」状態から、限定された実 solver closed loop へ進んだ。

これは capability / bounded numerical evidence である。勾配の 5% gate、Stage V downforce
reference、抽出後の物理同一性が未成立なので、production optimizer や target-physics の
証明ではない。

### 3.2 上限制だけでは、抽出可能な material を作る誘因にならなかった

PQ3.2 では、filter radius を 0.15 m に増やしても、上限制だけの backend は volume budget を
使い切らなかった。`b=0` の `beta_max` は約 0.417 に留まり、`b=8/16` の tanh projection が
sub-threshold field をほぼ消した。最終 projected volume は 0.00283 だった。

したがって、現在の downforce 勾配と上限制の組合せでは「material を増やすこと」と
「空力的に有利な方向へ移すこと」を同時に保証できない。continuation 中の volume target は
候補形成の補助として合理的である。ただし最終問題の物理制約は、あくまで
`V(rho_projection) <= V_max` である。

### 3.3 raw design volume を満たしても、投影体積は維持されない

PQ3.3 の `VolumeTargetBackend` は

```text
mean(rho_design_new[active]) = target
```

を満たす。現在の実装は `active = objective_gradient != 0` とし、move box 内で raw design
の平均値を二分探索している。これは採用された制約

```text
V(rho_projection) <= V_max
```

とは異なる量である。`b=0` では objective が -2.727、projected volume が 0.02745 まで進んだが、
`b=8/16` で projected volume は 0.01469 / 0.01302 へ低下した。raw design の target を維持しても、
projection threshold の両側にどう分布するかは拘束されないためである。

### 3.4 continuation level を変えると、同じ設計でも別の最適化問題になる

`b` と `q` を変えると、同じ `rho_design` でも `rho_projection`、`beta_solver`、objective、
volume gradient が変わる。PQ3.3 の `b=0` objective -2.727 と `b=16` objective -0.190 を
「同じ問題で性能が悪化した」と直接比較することはできない。正しい比較は、各 level の
新しい parent を実 primal/adjoint で評価し直し、その level 内での accepted history と
stationarity を見ることである。

### 3.5 「離散」と「抽出可能」は別の性質である

PQ3.3 の現在の hard gate は、active domain 全体の `beta_mean_nd <= 0.01`、
`max(beta_solver) >= 0.9`、volume upper bound の三つである。広い void 領域は global mean_nd を
小さくし、少数の near-solid cell が max gate を通せる。この二指標だけでは、連続した
material、十分な局所厚さ、root 接続、抽出後の volume/centroid、surface fidelity を保証しない。

今後は少なくとも次を同時に記録する。

- global mean_nd と material-support 上の正規化 grayness
- `0.1 < rho_projection < 0.9` の cell 数・体積
- `rho_projection >= 0.9` の cell 数・体積・最大 component 比
- component 数、root attachment、forbidden-mask 侵入
- local thickness、void width、component 間 gap
- 抽出前後の volume、centroid、IoU、Hausdorff/Chamfer または両方向 surface distance
- watertightness、winding、non-manifold edge、self-intersection

### 3.6 現在の抽出は、意図した geometry field を使っていない

採用した state chain は次である。

```text
rho_design
  -> cone filter
rho_filtered
  -> tanh projection
rho_projection       # volume と geometry occupancy の基準
  -> RAMP
beta_solver          # OpenFOAM Brinkman interpolation
  -> beta_max * beta_solver
alpha_brinkman
```

RAMP は

```text
beta_solver = p / (1 + q (1 - p)),  p = rho_projection
```

である。`q=100` のとき、`beta_solver=0.4/0.5/0.6` はそれぞれ
`rho_projection≈0.9854/0.9902/0.9934` に相当する。逆に
`rho_projection=0.4/0.5/0.6` に対応する solver threshold は
`beta_solver≈0.00656/0.00980/0.01463` である。

したがって、PQ3.3 で `beta_solver` を 0.4/0.5/0.6 で contour した sweep は、
`rho_projection` の 0.4/0.5/0.6 sweep より極端に material を削る。0.5 contour の
revoxelization が空になったことは重要な観測だが、採用計画の geometry occupancy が
空である証拠にはならない。

現時点では fail-closed の `ready_for_stage_s=false` を維持する。ただし PQ3.3b の必要性と
抽出不能の原因は、正しい場で再判定してから確定する。

### 3.7 composite Gate に残る測定上の欠陥

PQ4.0 は「local extraction pass が global ready を上書きしない」論理を正しく直した。
一方、現在の個別測定には次の問題が残る。

1. self-intersection は mesh と同じ mesh の boolean intersection を呼んでおり、
   自己交差の検出になっていない。`not_evaluated` も global failure に入らない。
2. component 間 gap は `distance_transform_edt(~material)` を material cell 上で読むため
   0 になり、component 間距離を測れていない。
3. `thickness_ridge_m_p5` を `minimum_solid_width` と呼んでおり、ProblemSpec の
   minimum semantics と一致しない。
4. `volume_fidelity_v1` が参照する calibration artifact は surface-distance calibration であり、
   volume threshold の 0.25 / 0.20 / 0.02 m³を測定していない。

このため PQ4.0 の合成論理は残しつつ、PQ4.1 の前に各測定を修正・校正する。

### 3.8 evidence identity と artifact サイズも修正が必要である

`docs/evidence/pq3_3_volume_target_2026_09.json` は manifest path は PQ3.3 を指すが、
`artifact_id` と `issue` が PQ3.2 のままである。また `final_design_rho` を JSON に直接埋め込み、
一つの evidence file が約 46,000 行になっている。

既存 evidence は実行時記録として上書きしない。訂正 artifact から元 JSON の SHA-256 を参照し、
ラベル訂正、場の意味、再判定結果を append-only で記録する。今後の大配列は VTI/NPZ に保存し、
JSON には path、shape、dtype、SHA-256、要約統計だけを置く。

## 4. 採用するブリッジ構成

Stage T 自体を捨てたり、直ちに MMA/GCMMA や robust three-field へ広げたりしない。
現在の Python-owned loop と実 OpenFOAM oracle を保ち、次の境界だけを明確にする。

```text
Stage T optimization
  rho_design -> rho_filtered -> rho_projection -> beta_solver -> OpenFOAM
                         |               |
                         |               +-- solver response / adjoint audit
                         +-- volume constraint / Stage S geometry

Stage T terminal bundle
  four named arrays + transform hash + candidate hash + solver artifact hashes
                         |
                         v
qualified rho_projection iso-surface
                         |
                         v
Stage S body-fitted baseline -> surface FD -> one shape step
```

`rho_projection` と `beta_solver` は同じ candidate lineage から生成するが、同じ配列名にはしない。
Stage T objective の solver consistency は `beta_solver` で、Stage S geometry consistency は
`rho_projection` で判定する。

## 5. 実行計画

### Work A — PQ3.3a: 既存候補の意味論修復と安価な再判定

高コスト CFD を追加せず、PQ3.3 の保存済み `rho_design` と transform から全中間場を再計算する。

1. 元 evidence、manifest、script、ProblemSpec、template、candidate の SHA-256 を固定する。
2. `rho_design`、`rho_filtered`、`rho_projection`、`beta_solver` を別配列で出力する。
3. 再計算した `beta_solver` が実 solver 注入場と tolerance 内で一致することを確認する。
4. `rho_projection` に対して登録済み 0.4/0.5/0.6 sweep を実行する。
5. 参考値として、RAMP の厳密な threshold mapping を使った `beta_solver` sweep も実行し、
   二つの mask が一致することを確認する。
6. PQ3.3 evidence の誤った `artifact_id` / `issue` は、元 file の hash を持つ訂正 artifact に記録する。

**Exit Gate A**

- 四つの場の名称、式、shape、dtype、hash が一意である。
- `beta_solver = RAMP(rho_projection)` と `alpha = beta_max * beta_solver` が tolerance 内で成立する。
- mapped threshold における二つの material mask が一致する。
- 既存 raw evidence を変更していない。

この再判定は、現候補の geometry diagnosis を正すためのものとする。`b=16` で accepted step が
ないため、仮に抽出指標が通っても、それだけで Stage S-ready には昇格させない。

### Work B — PQ4.0a: Stage S entry 測定の fail-closed 修復

1. self-intersection を実際の triangle-triangle broad/narrow phase または資格化済み library で測る。
   必須 profile で測定不能なら fail とする。
2. component 間 gap を、各 component の境界間最短距離として測る。material 内の EDT を
   material cell 上で読む現行式は廃止する。
3. minimum width の metric を ProblemSpec と一致させる。p5 を使う場合は
   `ridge_width_p5` と明記し、minimum の代用にしない。minimum を使う場合は voxel
   quantization と孤立ノイズの扱いを解析 fixture で事前校正する。
4. binary analytic shapes を使い、source volume、surface volume、revoxelized volume の
   relative/absolute error を測定して volume profile を登録し直す。
5. self-intersection、two-component gap、one-cell thin feature、volume threshold 境界、
   unavailable dependency の fail-closed test を追加する。

**Exit Gate B**

- 各 hard gate が、pass / fail / not-applicable / not-evaluated を区別する。
- 必須項目の not-evaluated は `ready_for_stage_s=false` になる。
- profile の各数値が、対応する calibration artifact を参照する。
- clean analytic candidate と意図的な defect candidate の両方で回帰 test が通る。

### Work C — projected-volume target backend の実装と CFD 前 preflight

現在の `VolumeTargetBackend` をそのまま長時間実行へ使わない。新しい backend は、candidate
`rho(kappa)` に対して

```text
phi(kappa) = mean(rho_projection(rho(kappa))[design_active])
```

を評価し、`phi(kappa) = V_target` を move box 内で解く。

実装要件:

- active set は `objective_gradient != 0` から推定せず、transform/ProblemSpec の
  `active_design_mask & allowed & ~forbidden & ~fixed_solid` を使う。
- low/high の attainable volume を先に評価し、target を bracket できなければ fail-closed にする。
- 二分探索後に `|V_projection - V_target|` を再検査し、未達を成功として返さない。
- metadata は raw design mean と projected volume を別名で記録する。
- mask、filter、projection、move box、zero-gradient cell、unreachable target を test する。
- identity transform と `b=8/16` の双方で、解析 FD と volume measurement が一致する。

最初の `V_target` は raw design target 0.10 を流用しない。PQ3.3 の最後の `b=0` accepted state の
projected volume 0.027449593... を canonical artifact から再計算し、その値またはそれ以下の
preregistered 値を使う。必ず `V_target <= V_max` とする。現在の `V_max≈0.07633` は変更しない。

実 CFD 前に、保存済み candidate と move box だけで次を計算する。

- `b=8, q=30` で target が到達可能か。
- `b=16, q=100` で target が到達可能か。
- `phi(kappa)` が二分探索区間で単調非減少か。
- 一段の continuation で target が到達不能なら、同じ campaign 中に設定を変えず停止する。
  必要な中間 level は別 manifest で登録する。

**Exit Gate C**

- projected-volume target の unit/analytic tests が通る。
- 保存済み state で各予定 level の target が move box 内に bracket される。
- target、Vmax、transform schedule、move limit を結果前に固定できる。

### Work D — PQ3.3b: level ごとの再最適化

Work A–C を通過した後、新しい immutable manifest で実 OpenFOAM campaign を開始する。
過去の PQ3.3 manifest、output directory、evidence file は再利用・上書きしない。

#### 固定するもの

- 入力 candidate hash と四つの state array hash
- ProblemSpec / compiled problem / source grid / canonical grid
- OpenFOAM image/version、template hash、solver controls
- filter radius 0.15 m、eta 0.5
- continuation levels、各 level の q、move limit
- `V_target`、`V_max`、volume tolerance
- bracket epsilon/noise floor、acceptance profile
- 最小・最大反復数、収束判定、連続 reject 停止数

#### level の実行規則

1. 新しい `b/q` に切り替えた直後、parent primal/adjoint を必ず再計算する。
2. objective 改善は同じ `b/q` level 内だけで比較する。
3. 各 proposal は Path B centered primal-FD bracket と実 trial primal を通す。
4. projected-volume target は candidate proposal の形成に使うが、全 accepted state は元の
   `V(rho_projection) <= V_max` も満たす。
5. 一つの level を抜けるには、最低 10 accepted iteration を実行した上で、直近 3 accepted step が
   次を満たすことを要求する。
   - `|V_projection - V_target| <= 1e-4`
   - 正の objective 改善量が `1e-4` 以下で、かつ採用判定の noise threshold (`1e-6`) より大きい
   - `mean(abs(delta rho_projection)) <= 1e-3`
6. 最大 iteration は manifest に固定する（v4 は level あたり 30）。同じ parent、同じ
   alpha ladder の全候補が reject された場合、決定論的な再試行は新しい候補を作らないため
   その時点で停止する。target 到達不能、solver/geometry gate failure でも停止する。
7. `b=16` で少なくとも一つ accepted step がない campaign を terminal candidate と呼ばない。

体積 equality target は continuation の数値的補助であり、物理問題の新しい equality constraint
ではない。`b=16` で形状が安定した後、同じ candidate を元の projected-volume upper bound の
下で再評価し、target 補助を外しても feasibility と objective が維持されることを terminal
record に残す。

**Exit Gate D**

- 全 accepted state が real primal、Path B bracket、projected-volume upper bound を通る。
- b=8 と b=16 の各 level で登録済み convergence 判定を満たす。
- b=16 で accepted state があり、terminal evaluation が target 補助なしでも feasible である。
- accepted/rejected history、checkpoint/resume、artifact hash が再現可能である。

### Work E — terminal candidate の materialization と PQ4.1

PQ3.3b の terminal candidate だけを、四場 bundle から `rho_projection` を geometry source として
materialize する。`beta_solver` は OpenFOAM response lineage の audit field として残す。

hard gate は次の論理積とする。

```text
ready_for_stage_s =
  lineage
  and terminal_stage_accepted
  and projected_volume_feasible
  and projection_discrete_enough
  and solver_field_discrete_enough
  and projection_to_solver_transform_consistent
  and extraction_fidelity
  and volume_fidelity
  and width_void_gap
  and components_root
  and manifold_self_intersection
  and clearance
```

threshold sweep の選択規則は `require_ready_for_stage_s=true` のままとする。一つも合格しなければ
`selected_threshold=null` で停止し、最も近い threshold を手動採用しない。

**Exit Gate E**

- `ready_for_stage_s=true` の実 candidate が一つ以上ある。
- 選択 threshold、source field、transform、candidate、surface、revoxelized volume の hash が
  同じ handoff manifest に束縛される。
- OpenFOAM solver field と Stage S geometry field の違いが、名前と式で追跡できる。

### Work F — Stage S surface FD と一つの shape update

Exit Gate E 後に初めて Stage S baseline を登録する。

1. body-fitted baseline mesh と drag/downforce response を資格化する。
2. surface normal、force direction、objective sign を固定する。
3. drag と downforce の directional derivative を別々に centered FD で確認する。
4. epsilon plateau、relative tolerance、absolute noise floor を実行前に登録する。
5. 両 response の surface FD が通った場合だけ、一つの小さな shape update を実行する。
6. update 後に volume、width、gap、root、clearance、mesh quality、solver stationarity を再評価する。

FD が不合格なら Hamilton–Jacobi evolution、reinitialization の長時間反復、複数 shape step へ
進まない。

### Parallel Work — PQ2

PQ2 の Stage V domain/boundary factor は Work A–E と独立に実行できる。登録済み manifest を
変更せず、factor を一つずつ測る。PQ2 が未完でも Stage S の実行 capability は調べられるが、
Stage V を truth とした改善、cross-fidelity ranking、target-physics claim は作れない。

PQ5 は baseline / Stage T / Stage S の required pairs と三格子以上の独立検証、PQ6 はその後の
robust fields、必要なら MMA/GCMMA、turbulence・finite wing・vehicle interference・physical
validation である。

## 6. 停止条件と分岐

| 観測 | 判断 | 次の行動 |
| --- | --- | --- |
| 正しい `rho_projection` 抽出で現候補の fidelity が大幅改善 | 旧診断は field semantic の交絡を含む | それでも terminal accepted/convergence がないため PQ3.3b を短縮せず、manifest を再検討 |
| projected target が move box 内で到達不能 | backend tuning ではなく continuation step が大きすぎる | 高コスト run を開始せず、新しい中間 level manifest を登録 |
| b=8 または b=16 で登録 alpha ladder の全候補が reject | 同じ parent で再試行しても新候補は生じない | campaign 停止。objective/volume/gradient のどこが阻害したか一因子診断 |
| target は維持するが抽出 fidelity が不合格 | volume ではなく topology/feature-scale が原因 | robust formulation または geometry policy を別 work package として登録 |
| `rho_projection` は良いが `beta_solver` response が消える | RAMP continuation が surrogate と geometry を分離している | q schedule と Brinkman interpolation を再資格化。Stage S へ進めない |
| PQ4.1 が pass | 初めて Stage S baseline 登録可 | drag/downforce surface FD へ進む |
| Stage S FD が fail | shape derivative 未資格 | one-step update を実行しない |

同一 campaign 内で threshold、target、filter radius、b/q schedule、move limit、gate tolerance を
結果に合わせて変更しない。変更が必要なら、旧結果を failed/diagnostic として保存し、理由を記した
新しい manifest を作る。

## 7. 成果物

### PQ3.3a / PQ4.0a

- 四場 candidate bundle と SHA-256
- PQ3.3 evidence correction artifact
- geometry-field rejudgment report
- self-intersection/gap/width/volume calibration artifact
- gate regression tests

### PQ3.3b

- preregistered manifest とその SHA-256
- projected-volume reachability preflight
- per-level parent/accepted/rejected/bracket records
- checkpoint/resume provenance
- terminal four-field bundle
- evidence JSON。大配列は含めず、外部 artifact の path/hash を参照する

### PQ4.1 / Stage S

- threshold sweep report
- composite entry verdict
- selected surface/SDF/revoxelized artifact と lineage
- body-fitted baseline registration
- drag/downforce surface FD report
- 最大一つの shape update と post-update qualification

## 8. 許される主張

現時点で主張できるのは、次の範囲である。

- bounded Path B 条件の下で、Stage T の実 OpenFOAM closed loop は動く。
- volume upper bound だけでは、現在の downforce 問題で抽出可能な material を形成しなかった。
- raw design volume target は projected volume を維持せず、projection continuation で体積と objective
  が低下した。
- PQ3.3 の solver field は登録済みの二つの離散性指標を満たした。
- 現行 composite gate は fail-closed に `ready_for_stage_s=false` を返した。
- 現行抽出は `beta_solver` と `rho_projection` の semantic mismatch を含み、正しい geometry
  field での再判定が必要である。

まだ主張できないもの:

- qualified Stage S candidate
- Stage S の一 step 改善
- Stage T / Stage S / Stage V 間の性能順位
- grid-independent downforce
- production optimizer、GCMMA、robust topology の成立
- FSAE 全車、高 Reynolds 数、乱流、実験との一致

この計画の最初の判定点は **PQ3.3a で、現候補の抽出失敗が field semantic の取り違えでどこまで
説明されるか** である。次の高コスト判定点は **projected-volume target を使った PQ3.3b が、
最終 transform の下で accepted・converged・extractable な候補を作れるか** である。
