# Stage S Work F — D3 後の現状整理と次の診断計画

作成日: 2026-09-25

対象スナップショット: `feat/p0-openfoam-closed-loop` / `3f067970a867e97fce78b5c4253d62398c702aea`

状態: D0〜D3 実行後の current plan

この文書は、[`stage_s_work_f_fd_diagnosis_plan_2026_09_25.md`](stage_s_work_f_fd_diagnosis_plan_2026_09_25.md)
で定めた D0〜D3 の実行結果を受けた後続計画である。ロードマップ、状態、実行順序の正本は
[`phase_plan.md`](phase_plan.md)、問題台帳の正本は
[`problem_register_2026_09.md`](problem_register_2026_09.md) とする。本書は正本文書に従属し、
既存 manifest、evidence、方向、epsilon、5% gate を上書きしない。

## 1. 結論

Work F は、morpher、mesh、primal、adjoint を実行できる段階には到達しているが、surface derivative は
まだ qualification を通過していない。

D0〜D2 により、次の単純な原因は否定された。

- control-point `varID` の並び違い
- prescribed movement と realized movement の不一致
- plus/minus の非対称性
- boundary control-point movement
- response direction、符号、`Aref`、`rhoInf`、`UInf` の不一致
- derivative file と direction vector の join error
- row-order 依存

D3 では primal convection scheme を `upwind` から `linearUpwind` に変えたところ、downforce の二つの
失敗方向は 5% 内へ改善した。一方で drag の既存 pass control が fail へ悪化し、drag の最大不一致も残った。
さらに baseline Cd が `2.5234 -> 2.2333` と約 11.5% 変化した。したがって discretization は寄与因子では
あるが、単独原因とは認定できない。

現在の停止状態は次のとおり。

```text
derivative_qualified=false
supports_discretization_cause=false
shape_update_allowed=false
```

次に行うべきことは full 32-case requalification ではない。まず、OpenFOAM が出力した design-variable
derivative を構成項ごとに分解し、B-spline movement に対する face geometry Jacobian を solver-free で
直接検証する。その後、`includeSurfaceArea` と `includeMeshMovement` を一因子ずつ adjoint-only で ablation し、
原因候補を未使用の holdout directions で検証する。

## 2. リポジトリと実行状態

| 項目 | 確認状態 |
| --- | --- |
| branch | `feat/p0-openfoam-closed-loop` |
| HEAD | `3f06797` — `Run the bounded discretization diagnostic and record the mixed result` |
| upstream | `origin/feat/p0-openfoam-closed-loop` と同期 |
| working tree | この計画作成前は clean |
| 稼働中の CFD/test process | 観測なし |
| OpenFOAM image | `opencfd/openfoam-default:2512` |
| image ID | `sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319` |

### 2.1 文書の現在状態

`phase_plan.md` の詳細 addendum と `opencode_handoff_2026_09.md` は D3 の mixed verdict を記録している。
一方、次の古い表現が残っている。

- `phase_plan.md` 上部 Stage S summary の末尾は D0〜D2 を current work としており、D3 完了を反映していない。
- `phase_plan.md` の旧 Slice C/D paragraph には「random directions が両 response で 5% 超過」と読める文が残るが、
  drag `random_seed_11` は 3.76% で pass である。
- `problem_register_2026_09.md` の「次の一手」は campaign 開始前の 2026-09-24 snapshot のままである。

これらは machine-readable verdict を変えないが、D4.0 で正本と issue ledger を最新状態へ整合させる。

## 3. 現在の evidence

| 段階 | artifact | SHA-256 | verdict |
| --- | --- | --- | --- |
| original 32-case FD | [`evidence/stage_s_work_f_surface_fd_result_2026_09.json`](evidence/stage_s_work_f_surface_fd_result_2026_09.json) | `048a2f9307d36a645e76dee7fac26c6325568888cfaa28063cf5685a4acbc9ee` | complete qualification fail |
| D1 realized direction | [`evidence/stage_s_work_f_realized_direction_audit_2026_09.json`](evidence/stage_s_work_f_realized_direction_audit_2026_09.json) | `79da4532b9be2d548a725b5a3cbe7d0dc226d997b831b79638b387efe6585193` | pass |
| D2 sensitivity semantics | [`evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json`](evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json) | `c840bca86934716fbc6cef1e3520971c365975895fe6bfcfa97a5b0df98d952a` | pass |
| D3 discretization diagnostic | [`evidence/stage_s_work_f_discretization_diagnostic_2026_09.json`](evidence/stage_s_work_f_discretization_diagnostic_2026_09.json) | `f3a85709817aa67d4fee8123d84d524784b403fd944702211c1677af878e67b6` | mixed; sole-cause hypothesis rejected |

