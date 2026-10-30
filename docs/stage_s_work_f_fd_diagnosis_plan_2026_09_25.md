# Stage S Work F — surface-FD 不一致の診断計画

作成日: 2026-09-25

対象スナップショット: `feat/p0-openfoam-closed-loop` / `f914c16b1e5b8bbfbe35433e4c513741ed9b39bc`

状態: 実行前の計画

この文書は、Work F centered-FD campaign の fail-closed verdict を受けた次の診断計画である。
ロードマップ、状態、実行順序の正本は引き続き [`phase_plan.md`](phase_plan.md)、問題台帳の正本は
[`problem_register_2026_09.md`](problem_register_2026_09.md) とする。本書は両文書に従属し、既存の
manifest、結果、閾値を置き換えない。

## 1. 目的

目的は、analytic surface derivative と centered FD の方向依存・response 依存の不一致を、
一度に一因子ずつ切り分けることである。

次の問いに順番に答える。

1. prescribed control-point direction は、morpher 後の実変位として意図どおり実現しているか。
2. analytic derivative の objective、符号、面積重み、正規化、active-variable contraction は FD response と同じ量を表しているか。
3. 上の二つが正しい場合、一次精度 `upwind` primal discretization と continuous adjoint の不整合が主要因か。
4. 原因を修正した後、登録済みの全方向・全 epsilon で drag/downforce の 5% gate を通過できるか。

最終目標は、両 response の完全な derivative qualification である。gradient-aligned directions だけの合格や、
符号一致だけでは完了としない。

## 2. 現在の証拠

### 2.1 完了しているもの

- base adjoint qualification は合格済み。
- active space は内部 `6 x 6 x 6` control points の 3 components、合計 648 variables。
- `varID = 3 * cp_id + component` の写像は OpenFOAM source semantics に拘束済み。
- 4 本の登録 direction は unit infinity norm の不変 artifact として保存済み。
- 32 perturbation sides は geometry、clearance、mesh gate を全件通過済み。
- 32 perturbation primals は residual、force stationarity、`checkMesh` gate を全件通過済み。
- 全 32 centered-FD rows で analytic/FD の符号は一致。
- epsilon ladder 全体で比がほぼ一定で、単純な刻み幅依存は観測されていない。

主要 evidence:

- [`evidence/stage_s_work_f_adjoint_qualification_2026_09.json`](evidence/stage_s_work_f_adjoint_qualification_2026_09.json),
  SHA-256 `f0bec416540d3faf7f78dba09bcd3b2cb647740cf90fb53b4038cf9b2dcea606`
- [`evidence/stage_s_work_f_perturbation_sides_2026_09.json`](evidence/stage_s_work_f_perturbation_sides_2026_09.json),
  SHA-256 `01aeda492f43e76e9dad173599f339ba48f9adb8dc5744de062de7ce47cbc9db`
- [`evidence/stage_s_work_f_surface_fd_result_2026_09.json`](evidence/stage_s_work_f_surface_fd_result_2026_09.json),
  SHA-256 `048a2f9307d36a645e76dee7fac26c6325568888cfaa28063cf5685a4acbc9ee`

### 2.2 現在の verdict

| response | direction | FD / analytic | 最大相対誤差 | 判定 |
| --- | --- | ---: | ---: | --- |
| downforce | `downforce_gradient_aligned` | 約 1.04086 | 約 4.09% | pass |
| downforce | `drag_gradient_aligned` | 約 1.02793 | 約 2.79% | pass |
| downforce | `random_seed_11` | 約 1.0857 | 約 8.58% | fail |
| downforce | `random_seed_2026` | 約 0.8796 | 約 12.04% | fail |
| drag | `downforce_gradient_aligned` | 約 1.02661 | 約 2.66% | pass |
| drag | `drag_gradient_aligned` | 約 0.95949 | 約 4.05% | pass |
| drag | `random_seed_11` | 約 1.0376 | 約 3.76% | pass |
| drag | `random_seed_2026` | 約 1.4593 | 約 45.93% | fail |

最終状態は次のとおり。

```text
both_responses_pass=false
shape_update_allowed=false
```

### 2.3 現時点の解釈

