# ダウンフォース最適化 — PQ0/PQ1 実装後の統合・資格化計画（2026-09-22）

Status: **adopted architecture and qualification plan**

Authority: [`phase_plan.md`](phase_plan.md) がロードマップ、状態、実行順の唯一の
authority である。本書は、その順序を実装、数値実験、合否判定へ展開する詳細計画である。
問題状態は [`problem_register_2026_09.md`](problem_register_2026_09.md)、schema と artifact
semantics は [`problem_contract_v2.md`](problem_contract_v2.md) と
[`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) に従う。

> **2026-09-22 current-state note:** PQ0.1、PQ0.2、PQ1.1、最初のPQ3 closed loop、
> PQ3.1--PQ3.3は実行済みである。本書の未実行形で書かれた各節は、その時点のentry/exit
> criteriaを保存する。PQ3.3後の現在地、field-semantic再判定、projected-volume continuation、
> PQ4.1、最初のStage S stepの実行順は
> [`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md)
> に従う。`phase_plan.md`が最終authorityである。

Baseline: branch `feat/p0-openfoam-closed-loop`, commit
`1d4046341dfb599582a9976061a07689d32c5927`。

本書は 2026-09-21 版を同じファイルで改訂した。古い計画書を増やさず、PQ0/PQ1 の実装結果と
実装後監査を一つの active plan に反映する。

---

## 1. 結論

採用する構造は変えない。

```text
ProblemSpec
  -> Stage T: density / Brinkman による topology 探索
  -> Stage S: 抽出境界の sharp-interface 改善
  -> Stage V: body-fitted OpenFOAM による独立検証
```

現在の実装は、compiler、DesignTransform、非線形受理、checkpoint、有限差分 campaign、
抽出 sweep、独立検証 algebra まで前進した。PQ1 では source grid の細分化により
FD/adjoint 比が粗格子の `1.22 / 1.38 / 1.57` から `1.15 / 1.11 / 1.14` へ移動し、
30 倍の epsilon 範囲で安定した。したがって continuous adjoint の符号情報を限定研究に使う
根拠は得たが、5% の production gate は通っていない。

実装後監査では、PQ3 を始める前に閉じるべき統合ギャップも判明した。

1. `CompiledProblem.volume_constraint` は one-step optimizer では使われるが、
   `run_stage_t_loop` の nonlinear path では value/gradient に連結されていない。
2. `make_oracle_from_compiled()` の value/gradient API は分かれているが、両方が同じ
   `primitive_evaluator` を再実行し、accepted trial の primal artifact を再利用しない。
3. trial は primal-only であるべきなのに、現在は `adjoint_converged` を必須判定し、欠落時は
   `True` を既定値にする。parent adjoint と trial primal の意味が混ざっている。
4. Path B が要求する「各提案方向の centered primal FD bracket」は nonlinear loop に未接続である。
5. 現在の実 P0 fixture は `drag - downforce` の無制約問題であり、次に解くべき
   「downforce 最大化 + 投影後体積制約」を表していない。
6. `DesignTransformState.rho_projected` は射影出力、fixed-grid artifact の
   `rho_projected` は RAMP 後の OpenFOAM `beta` であり、同名が異なる状態を表す。

従って次の順序を採用する。

```text
PQ0.1  nonlinear path の統合修復
   -> PQ0.2  実 OpenFOAM oracle の最小 smoke
   -> PQ1.1  gradient の残る grid/mesh 資格化
   -> PQ3    Path B 限定 closed loop（1–3 accepted steps）
   -> PQ4    T-to-S handoff と一つの sharp-interface step
   -> PQ5    baseline/T/S の独立三格子検証
   -> PQ6    production optimizer と target-physics ladder

PQ2 Stage V domain/boundary factor は PQ0.1–PQ1.1 と並行可能
```

長時間最適化、robust 三場、MMA/GCMMA 導入、front-wing への拡張は、上の gate を飛ばして
始めない。

---

## 2. 現在地と証拠範囲

### 2.1 実装済み