## 4. D0〜D2 で確認されたこと

### 4.1 D1 — realized-direction audit

- 32/32 sides が prescribed control-point movement を再現した。
- side の最大 movement error は `9.7e-9 m` 以下。
- 16/16 centered pairs で cosine similarity は実質 1。
- odd-symmetry error、even component、movement difference はすべて登録 tolerance 内。
- boundary control points は固定。
- prescribed direction と realized direction で計算した analytic contraction は約 `4e-6` absolute で一致。
- solver は実行していない。

したがって、現在の FD 不一致を control-point ordering、clipping、permutation、plus/minus asymmetry で説明する
ことはできない。

### 4.2 D2 — sensitivity semantics audit

- drag objective direction `(1, 0, 0)` は primal/adjoint/manifest で一致。
- downforce objective direction `(0, 0, -1)` は primal/adjoint/manifest で一致。
- `Aref=0.64`、`rhoInf=1`、`UInf=1` は一致。
- downforce は `-Cl` として一貫している。
- boundary variables は contraction から除外されている。
- raw derivative file は `varID` で join されている。
- 独立 parser が全 8 analytic directional derivatives を相対 `1e-9` より十分小さい差で再現した。
- solver は実行していない。

これは記録された response identity と contraction の一貫性を支持する。一方、OpenFOAM 内部の
surface-area treatment や geometric chain rule が連続 adjoint と discrete primal の組合せに対して正しいことまで
独立に証明したものではない。

## 5. D3 — discretization diagnostic の結果

D3 は一つの中間 epsilon `5e-4 m`、三つの directions、両 signs を使い、変更因子を
`div(phi,U) bounded Gauss upwind` から `bounded Gauss linearUpwind grad(U)` だけに限定した。

base primal、drag/downforce adjoint、6 perturbation primals はすべて gate を通過した。

### 5.1 Baseline response の変化

| response | upwind | linearUpwind | 相対変化 |
| --- | ---: | ---: | ---: |
| Cd | 2.5234 | 2.2333 | 約 -11.5% |
| downforce | 1.6908 | 1.6659 | 約 -1.5% |

この変化量は、scheme を derivative agreement のための小さな補正として扱えないことを示す。

### 5.2 Directional derivative ratio

| response / direction | upwind | linearUpwind | 変化 |
| --- | ---: | ---: | --- |
| downforce / `downforce_gradient_aligned` | 1.0409 | 1.0418 | pass を維持 |
| downforce / `random_seed_11` | 1.0857 | 1.0432 | fail -> pass |
| downforce / `random_seed_2026` | 0.8796 | 1.0336 | fail -> pass |
| drag / `downforce_gradient_aligned` | 1.0266 | 1.0070 | pass を維持・改善 |
| drag / `random_seed_11` | 1.0376 | 0.8521 | pass -> fail |
| drag / `random_seed_2026` | 1.4592 | 1.2608 | 改善したが fail |

事前登録した「失敗方向が 1 に近づき、control が悪化しない」という条件を満たさない。

```text
n_improved_across_the_gate=2
n_worsened_controls=1
supports_discretization_cause=false
```

## 6. 工学的な解釈

### 6.1 現在強く支持されること

- 不一致は epsilon に対して安定しているため、単純な truncation/noise 問題ではない。
- movement mapping は正しい。
- 記録された response/sign/normalization と contraction は一貫している。
- convection discretization は derivative ratio に大きく影響する。
- しかし scheme 変更だけでは全 response/direction を同時に説明できない。
- gradient-aligned direction の pass だけでは gradient vector 全体の方向精度を保証しない。

### 6.2 Derivative component の観測

現在の `volumetricBSplines` derivative file では、`total` は実質的に次の二項から構成される。

```text
total = dxdbSurf + dSdb
```

現在の runs では `dxdbVol`、`dndb`、`dxdbDirect` などは directional contraction 上でゼロである。

特に random directions では二項が相殺する場合があり、各項の小さな誤差が total の大きな相対誤差になる。

| response / direction | `dxdbSurf` | `dSdb` | analytic total | FD |
| --- | ---: | ---: | ---: | ---: |
| downforce / seed 11 | +0.02465 | -0.17737 | -0.15272 | -0.16581 |
| downforce / seed 2026 | -0.24243 | -0.14158 | -0.38401 | -0.33778 |
| drag / seed 11 | -0.02818 | -0.13972 | -0.16790 | -0.17423 |
| drag / seed 2026 | -0.20195 | +0.06770 | -0.13425 | -0.19592 |