不一致は epsilon に対してほぼ一定であり、direction と response に依存している。したがって、最初から
epsilon を変更したり CFD を全件再実行したりせず、既存 artifact だけで確認できる写像・意味論を先に監査する。

同一の `random_seed_2026` に対して downforce 比が約 0.88、drag 比が約 1.46 であるため、全方向に共通する
単純な scalar scaling error だけでは説明しにくい。ただし、direction-dependent な morpher clipping、
control-point movement の実現差、surface-area weighting、response-specific adjoint semantics はまだ候補として残る。

## 3. 守る契約

診断中は次を変更しない。

- 元の 4 directions
- epsilon ladder: `1e-4`、`2.5e-4`、`5e-4`、`1e-3 m`
- 相対誤差上限 5%
- sign agreement rule
- epsilon plateau rule
- near-zero rule
- 元の response identities
- 元の Work F baseline、mesh profile、solver qualification profile
- 既存 evidence とその hash

追加結果はすべて append-only artifact とする。観測後に元 manifest、direction、epsilon、tolerance を編集しない。
診断 pass を derivative qualification pass や shape-update permission に読み替えない。

## 4. 実行順序

```text
D0 文書整合
  -> D1 realized-direction audit（solver-free）
    -> D2 response/sensitivity semantics audit（solver-free）
      -> 原因が特定できたか判定
        -> Yes: 修正案を別 checkpoint で登録
        -> No: D3 bounded discretization diagnostic
          -> D4 full requalification
            -> 両 response pass の場合のみ D5 one-step manifest
```

D0〜D2 では新しい OpenFOAM solver run を行わない。D3 以降は、直前の結果と独立した manifest を登録してから
実行する。

## 5. D0 — 文書と verdict の整合

### 目的

machine-readable evidence と正本文書の表現差を解消し、診断対象を一意にする。

### 作業

1. `phase_plan.md` 上部の Stage S summary を、campaign 実行済み・complete qualification fail・shape update blocked に更新する。
2. drag の `random_seed_11` は 3.76% で pass であることを正しく記載する。
3. 「両 response の全 random directions が fail」と読める表現を修正する。
4. [`current_state_and_next_plan_2026_09_25.md`](current_state_and_next_plan_2026_09_25.md) を
   pre-campaign historical snapshot と明示する。
5. 過去の raw evidence、manifest、hash は変更しない。

### 完了条件

- prose と `stage_s_work_f_surface_fd_result_2026_09.json` の pass/fail matrix が一致する。
- overall verdict は `both_responses_pass=false`、`shape_update_allowed=false` のまま保持される。

## 6. D1 — realized-direction audit

### 目的

prescribed した 648-variable direction と、各 plus/minus case で実際に適用された control-point movement が
一致しているかを、CFD response を使わずに検証する。

### 実装範囲

各 `(direction, epsilon, sign)` case から control-point state または movement を読み、次を再構成する。

```text
delta_odd  = (x_plus - x_minus) / (2 * epsilon)
delta_even = (x_plus + x_minus - 2 * x_base) / (2 * epsilon)
```

各 case について次を記録する。

- active `varID` ordering
- prescribed direction hash
- realized `delta_odd` hash
- inactive/boundary component の最大変位
- infinity norm、L2 norm
- prescribed/realized cosine similarity
- prescribed/realized absolute・relative差
- plus/minus の odd symmetry error
- even component の大きさ
- morpher による clipping、bounding、permutation の有無
- control points、moved mesh、moved surface の hash lineage

さらに、両 response の raw analytic gradient `g` に対して、次の二つを併記する。

```text
d_analytic_prescribed = g dot direction_prescribed
d_analytic_realized   = g dot delta_odd
```

既存 FD 値との比を両方計算するが、元 verdict は上書きしない。

### 出力案

- `docs/evidence/stage_s_work_f_realized_direction_audit_manifest_2026_09.json`
- `docs/evidence/stage_s_work_f_realized_direction_audit_2026_09.json`

manifest には response 値を読む前に固定できる mapping、対称性、norm の判定規則を登録する。結果を見た後に
tolerance を調整しない。

### 判定