| 項目 | 現在の実装 | 証拠として言える範囲 |
| --- | --- | --- |
| Problem compiler | objective/response constraint を標準 minimization と `g <= 0` へ変換し、compile-time volume budget を持てる | contract/capability |
| DesignTransform | filter → tanh projection → RAMP の forward と pullback | unit-level numerical/capability |
| Nonlinear controller | merit/trust、trial primal、rollback、checkpoint/resume | synthetic integration capability |
| PQ0 audit | 実 P0 artifact で `declared_equals_solved=true` | 当該 unconstrained `drag - downforce` fixture の contract evidence |
| PQ1 campaign | base adjoint と perturbation primal を役割分離し、manifest の epsilon/direction を fail-closed に消費 | campaign semantics |
| Refined source grid | 64x32x32、tight residual で比 `1.1504 / 1.1134 / 1.1441`、plateau 幅 `0.00043 / 0.00003 / 0.00450` | 当該 frozen state/response/configuration の数値 evidence |
| Stage V scheme | `linearUpwind` で drag finest drift 0.364% | 当該候補の drag numerical evidence |
| Extraction | threshold sweep、component/root/volume diagnostics | capability。Stage S-ready candidate は未生成 |
| Robust fields | nominal/eroded/dilated prototype と production exclusion | prototype capability |

### 2.2 まだ言えないこと

- downforce gradient が production 精度であること。
- source-grid convergence または grid independence。比較した source grid は二段階だけである。
- 現在の nonlinear loop が物理体積制約を解いていること。
- 実 OpenFOAM evaluator で primal-only trial と parent adjoint が重複なく動くこと。
- optimizer-generated candidate の Stage T → Stage V 改善順位が保存されること。
- Stage V downforce が grid-independent であること。
- Stage S の形状勾配、再初期化、曲率制御が資格化されたこと。
- full vehicle、高 Reynolds 数、moving ground、multipoint 条件へ一般化できること。

### 2.3 PQ1 の正しい解釈

細格子結果は **refined-grid epsilon-stable** である。二つの source-grid level しかないため、
`grid-consistent` や `converged` とは呼ばない。全方向が 1 に近づいたことから source-grid
離散化が mismatch の主要寄与である可能性は高いが、唯一原因とは確定しない。

Path B は gradient magnitude を経験係数で補正する経路ではない。使えるのは、符号の安定した
adjoint を proposal 生成に使い、各 proposal を primal FD と実 trial primal で確認する限定経路
だけである。

---

## 3. 解く問題を固定する

最初の実 closed loop は、次の reduced problem に固定する。

```text
design variable: rho in [0, 1]

rho
  -> mask-aware filter
  -> tanh projection = rho_projection
  -> RAMP interpolation = beta_solver
  -> OpenFOAM Brinkman field

minimize  J(rho) = -C_DF(rho)

subject to
  g_V(rho) = V(rho_projection) - V_max <= 0
  fixed/forbidden/root masks
  declared geometry gates
  move/trust bounds
```

`C_DF` は global `-z` 方向の正の downforce coefficient とし、最大化を標準 minimization
`J=-C_DF` へ変換する。体積は RAMP 後の抵抗係数ではなく、射影後の幾何占有率に対して定義する。

drag は最初の loop では report-only response とする。drag を設計要件にする場合は、後続 manifest
で `C_D <= C_D,max` の制約として追加する。無次元化・scale・weight を登録しない
`drag - downforce` の単純和は使わない。

最初の reduced problem で connectivity を無効にする場合、その候補は connectivity-qualified と
呼ばない。root、minimum width、connectivity を PQ3 の geometry gate に要求するなら、fixture
と初期 feasible seed に明示し、未実装の微分制約を暗黙に解いたことにしない。

---

## 4. PQ0.1 — nonlinear production path の統合修復

### 4.1 目的

実装済み部品を一つの意味的に正しい nonlinear path にする。新しい optimizer や抽象層は作らず、
既存の `CompiledProblem`、`DesignTransform`、`run_stage_t_loop` を接続する。

### 4.2 Volume constraint を nonlinear loop へ接続

`make_oracle_from_compiled()` は solver primitive constraints に加え、
`compiled.volume_constraint` を同じ `OracleResult` へ追加する。

- value: `V(rho_projection) - V_max`
- gradient: `DesignTransform.pullback_from_projected(...)`
- response constraint と volume constraint の ID 重複を fail-closed に拒否
- parent/trial/checkpoint/history の全てで同じ constraint ID と定義 hash を使用
- trial は CFD 前に安価な volume/box/mask gate を評価し、明白な infeasible proposal を拒否可能にする