この表は read-only inspection による engineering observation であり、まだ登録済み evidence ではない。
特に drag seed 2026 では二項が逆符号であり、component-level error を total の一つの倍率として補正してはならない。

### 6.3 v2512 source から確認できること

対象 image の OpenFOAM v2512 source では、現在の `sensitivityType surface` は E-SI shape sensitivity を使う。

- `includeMeshMovement` の default は `true`。
- `includeSurfaceArea` の default は `false`。
- 現在の case は `includeSurfaceArea true` を明示している。
- `shapeDesignVariables` は `dxdbSurf`、`dSdb`、`dndb`、`dxdbDirect` などを別々に組み立ててから合算する。

したがって、次の診断は total derivative だけでなく、surface movement term と surface-area term を分けて扱う。

## 7. 変更しないもの

原因診断中は次を変更しない。

- 元の 4 directions とその hash
- 元の epsilon ladder
- 5% relative rule
- sign agreement rule
- plateau rule
- near-zero rule
- original upwind verdict
- D3 linearUpwind verdict
- Work F baseline geometry
- response identities
- 既存 evidence と hash

観測済み response に合わせて per-response scale、方向別 correction、epsilon、tolerance を調整しない。

## 8. 次の実行順序

```text
D4.0 diagnostic registration
  -> D4.1 derivative-component audit（solver-free）
  -> D4.2 geometry-Jacobian audit（solver-free）
    -> geometry chain rule が fail: 一因子修正 -> side preflight から再実行
    -> geometry chain rule が pass: D4.3 adjoint-option ablation
      -> D4.4 factor judgment
        -> candidate factor あり: D5 independent holdout
        -> candidate factor なし: fail-closed / architecture decision
          -> holdout pass 時のみ D6 full requalification
            -> 両 response pass 時のみ D7 one-step manifest
```

## 9. D4.0 — diagnostic registration

### 目的

D4 の計算を始める前に、入力、比較対象、factor、停止条件を固定する。

### 文書整合

1. `phase_plan.md` 上部 summary を D3 mixed verdict と `shape_update_allowed=false` まで更新する。
2. 旧 Slice C/D paragraph の drag `random_seed_11` 表現を machine-readable verdict と一致させる。
3. `problem_register_2026_09.md` の current questions と next action を D3 後へ更新する。
4. 過去の manifest、evidence、raw logs、hash は変更しない。

### Manifest に拘束するもの

- original upwind base/adjoint/FD evidence の path と SHA-256
- D1/D2/D3 evidence の path と SHA-256
- four direction hashes
- original derivative file hashes
- linearUpwind derivative file hashes
- OpenFOAM image ID
- 使用する v2512 source files とその SHA-256
- component names と合算式
- option ablation の順序
- pass/fail/control-worsening rule
- holdout seed の生成規則

### 禁止事項

- D4 の結果を見て ablation factor を追加する。
- 複数 option を同時に変更する。
- 同じ結果に合うように component scale を fit して production correction にする。
- D4 を derivative qualification と呼ぶ。

### 出力案

- `docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json`

## 10. D4.1 — derivative-component audit

### 目的

既存 derivative file と既存 FD rows だけを使い、方向ごとの不一致がどの component combination で増幅されるかを
記録する。solver は実行しない。

### 計算

各 scheme、response、direction について次を出力する。

```text
d_total
d_dxdbVol
d_dxdbSurf
d_dSdb
d_dndb
d_dxdbDirect
d_dVdb
d_distance
d_options
d_dvdb
closure = d_total - sum(d_components)
cancellation_index = sum(abs(d_components)) / max(abs(d_total), floor)
fd_residual = d_fd - d_total
```

original upwind は全 4 directions・全 epsilon、linearUpwind は登録済み 3 directions・`5e-4 m` を対象にする。

### 判定

- `closure` が file precision 内であることを必須とする。
- cancellation index が大きい方向と FD error の関係を記録する。
- 一項の削除または一つの共通 scalar だけで全方向を説明できるかを診断する。
- post-hoc fit は説明用に限定し、修正値や qualification に使わない。

### 出力案

- `docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json`

## 11. D4.2 — B-spline geometry-Jacobian audit

### 目的

D1 は control-point movement が正しいことを確認したが、control-point movement から face center、face area vector、
normal への analytic chain rule は独立検証していない。ここを flow solver なしで確認する。