| 結果 | 次の処置 |
| --- | --- |
| prescribed と realized が登録精度内で一致 | morpher mapping は主要因ではないとして D2 へ進む。 |
| permutation、clipping、inactive movement、odd-symmetry failure を検出 | runner/morpher defect として fail。修正を別 commit に分離し、全 32 side preflight から再実行する。 |
| realized contraction で元の不一致が説明できる | 元 FD 結果は preserved diagnostic とし、修正後の新 manifest で再認定する。結果だけを再解釈して pass にしない。 |

### 停止条件

- control-point movement を authoritative artifact から復元できない場合、moved surface の頂点差から
  control-point direction を逆推定しない。
- その場合は OpenFOAM utility に read-only dump mode を追加する計画を先に登録する。

## 7. D2 — response と sensitivity semantics の監査

### 目的

adjoint derivative と primal FD が、符号・単位・正規化・面積積分を含めて同じ response を表しているか確認する。

### 監査項目

#### 7.1 Response identity

- drag direction `(1, 0, 0)`
- downforce direction `(0, 0, -1)`
- `Aref = 0.64`
- `UInf = 1`
- `rhoInf = 1`
- force coefficient の符号
- primal output から `Cd` / downforce を組み立てる式
- manifest response identity と OpenFOAM dictionary の一致

#### 7.2 Surface sensitivity convention

- `sensitivityType surface`
- `includeSurfaceArea true`
- face normal の向き
- face area を sensitivity が既に含むか、後段で再度掛けていないか
- surface sensitivity から B-spline control-point derivative への chain rule
- drag と downforce で同じ transformation path を通っているか

#### 7.3 Active-variable contraction

- derivative file の `total` column の意味
- `varID` と component の対応
- confined boundary variables が contraction に混入していないこと
- direction normalization が両 response で同じこと
- objective sign を一度だけ適用していること
- file order に依存せず `varID` で join していること

#### 7.4 独立再計算

現在の qualifier/runner とは別の最小 read-only parser で、raw derivative file と direction artifact から
全 8 analytic directional derivatives を再計算する。既存 JSON の値と bitwise または登録済み数値精度で一致するか確認する。

### 出力案

- `docs/evidence/stage_s_work_f_sensitivity_semantics_audit_manifest_2026_09.json`
- `docs/evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json`

### 判定

| 結果 | 次の処置 |
| --- | --- |
| response/scaling/sign/area defect を検出 | 一因子だけ修正し、base primal/adjoint qualification を新 lineage でやり直す。旧 evidence は保持する。 |
| semantics が一致し、D1 も pass | D3 の discretization diagnostic を登録する。 |
| 複数の defect 候補が残る | 同時に修正せず、最も上流の一因子だけを選び、新しい diagnostic を登録する。 |

## 8. D3 — bounded discretization diagnostic

### 実行条件

D1 と D2 が通過し、morpher mapping と response/sensitivity semantics で不一致を説明できない場合だけ実行する。

### 仮説

現在の一次精度 `upwind` primal discretization に対する continuous adjoint が、方向依存の離散誤差を持っている。

### 方針

これは full qualification ではなく、原因を識別する bounded factor experiment とする。
元の `upwind` 結果を上書きせず、solver scheme だけを変更した独立 case lineage を作る。

候補 factor は、既存 Stage V で使用実績のある `linearUpwind` とする。ただし、採用前に
`adjointOptimisationFoam` と primal の両方で同一の離散化契約が成立することを structural preflight する。

### 最小 case matrix

一つの中間 epsilon を事前登録し、次の 3 directions の plus/minus を使う。

| direction | 選定理由 |
| --- | --- |
| `downforce_gradient_aligned` | 両 response で pass した control |
| `random_seed_11` | downforce fail、drag pass の response-dependent case |
| `random_seed_2026` | 両 response fail、特に drag の最大不一致 case |

必要 run は、変更 scheme の base primal、drag/downforce base adjoints、3 centered pairs の 6 primals である。
epsilon は結果を見て選ばず、元 ladder の中央から manifest 作成時に一つ固定する。

### 必須 gate

- 変更 scheme の base primal residual と stationarity
- 変更 scheme の二つの adjoint convergence
- response identity と derivative schema
- 6 perturbation sides の geometry/mesh lineage
- plus/minus 両 primal の residual と stationarity
- 同じ case から drag/downforce の両方を取得
- 元 scheme と変更 scheme の差を response ごと・direction ごとに記録