現在の test にある「downforce response を `volume_budget` と命名した制約」は廃止し、実際の
projection occupancy を検査する。

### 4.3 Primal と adjoint の実行契約を分離

oracle は次の二つを別 callback として持つ。

```text
evaluate_values(rho)
  -> primal artifact + response values + primal/geometry status

evaluate_gradients(rho, accepted_primal_artifact)
  -> accepted primal を入力に adjoint だけを実行
  -> response gradients + adjoint status
```

`evaluate_gradients` は渡された primal artifact の candidate hash、state hash、final time、
response hash、solver profile を照合する。同じ `rho` から primal を黙って再実行しない。

accepted trial は次 iteration の parent primal artifact として再利用する。必要な solver 実行は
「初期 parent primal 1回、各 accepted parent の adjoint 1回、各 trial の primal 1回」を基本とする。
API 呼出し数だけでなく、実 evaluator の primal/adjoint invocation ID で重複を検査する。

### 4.4 Parent と trial の収束状態を分ける

trial primal に adjoint 状態を要求しない。

```text
trial.adjoint_status = not_applicable
parent.adjoint_status = converged | failed
```

parent gradient は adjoint status、最終残差、required response、最終 time、field hash のいずれかが
欠ければ fail-closed に停止する。欠落を `True` とみなさない。trial acceptance は primal、geometry、
constraints、実 objective、trust/merit だけで判定する。

### 4.5 Path B centered FD bracket を実装

proposal `d` ごとに `d_hat = d / ||d||_inf` を作り、parent で次を評価する。

```text
D_adj = grad(J)^T d_hat
D_FD  = [J(rho + epsilon d_hat) - J(rho - epsilon d_hat)] / (2 epsilon)
```

- `rho ± epsilon d_hat` が bounds/masks を対称に満たす epsilon を manifest から選ぶ。
- clip によって方向を変えない。対称点が作れない場合は move を縮め、作れなければ proposal を拒否する。
- 両側 primal は同じ solver/mesh/residual profile を使う。
- `|J+ - J-|` が登録 noise floor 以下なら判定不能として step を進めない。
- minimization convention で `D_adj < 0`、`D_FD < 0` かつ符号が一致する場合だけ
  trial primal へ進む。
- magnitude 補正係数は掛けない。
- FD bracket artifact を proposal、parent、epsilon、両側 run hash とともに保存する。

### 4.6 状態名を一意にする

内部 semantic name を次へ統一する。

| 状態 | 意味 |
| --- | --- |
| `rho_design` | optimizer design variable |
| `rho_filtered` | filter output |
| `rho_projection` | tanh projection output。volume と geometry occupancy の基準 |
| `beta_solver` | RAMP 後に OpenFOAM が使う Brinkman interpolation field |

既存 artifact schema を直ちに破壊しない。schema version を上げるまでは旧 key に semantic metadata
を必須化し、reader 側で一度だけ変換する。新しい同義 key の二重保存は避ける。

### 4.7 PQ0.1 exit gate

- nonlinear loop の objective、response constraints、volume constraint が compiler の
  `solved_set` と完全一致する。
- synthetic evaluator で volume infeasible proposal が拒否され、volume gradient の centered FD が通る。
- trial は adjoint なしで評価でき、parent は adjoint 欠落で必ず停止する。
- accepted trial の primal artifact が次 parent で再利用され、重複 primal がない。
- Path B bracket の sign match、sign mismatch、noise-floor、非対称 bounds の回帰 test が通る。
- checkpoint resume が problem/transform/oracle/bracket profile の変更を拒否する。
- projection output と solver beta の lineage が machine-readable に区別される。
- `declared_equals_solved=true` audit が「downforce 最大化 + volume inequality」の新 fixture で成立する。

### 4.8 停止条件

- volume constraint を `ProblemSpec` と transform declaration の二重所有にして一致を推測する必要がある。
- primal artifact を adjoint adapter が一意に再利用できない。
- centered FD の solver noise floor を測れない。
- reduced problem に feasible initial state が存在しない。

この場合は schema または adapter を先に直し、optimizer tuning へ進まない。

---

## 5. PQ0.2 — 実 OpenFOAM oracle の最小 smoke

PQ0.1 の synthetic tests の次に、長時間 campaign の前に一つの実 solver trace を作る。

### 実行列