### 比較対象

既存 plus/minus moved meshes から、各 design face について centered difference を計算する。

```text
dCf/db = (Cf_plus - Cf_minus) / (2 * epsilon)
dSf/db = (Sf_plus - Sf_minus) / (2 * epsilon)
dn/db  = (n_plus  - n_minus)  / (2 * epsilon)
```

OpenFOAM の B-spline parameterization が持つ analytic `dxdbFace`、`dSdb`、`dndb` を同じ registered direction に
contract し、face-by-face および patch-integrated で比較する。

### 実装方針

- 既存 `moveControlPoints` の movement path は変更しない。
- 必要なら read-only の geometry-derivative dump utility を別名で追加する。
- dump utility は mesh を更新せず、analytic geometry derivatives と source/image hash だけを出力する。
- moved surface の頂点差から control-point derivative を逆推定しない。
- face ordering と patch identity を hash で拘束する。

### Gate

- plus/minus face topology が一致する。
- face ordering が一致する。
- epsilon plateau が存在する。
- analytic/FD の sign、relative/absolute error を geometry quantity ごとに事前登録した tolerance で判定する。
- design patch 以外の derivative はゼロである。

### 分岐

| 結果 | 処置 |
| --- | --- |
| geometry Jacobian fail | morpher/parameterization chain-rule defect として停止し、一因子修正後に side preflight から再実行する。 |
| geometry Jacobian pass | geometry mapping を主要因から外し、D4.3 へ進む。 |
| analytic dump を authoritative に取得できない | 推測せず停止し、dump 経路だけを先に実装・review する。 |

### 出力案

- `docs/evidence/stage_s_work_f_geometry_jacobian_manifest_2026_09.json`
- `docs/evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json`

## 12. D4.3 — adjoint-option ablation

### 実行条件

D4.1 の component closure と D4.2 の geometry Jacobian が pass した場合だけ実行する。

### 原則

- original `upwind` primal state と既存 FD rows を固定する。
- option を一つだけ変更した独立 adjoint lineage を作る。
- base primal response と field hash が original lineage と一致することを確認する。
- 新しい perturbation primal は流さない。
- ablation は原因診断であり、production setting の採用ではない。

### D4.3a — `includeSurfaceArea`

変更因子:

```text
baseline:  includeSurfaceArea true
treatment: includeSurfaceArea false
```

固定条件:

```text
includeMeshMovement true
sensitivityType surface
smoothSensitivities false
shapeType volumetricBSplines
```

drag/downforce の二つの adjoint を実行し、4 original directions 全部へ contract する。既存 upwind FD rows と比較し、
次を記録する。

- total と全 component
- 元の failing rows が 1 に近づくか
- 元の passing controls が 5% 外へ悪化しないか
- response 間で一貫した説明になるか
- cancellation pattern がどう変わるか

`includeSurfaceArea false` が良好でも、それだけで採用しない。現在の結果を見て選んだ factor なので、D5 holdout が必要である。

### D4.3b — `includeMeshMovement`

D4.3a が sole-cause 条件を満たさない場合だけ実行する。

変更因子:

```text
baseline:  includeMeshMovement true
treatment: includeMeshMovement false
```

これは mesh-movement term の寄与を測る ablation であり、`false` を production setting として採用する試験ではない。
比が改善した場合は「mesh-movement sensitivity term に不整合がある」という仮説を支持するに留める。

### Sole-cause support rule

候補 factor は次をすべて満たした場合だけ D5 へ進める。

- original failing rows がすべて 5% 内へ移動する。
- original passing rows が一つも 5% 外へ悪化しない。
- 全方向の sign agreement を保つ。
- response identity と derivative schema を保つ。
- base primal field/response lineage が変わらない。
- 一方向だけの near-zero/cancellation artifact でない。

### 出力案

- `docs/evidence/stage_s_work_f_adjoint_option_diagnostic_manifest_2026_09.json`
- `docs/evidence/stage_s_work_f_adjoint_option_diagnostic_2026_09.json`

## 13. D4.4 — factor judgment

| D4 結果 | 判断 |
| --- | --- |
| geometry Jacobian defect | その defect だけを修正し、base derivative qualification と side preflight からやり直す。 |
| 一つの adjoint option が sole-cause rule を満たす | candidate factor として D5 holdout へ進む。 |
| 複数 factor が部分改善だけを示す | 組合せ探索を開始せず、continuous-adjoint formulation の限界として fail-closed で設計判断へ戻す。 |
| どの factor も説明しない | OpenFOAM continuous-adjoint route はこの Work F profile では未資格とし、D6/D7 へ進まない。 |