### 出力案

- `docs/evidence/stage_s_work_f_discretization_diagnostic_manifest_2026_09.json`
- `docs/evidence/stage_s_work_f_discretization_diagnostic_2026_09.json`

### 判定

| 結果 | 解釈 |
| --- | --- |
| failing directions が明確に 1.0 へ近づき、control は悪化しない | discretization を主要因候補として支持。D4 用の full manifest を別途登録する。 |
| 全方向が同じ比率で移動 | response normalization または scheme 間の基準値差を再監査する。 |
| 不一致が方向依存のまま残る | continuous-adjoint formulation、surface weighting、morpher chain rule の未解決項を再検討する。 |
| base primal/adjoint gate が fail | 変更 scheme は採用せず、full campaign を開始しない。 |

この 6-run diagnostic の結果だけで derivative qualification pass や shape update を許可しない。

## 9. D4 — full derivative requalification

### 実行条件

D1〜D3 のいずれかで原因が特定され、修正後の base primal/adjoint と bounded diagnostic が通過した場合だけ実行する。

### 作業

1. 元 manifest を参照する新しい versioned manifest を登録する。
2. 4 directions、4 epsilons、両 signs の全 32 sides を再生成する。
3. geometry、clearance、mesh preflight を全件再実行する。
4. 全 32 primals を逐次実行する。
5. drag/downforce を同じ case から取得する。
6. 元と同じ 5%・sign・plateau・near-zero rule で response 別に判定する。

### 完了条件

```text
all_sides_pass=true
n_runs_pass=32
drag.passed=true
downforce.passed=true
both_responses_pass=true
```

どれか一つでも満たさない場合は、`shape_update_allowed=false` を維持する。

## 10. D5 — one-step manifest

D4 で両 response が pass した場合に限り、別 checkpoint で一歩専用 manifest を作る。

この段階でも、derivative qualification と shape update を同一 evidence slice に混ぜない。

one-step manifest には少なくとも次を登録する。

- 使用する response と direction
- control-point displacement bound
- predicted response change
- numerical/FD uncertainty
- geometry、volume、width、root/connectivity、clearance gate
- mesh、residual、stationarity gate
- 実現 response change の acceptance rule
- rollback rule

実行は最大一回とし、成功しても multi-step Stage S optimizer や Hamilton-Jacobi evolution へ自動移行しない。

## 11. 優先順位と計算資源

| 優先度 | 作業 | 新規 CFD run |
| ---: | --- | ---: |
| 1 | D0 文書整合 | 0 |
| 2 | D1 realized-direction audit | 0 |
| 3 | D2 sensitivity semantics audit | 0 |
| 4 | D3 bounded discretization diagnostic | base + adjoints + 6 primals |
| 5 | D4 full requalification | 32 primals + base/adjoint lineage |
| 6 | D5 one shape step | 条件付き |

D1 と D2 を完了するまで D3 の solver を開始しない。D3/D4 実行中は PQ2 など別の重い OpenFOAM campaign を
同じ machine で並行実行しない。

## 12. 最初の review checkpoint

最初の checkpoint は D0〜D2 に限定する。

> 文書上の pass/fail matrix を machine-readable evidence と一致させ、全 32 cases の prescribed/realized
> direction を solver-free で監査し、response・surface-area weighting・active-variable contraction を独立再計算する。
> 新しい CFD は流さず、元の verdict と threshold は変更しない。

この checkpoint で原因が特定できれば、その一因子だけを修正する。特定できない場合のみ、D3 の小規模な
discretization diagnostic を別 manifest として登録する。

## 13. 明示的な非目標

本計画だけでは、次を主張しない。

- qualified surface derivative
- Stage S shape improvement
- Stage T optimizer convergence
- Stage T から Stage S への改善
- Stage V downforce grid convergence または GCI
- target-Re、turbulent、finite-wing、moving-ground、full-vehicle の妥当性
- 一般的な cross-fidelity ranking

これらは、それぞれに登録済みの後続 gate と独立 evidence を必要とする。