1. feasible parent primal
2. 同じ parent artifact を消費する parent adjoint
3. Path B bracket の `rho + epsilon d_hat` primal
4. Path B bracket の `rho - epsilon d_hat` primal
5. 一つの trial primal
6. accept または rollback
7. checkpoint から resume し、受理済み trial primal を parent として再利用

### 合格条件

- primal/adjoint の invocation ID と input/output hash が一意に追跡できる。
- parent primal の暗黙再実行がない。
- trial に adjoint を走らせない。
- volume、objective、geometry gate が同じ candidate hash を参照する。
- interruption 後の resume が同じ decision/history を再現する。
- sign、units、`dJ/drho=-dC_DF/drho` が artifact に明記される。

これは closed-loop 改善の証明ではなく、production execution path の capability evidence である。

---

## 6. PQ1.1 — gradient oracle の残る資格化

### 6.1 現判定

PQ1 は refined source grid 上の **Path B bounded exception** である。Path A ではない。

### 6.2 次の順序

1. base mesh gate を測定し、現在の `not_measured` を解消する。
2. canonical grid refinement を専用 immutable manifest として登録する。
3. frozen design、response、domain、solver、direction、epsilon、residual を固定し、canonical
   parameterization だけを変更する。
4. source grid を変えない比較で、canonical parameterization が比へ与える効果を判定する。
5. source-grid dependence が主要なままなら、結果を見る前に第三 source-grid level を登録し、
   三段階で収束傾向を調べる。

二段階の grid 比から Richardson extrapolation、観測次数、GCI を作らない。非単調なら convergence
claim を止め、level ごとの bounded evidence として残す。

### 6.3 判定

| 判定 | 条件 | 次 |
| --- | --- | --- |
| Path A | 全登録方向で符号一致、epsilon plateau、relative error <= 5%、mesh/base gates measured pass | 通常の限定 PQ3 |
| Path B | 5% は未達だが符号と plateau が安定し、各 proposal の centered FD bracket を実行できる | 1–3 accepted steps の research PQ3 |
| No-Go | 符号反転、plateau 不成立、mesh/base gate fail、または FD bracket が proposal を支持しない | loop 停止。solver-side adjoint formulation を修正 |

Path B のまま PQ3 へ進む場合、現比 `1.11–1.15` を補正値として使わない。異なる state、方向、
constraint gradient へ外挿しない。

---

## 7. PQ2 — Stage V downforce reference の数値資格化

PQ2 は PQ0.1、PQ0.2、PQ1.1 と独立に進められる。登録済み
`evidence/stage_v_domain_boundary_factor_manifest_2026_09.json` を変更せず実行する。

### 実行

- fixed candidate、matched-Re laminar、`linearUpwind`、V2 を固定する。
- far-field domain extension を 1 run。
- far-field boundary treatment variant を 1 run。
- mesh/stationarity gate に失敗した run も除外せず failed と記録する。
- この campaign で V3 や複数因子同時変更を追加しない。

### 判定

- V2 downforce 変化が 0.005 を超える因子がある場合、その因子を固定した三格子 family を新しく
  事前登録し、V2→V3 drift を再測定する。
- どちらも 0.005 以下なら、残る 0.010374 の非単調 drift を当該候補の measured numerical band
  として扱う。grid-independent や GCI とは呼ばない。
- drag は 2% relative、downforce は 0.005 absolute で別々に判定する。

PQ2 が未完でも Stage T execution capability を調べる PQ3 は開始できる。ただし、PQ2 が閉じるまで
Stage V を truth value とした改善量や target-physics claim は作らない。

---

## 8. PQ3 — 最初の限定 OpenFOAM closed loop

### 8.1 Entry gate

- PQ0.1 の全 exit gate が pass。
- PQ0.2 の実 oracle smoke が pass。
- PQ1.1 が Path A、または制約を明記した Path B manifest が確定。
- reduced problem、`V_max`、filter/projection/RAMP、初期 feasible seed、move bounds、noise floor、
  accepted-step 上限を事前登録。
- geometry/topology policy のうち、実際に強制する項目と report-only 項目を分離。

### 8.2 Campaign