複数 option の組合せを既存 4 directions に合わせ込む探索は行わない。

## 14. D5 — independent holdout directions

### 必要性

D4 の factor は original FD 結果を見た後に選ばれる。したがって、同じ directions だけで再評価しても独立検証にならない。

### 登録

- 新しい random directions を最低 2 本登録する。
- seed は結果に依存せず、manifest hash から決定論的に導出する。
- active 648-variable space 上で unit infinity norm に正規化する。
- 元の gradient-aligned directions のうち一つを control として残す。
- epsilon は元 ladder の中央値から一つを事前登録する。
- plus/minus の両 sides を使う。

最小 discriminant は 3 directions x 2 signs = 6 primals とする。両 response を同じ runs から読む。

### Pass 条件

- geometry/mesh/residual/stationarity gate を全 side が通過する。
- drag/downforce の sign が一致する。
- 二つの新 random directions が両 response で 5% 内。
- gradient-aligned control が 5% 内を維持する。
- pre-registered near-zero rule を守る。

一つでも fail/unresolved なら D6 へ進まない。

## 15. D6 — full independent requalification

D5 が pass した場合だけ、新しい versioned manifest を登録する。

方向集合は、original 4 directions に最低 2 本の independent holdout directions を加える。元の 4 epsilons、両 signs、
元の 5%・sign・plateau・near-zero rule を使う。最小構成は 6 directions x 4 epsilons x 2 signs = 48 primals となる。

### 完了条件

```text
all_sides_pass=true
all_primals_qualified=true
drag.passed=true
downforce.passed=true
original_directions_pass=true
holdout_directions_pass=true
both_responses_pass=true
```

full requalification の結果を見る前に、shape-step rule を変更しない。

## 16. D7 — one-step manifest

D6 が完全 pass した場合だけ、別 checkpoint で一歩専用 manifest を登録する。

- control-point displacement bound
- predicted drag/downforce change
- FD/adjoint uncertainty
- volume、minimum width、root/connectivity、clearance
- mesh quality
- residual と force stationarity
- realized response change
- rollback rule

を事前登録する。shape update は最大一回とし、成功しても multi-step Stage S optimizer へ自動移行しない。

## 17. 優先順位と計算量

| 優先度 | 作業 | 新しい flow solver run |
| ---: | --- | ---: |
| 1 | D4.0 manifest | 0 |
| 2 | D4.1 component audit | 0 |
| 3 | D4.2 geometry-Jacobian audit | 0 |
| 4 | D4.3a surface-area ablation | base lineage check + 2 adjoints |
| 5 | D4.3b mesh-movement ablation | 条件付きで 2 adjoints |
| 6 | D5 independent holdout | 6 primals + candidate adjoints |
| 7 | D6 full requalification | 48 primals + base/adjoint lineage |
| 8 | D7 one shape step | 条件付き |

D4.0〜D4.2 を最初の review checkpoint とする。この checkpoint では新しい primal/adjoint を流さない。

## 18. 最初の review checkpoint

> original/linearUpwind derivative file を構成項別に分解し、全方向で合算 closure と cancellation を記録する。
> 次に、既存 plus/minus meshes と OpenFOAM の analytic B-spline geometry derivative を比較し、face center、area vector、
> normal の chain rule を solver-free で検証する。ここが通るまで adjoint option を変更しない。

この checkpoint の目的は、CFD を追加実行する前に、残る問題が geometry chain rule なのか、continuous-adjoint
surface term なのかを分離することである。

## 19. 停止条件

- geometry Jacobian の authoritative dump が得られない場合は推測しない。
- 一つの option ablation が一部方向だけを改善しても採用しない。
- passing control を悪化させる factor を full campaign へ進めない。
- response ごとの fitted scale で 5% gate を通さない。
- original data を使って選んだ factor を holdout なしで資格化しない。
- continuous adjoint を合理的な一因子診断で説明できなければ、shape update を保留したまま architecture decision へ戻る。

## 20. 非目標

本計画だけでは次を主張しない。

- qualified surface derivative
- Stage S shape improvement
- Stage T convergence
- Stage T から Stage S への改善
- Stage V downforce grid convergence または GCI
- target-Re、turbulent、finite-wing、moving-ground、full-vehicle の妥当性
- optimizer-generated shapes の一般的な cross-fidelity ranking

これらには別の登録済み gate と独立 evidence が必要である。