- objective: `minimize -C_DF`
- constraint: projected volume inequality
- accepted steps: 最大 3
- trial: primal-only
- parent: accepted primal reuse + adjoint-only
- Path B: 全 proposal に centered primal FD bracket
- acceptance: 実 trial primal、volume、geometry、merit/trust、noise margin
- rejection: rollback し、continuation/accepted counter を進めない
- restart: 少なくとも一度、意図的中断から再開する

初回 campaign では robust three-field、connectivity finite-difference production constraint、
actual MMA/GCMMA、mesh adaptation を入れない。これらが必要な問題設定なら PQ3 の結果を
`capability only` とし、後続 gate を定義してから追加する。

### 8.3 合格条件

- 1–3 steps の範囲で少なくとも一つの accepted step がある。
- 各 accepted step は実 primal で `C_DF` を noise margin より大きく改善する。
- volume と強制 geometry gates を全 accepted state が満たす。
- accepted/rejected trial、FD bracket、rollback、checkpoint が immutable lineage を持つ。
- rerun/resume で同じ accepted history と final hash を再現する。
- 最終 candidate に extraction preregistration を結び付ける。

### 8.4 停止条件

- Path B FD bracket が adjoint proposal の descent sign を支持しない。
- volume を満たす feasible trial が作れない。
- primal/adjoint/geometry gate が fail。
- improvement が repeatability/noise floor 以下。
- accepted trial の再利用または rollback lineage が壊れる。

停止は optimizer 強化の合図ではない。原因を objective、constraint、gradient、solver、geometry の
どこに局在できるかを記録し、その一因子だけを修正する。

---

## 9. PQ4 — T-to-S handoff と最初の sharp-interface step

### 9.1 抽出

PQ3 final accepted candidate だけを対象に、事前登録した threshold sweep を実行する。

- projected-volume discrepancy
- component count と root attachment
- minimum solid/void width と gap
- surface self-intersection/manifoldness
- clearance
- candidate/field/threshold/hash lineage

`ready_for_stage_s=true` は全 gate を満たした threshold にだけ付ける。既存 sweep の失敗結果を
上書きせず、新 candidate の evidence を別 artifact として保存する。

### 9.2 Stage S

最初の一歩は body-fitted surface gradient を使う一つの小さな形状更新に限定する。

- drag と downforce の surface directional derivative を別々に centered FD で確認。
- downforce objective の符号と法線規約を固定。
- reinitialization、curvature smoothing、mesh morphing の各作用を別 hash で記録。
- 一 step 後に volume、thickness、clearance、mesh quality を再評価。

gradient FD が不合格なら Hamilton–Jacobi の長時間 evolution を開始しない。

---

## 10. PQ5 — 独立 Stage V verification

比較対象を先に固定する。

1. baseline
2. PQ3 Stage T candidate
3. PQ4 Stage S candidate

各 candidate を同じ qualified profile の三格子以上で評価し、drag と downforce を別 response として
扱う。baseline→T と T→S の required pair を事前登録し、candidate-specific numerical band と
extraction/geometry uncertainty を合わせて、差が解像可能か判定する。

報告語は次に限定する。

- `resolved improvement`: uncertainty band を越える改善が全 required pair で一致
- `resolved degradation`: uncertainty band を越える悪化
- `unresolved`: 差が band 内または pair の符号が定まらない
- `invalid`: mesh、stationarity、lineage、geometry gate のいずれかが不合格

順位相関だけで production optimizer を合格させない。絶対値、差分、grid drift、surface/volume
geometry の同一性を同じ candidate lineage で確認する。

---

## 11. PQ6 — production optimizer と target-physics ladder

PQ5 までの evidence が成立した場合だけ、次を一つずつ追加する。

1. nominal/eroded/dilated 三場の volume、minimum width、worst-case tie rule と全 pullback
2. analytic または adjoint connectivity constraint
3. actual MMA/GCMMA backend。moving asymptotes state と checkpoint を含む
4. turbulence model/wall treatment の qualification
5. finite wing、ground effect、multipoint yaw/ride height
6. isolated front wing、endplate/root、vehicle interference
7. wind-tunnel または他の独立 physical validation

各追加は同じ problem、同じ acceptance rule、同じ evidence class で直前 backend と比較する。
単に iteration 数が減る、または objective が大きく動くことを採用理由にしない。

---

## 12. 実行順と並行性

| 順位 | Slice | 依存 | 重い solver run |
| --- | --- | --- | --- |
| 1A | PQ0.1 nonlinear integration | なし | なし。unit/synthetic integration |
| 1B | PQ2 domain/boundary factor | 登録済み manifest | V2 × 2。1A と並行可 |
| 2 | PQ0.2 real oracle smoke | PQ0.1 | parent/FD/trial の最小組 |
| 3 | PQ1.1 mesh/canonical/source grid qualification | PQ0.2 と campaign manifest | 複数 primal/adjoint。PQ2 と並行可 |
| 4 | PQ3 bounded closed loop | PQ0.2 + PQ1 Path A/B | accepted 最大 3 steps |
| 5 | PQ4 extraction/Stage S | PQ3 candidate | extraction + surface FD + 1 step |
| 6 | PQ5 independent Stage V | fixed T/S candidates + usable PQ2 classification | 3 candidates × 3+ grids |
| 7 | PQ6 production/physics | PQ5 decision | 段階ごとに登録 |

OpenFOAM の重い campaign を同時に走らせて residual、wall time、memory pressure を変えない。
並行実行する場合も solver resource と output directory を分離し、各 run manifest に実行環境を残す。

---

## 13. Milestone と decision gate

| Milestone | 完了条件 | 意味 |
| --- | --- | --- |
| M0.1 | volume/oracle/adjoint/FD bracket semantics が nonlinear path で pass | component ではなく一経路として整合 |
| M0.2 | 実 OpenFOAM smoke と restart が pass | execution capability |
| M1 | PQ1 Path A/B/No-Go 更新 | gradient の利用範囲を固定 |
| M2 | PQ2 usable/bounded/invalid 判定 | Stage V reference の数値範囲を固定 |
| M3 | PQ3 accepted candidate と再現可能 history | 限定 closed-loop capability |
| M4 | Stage S-ready extraction + FD-qualified one-step | sharp-interface capability |
| M5 | required pair の resolved/unresolved/invalid 判定 | architecture の対象候補に対する数値判断 |
| M6 | robust/backend/physics ladder の個別合格 | production claim の候補 |

Milestone は下位 evidence を自動的に target-physics evidence へ昇格させない。

---

## 14. Evidence と検証規則

各 slice は少なくとも次を別 field で記録する。

- evidence class
- input spec/candidate/transform/mesh/solver hashes
- requested と actual backend/profile
- primal/adjoint termination reason、residual、final time
- objective と各 constraint の value/gradient space/units/sign
- proposal、FD bracket、trial、decision、rollback lineage
- mesh/stationarity/geometry gate
- measured、derived、not measured の区別
- supported claim と unsupported claim

コードまたは docs を変えた slice では、最小 relevant test に加えて次を実行する。

```bash
.venv/bin/python -m compileall src tests scripts
.venv/bin/python -m pytest -q
git diff --check
```

solver campaign は command、environment、artifact path、hash、run count を記録する。artifact を
手編集して pass に変えず、再計算または新しい correction artifact で訂正する。

---

## 15. 明示的に保留すること

- gradient magnitude への経験的 scale correction
- PQ3 の 3 accepted steps を超える長時間 optimization
- actual MMA/GCMMA backend
- robust three-field production campaign
- production connectivity finite differences
- adaptive mesh / mesh epochs
- 新しい parametric candidate generator
- Stage S の長時間 Hamilton–Jacobi evolution
- turbulent/high-Re/front-wing/full-vehicle claim

これらは価値がないのではなく、現在の blocker を解決しないため後段へ置く。

---

## 16. 直近の reviewable slice

次の一つの作業は **PQ0.1 nonlinear production path の統合修復**である。

実装順は次に固定する。

1. nonlinear loop に real projected-volume value/gradient を接続し、偽の volume test を置換。
2. primal callback と adjoint callback を分離し、accepted primal artifact を再利用。
3. trial adjoint を `not_applicable`、parent adjoint を fail-closed にする。
4. Path B centered FD bracket と noise-floor/bounds 判定を受理前へ接続。
5. downforce-only + volume reduced problem で `declared_equals_solved` audit を再生成。
6. projection output と solver beta の semantic metadata を一意にする。

この slice が通った後にだけ PQ0.2 の実 OpenFOAM smoke を走らせる。PQ2 の登録済み V2 二因子
campaign は独立に進めてよい。PQ3 の長時間化、MMA/GCMMA、robust 三場は開始しない。
