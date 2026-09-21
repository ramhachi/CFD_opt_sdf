# ダウンフォース最適化 — 実装後の統合・資格化計画（2026-09-21）

Status: **adopted post-implementation plan**. 2026-09-21 の実装と実測を反映し、
旧 DF0–DF7 実装計画の次に実行する作業を定める。

Authority: [`phase_plan.md`](phase_plan.md) がロードマップ、状態、実行順の唯一の
authority である。本書は、その順序を実装・数値実験・合否判定へ展開する詳細計画である。
問題の状態は [`problem_register_2026_09.md`](problem_register_2026_09.md)、schema と
artifact semantics は [`problem_contract_v2.md`](problem_contract_v2.md) と
[`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) に従う。

Baseline: branch `feat/p0-openfoam-closed-loop`, implementation baseline
`4bbd8e3`。ここに記す数値はこの時点までの evidence artifact に限定する。

---

## 1. 結論

Stage T → Stage S → Stage V の構造は維持する。Stage T を捨てる根拠はなく、OpenFOAM
Stage V は引き続き独立した truth/audit とする。一方、**部品の実装完了と、downforce
最適化器としての資格化は別である**。

2026-09-21 までに DF0–DF6 の主要部品は実装された。具体的には ProblemSpec compiler、
DesignTransform、P6 有限差分 campaign、非線形 trial controller、restart、抽出 sweep、
Stage S drag sensitivity path、独立比較 algebra、robust three-field の基礎である。
しかし、これらは一つの production OpenFOAM closed loop としてまだ接続されていない。
また、現在の実測は次の二つの主要 blocker を示している。

1. Stage T の continuous adjoint は、凍結設計上の discrete primal FD に対して
   gradient-aligned 方向で +21.8%、random 方向で +37.6% / +56.8% の差を持つ。
   transfer、設計変化、primal residual は原因から除外されたが、solver 側の不整合は
   未解決である。
2. Stage V の `linearUpwind` family は drag の最細格子 drift を 0.364% まで下げたが、
   downforce は 0.010374 で登録上限 0.005 を超え、三格子列も非単調である。
   downforce の grid-independent claim と GCI は出せない。

したがって次の仕事は、**PQ0 統合整合性 → PQ1 Stage T gradient → PQ2 Stage V
downforce reference → PQ3 実 closed loop → PQ4 Stage S → PQ5 独立検証 → PQ6
production/target physics** の順とする。PQ は post-implementation qualification を表す。

---

## 2. 現在地

### 2.1 実装済みだが、意味を限定すべきもの

| 項目 | 現在の証拠 | 正しく言えること | まだ言えないこと |
| --- | --- | --- | --- |
| DF0 / P18 | 8-shape downforce は候補別 band 後も V1/V2 で pass、25 resolvable pairs、反転 0。17-shape pool は両応答 `unresolved` | 登録された8固定形状では順位反転を観測しなかった | optimizer reachable set 全体、絶対値精度、grid-independent ranking |
| DF1 | compiler、filter/projection/RAMP、transform hash、lineage validator の unit evidence | 必要な primitive と変換部品が存在する | 宣言問題と production solver が完全一致する |
| DF2 / P6 | transfer identity は machine precision、凍結設計 FD campaign 完遂 | mismatch は transfer や primal residual ではなく solver-side chain に局在する | gradient magnitude が 5% gate 内で正しい |
| DF3 | primal re-evaluation、rollback、move reduction、checkpoint の pure-Python loop | 受理制御の部品と deterministic fixture がある | 実 OpenFOAM closed loop、GCMMA 実装、production convergence |
| DF4 | extraction sweep と drag surface sensitivity ingestion | 不合格 threshold を含めて抽出結果を記録できる | `ready_for_stage_s=true` の実 candidate、FD-qualified Stage S step |
| DF5 | required-pair / uncertainty / gate algebra | 比較結果を fail-closed に分類できる | baseline/T/S の三格子実証 |
| DF6 | robust three-field の forward/backward と topology check | robust formulation の基礎 API がある | closed-loop integration、dilated-volume gradient、worst-case active-set処理、production cost |
| Stage V | drag drift 0.364% with `linearUpwind`; downforce drift 0.010374 | drag reference family は登録 2% bound 内 | downforce reference の 0.005 bound、GCI、FSAE target physics |

### 2.2 既存 candidate の抽出結果

既存 `work/ramp_interp/fixture` に対する閾値 0.45 / 0.50 / 0.55 の登録 sweep は、
0.45 で体積相対差 0.716、0.50 で iso 値範囲外、0.55 で connectivity fail だった。
これは抽出 machinery の capability evidence であり、handoff 成功ではない。PQ3 で生成する
新しい候補に対して同じ規則を再実行する。

### 2.3 P18 の扱い

P18 は [`p18_closure_record_2026_09.md`](p18_closure_record_2026_09.md) により
**固定形状 diagnostic として閉じた**。この closure を optimizer-generated shapes へ
拡張しない。今後の候補は candidate hash、transform hash、局所 feature、抽出規則、
候補別数値不確かさ、required decision pairs を新たに登録する。

---

## 3. 統合前に解消する実装上の不整合

以下は新機能候補ではなく、現行部品を正しい一経路にするための必須修正である。

| ID | 不整合 | 影響 | PQ0 での処置 |
| --- | --- | --- | --- |
| I1 | `compile_problem()` が `volume_constraint=None` を返す | projected occupied-volume inequality が宣言問題から消える | ProblemSpecから明示的にcompileする。宣言がなければ暗黙追加せず fail closed |
| I2 | legacy fixed optimizer が control default から connectivity / volume bound を追加し得る | `declared != solved` | compiler出力以外の制約をproduction pathから除き、全 solved term をartifactへ列挙 |
| I3 | `VolumeOccupationConstraint.gradient()` が `DesignTransform.backward()` を使い RAMP derivative まで掛ける | volumeは `rho_projected` 上の定義なのに、`q>0` で勾配が誤る | projectionまでの専用 pullback を追加し、`q=30` を含むFDで検証 |
| I4 | `make_oracle_from_compiled()` がtransformを実際には使わない | solver入力空間と返却gradient空間が曖昧 | `rho_design -> state -> solver field` と `g_solver -> g_design` を型・metadata・hashで明示 |
| I5 | legacy更新は `rho_filtered=rho_projected=rho`, `alpha=beta_max*rho` を再生成する | canonical transformを迂回する | production runnerをDesignTransform一本へ接続。legacy pathはdiagnosticと明記 |
| I6 | trial evaluation でも gradient/adjoint を要求し、accepted trialを再評価する | OpenFOAM計算を重複し、planned cost modelと違う | parentはvalue+gradient、trialはprimal value-onlyへAPI分離し、受理済みpayloadを再利用 |
| I7 | controllerは projected-gradient + merit/trust であり、MMA/GCMMAではない | algorithm claimが実装より強い | 現段階を nonlinear merit/trust controller と呼ぶ。moving asymptote実装後のみGCMMAと呼ぶ |
| I8 | checkpointがProblemSpec hashとbackend stateを完全に束縛しない | resume時に別問題・別backendを混ぜ得る | spec/transform/backend/oracle profile/input hashesを照合し不一致時に停止 |
| I9 | extraction selectionで `0.0 or inf` となる箇所がある | 完全一致の0を最悪値として扱う | `None` と数値0を分離する regression test を追加 |
| I10 | candidate-specific uncertaintyがdocstringに反してdefault bandより小さく設定できる | Gate 4を意図せず緩める | `max(default, candidate)` をAPI内で強制し縮小指定をrejectまたはclamp |
| I11 | independent verificationが三格子をschema上で必須化せず、欠落 uncertainty が0になり得る | algebraだけでqualifiedに見える | grid level数、response別uncertainty、extraction statusを必須化 |
| I12 | robust fieldsはdilated volume値を持つがそのconstraint gradientとworst-case tie ruleがloop未接続 | robust最適化を実行できない | PQ6までprototype扱い。PQ0/PQ3のproduction pathへはまだ入れない |

I1–I12 は、全てを一度に高度化する指示ではない。PQ0 は既存部品を一本化し、未統合機能を
明示的に無効化する。actual GCMMA と robust formulation は PQ5 の証拠が揃うまで保留する。

---

## 4. 維持するアーキテクチャと情報境界

```text
ProblemSpec v2
    │ compile: objective / constraints / response bindings / topology policy
    ▼
CompiledProblem ───────────────┐
    │                          │ hash-bound declaration
    ▼                          ▼
rho_design ── DesignTransform ──> rho_filtered ──> rho_projected ──> beta/alpha
    ▲                                                           │
    │ exact transpose pullback                                  ▼
g_design <────────────────────────────── solver primitive gradient
    │
    ▼
nonlinear merit/trust controller
    ├─ parent: primal + adjoint gradient, once
    ├─ trial: primal values + constraints + geometry gates
    └─ accept / rollback / move update / checkpoint
    │
    ▼
Stage T candidate ── registered extraction ──> Stage S ──> independent Stage V
```

守る原則は次の通り。

1. objectiveは符号を含めてprimitive responseからPython側で合成する。
2. 制約はすべて `g <= 0` に正規化し、宣言されていない制約をproduction runへ追加しない。
3. volumeは `rho_projected`、porous resistanceはRAMP後のfieldという空間差を保つ。
4. optimizerに返す勾配は、solverが微分したfieldを明記してからexact transposeで戻す。
5. accepted/rejectedは必ず非線形primal値と全制約・geometry gateで決める。
6. Stage Vは最適化のtuning signalに使わず、候補固定後の独立比較に限定する。
7. contract/capability、数値資格、reduced-case physics、FSAE target physics、実験妥当性を
   別々のevidence classとして保存する。

---

## 5. PQ0 — production integration closure

### 目的

実装済み部品を、宣言と計算が一致する最小の一経路にする。PQ0中はOpenFOAMの長時間runを
行わず、pure-Python fixtureと既存artifactで統合誤りを除く。

### 作業

1. compilerにvolume inequalityを接続し、objective/constraint/geometry requirementの
   全 solved set をmachine-readableに出力する。
2. DesignTransformに `beta` gradient用と `rho_projected` gradient用の別pullbackを持たせ、
   各APIが受け取るgradient spaceを名前とmetadataで固定する。
3. legacy fixed optimizerはproduction entryから外すか、compiler/transformを消費するadapterに
   する。暗黙のvolume/connectivity、identity transform更新は禁止する。
4. oracleを次に分割する。
   - parent evaluation: primal値、primitive gradients、資格gate
   - trial evaluation: primal値、constraint値、geometry gate
   - accepted trial: trial payloadを次parentとして再利用し、次iteration開始時に一度だけadjoint
5. checkpointへProblemSpec、CompiledProblem、DesignTransform、backend、solver profile、rho、
   response artifactのhashを保存し、resume時に全照合する。
6. I9–I11のfail-closed修正を行う。DF6 prototypeはproduction registryから除外したままにする。
7. docstring、CLI、artifact中の `GCMMA-shaped` 表現を実装内容に合わせて訂正する。

### 合格条件

- compiler artifactに宣言objective/constraintと実際のsolved setが一対一で現れる。
- `q=0` と `q=30` のprojected-volume gradientが中心差分と登録許容差内で一致する。
- transform chainの各fieldに対するdot-product/FD testが通り、gradient spaceを取り違える
  mutation testがfail closedになる。
- 一つのouter iterationで、parent adjointは1回、各trialはprimal-only、受理後の重複primalは0回。
- spec、transform、backendのいずれかを変えたcheckpoint resumeが拒否される。
- extraction差0、uncertainty縮小、二格子だけのverificationがそれぞれtestで検出される。
- repository full test、compileall、`git diff --check` が通る。

### 停止条件

ProblemSpec v2にvolume budgetのauthorityを一意に置けない場合は、推測でdefaultを追加しない。
contract amendmentを独立diffとして先に決める。

### 成果物

- integration testとmutation test
- 一つのfixtureについてのcompiled-problem/transform/checkpoint artifact
- `declared == solved` audit report
- legacy diagnostic pathの明示的status

---

## 6. PQ1 — Stage T gradient oracle の資格化

### 目的

P6の +22%〜+57% mismatchを原因別に分離し、production勾配として通すか、限定的な
FD-confirmed research loopへ落とすかを決める。

### 最初に修復するcampaign semantics

現在のFD campaignは各perturbation rowへadjoint gateを要求するmanifestと、実際にはperturbed
caseでadjointを走らせないrunnerが一致していない。有限差分側に必要なのはqualified primal
valueである。次のように再登録する。

- base: mesh、primal residual/stationarity、requested adjoint residual/final-time/hash gateを全て要求
- `+epsilon/-epsilon`: 同一mesh/spec/solver profile、primal residual/stationarity、response hashを要求
- analytic derivative: base adjointから一度だけ取得
- campaign provenance: baselineとtight-residual probeを別manifest/hashとして束縛

### 原因分離の順序

1. downforce objective source、normal/sign、boundary contribution、porous source derivative、
   sensitivity fieldとfinal-time bindingをcode+dictionary auditする。
2. gradient-alignedに加え、analytic derivativeが数値ノイズ床より十分大きい直交/ランダム方向を
   事前登録する。ほぼ0のrandom derivativeをratio passの根拠にしない。
3. 同一物理形状でStage T格子とadjoint source gridを一因子ずつ細分化し、ratioが1へ近づくか測る。
4. regularisation、primal residual、transferは既に反証/除外した仮説として再試行しない。
5. scalar補正は、方向・epsilon・gridに依存しないことと理論的原因が示せた場合にだけ候補にする。

### 判定経路

**Path A — production gradient pass**

- 事前登録した全有効方向で相対誤差5%以内。
- epsilon plateau、符号、response binding、全資格gateを満たす。
- grid refinementで誤差が悪化せず、選択gridをartifactに固定する。

**Path B — bounded research exception**

5%を満たさないが符号と誤差区間がgrid/directionに対して安定する場合、production gradientとは
呼ばない。PQ3は小規模research campaignに限定し、各提案方向をprimal FDでbracketし、実primal
re-evaluationでのみ受理する。magnitude補正は使わず、結果にはconfiguration-specific boundを付ける。

**No-Go for closed loop**

符号反転、epsilon不安定、grid refinementで発散、またはobjective/BC derivative欠落が残る場合、
PQ3を開始しない。solver-side adjoint formulationを修正してPQ1を再実行する。

### 成果物

- preregistered FD manifest v2
- direction × epsilon × grid のmachine-readable report
- base/perturbation別gate table
- P6 close、bounded exception、またはNo-Goの三値判定

---

## 7. PQ2 — Stage V downforce reference の数値資格化

### 目的

dragで成功した`linearUpwind` familyを固定し、downforceの0.010374 driftがdomain/boundary、
body近傍解像、steady assumptionのどこから来るかを一因子ずつ調べる。

### 実行順

1. 登録済み
   [`evidence/stage_v_domain_boundary_factor_manifest_2026_09.json`](evidence/stage_v_domain_boundary_factor_manifest_2026_09.json)
   を変更せず実行する。candidate、力の正規化、scheme、mesh family、gateを固定する。
2. domain extensionとfar-field boundary treatmentの主効果を判定する。複数因子を同時変更しない。
3. downforce driftが残る場合、結果に応じて次の一因子だけを事前登録する。
   - body/leading-edge近傍解像
   - span/end treatmentと境界距離
   - steady vs time-resolved response
4. 各campaignでpressure、viscous、total force、stationarity、residual、mesh profileを別fieldに保存する。

### 合格と限定継続

- **grid-qualified**: 三格子全てがprofile gateを満たし、最細transitionがdownforce 0.005以内。
  単調/asymptoticである場合だけGCIを報告する。
- **bounded reference**: 0.005を満たさなくても、candidate-specific数値bandを保守的に登録し、
  PQ5のrequired improvementがそのcombined uncertaintyを超える場合だけ限定比較に使える。
  この場合もgrid-independentとは呼ばない。
- **unusable reference**: driftが候補差と同程度以上、またはgate failure/非定常依存が残る場合、
  downforce ranking conclusionを停止する。dragのqualified resultは分離して保持する。

### 成果物

- domain/boundary factor report
- 次因子が必要なら実行前manifest
- response別 numerical uncertainty table
- P16更新

PQ2はPQ0/PQ1と計算資源が競合しない範囲で並行できる。ただし、その結果をPQ3の受理判定へ
接続してはならない。

---

## 8. PQ3 — 最初の実 OpenFOAM closed loop

### Entry gate

- PQ0合格。
- PQ1 Path A、または制約を明記したPath B manifest。
- feasible seedまたは明示的restoration phase。
- solver/case/transform/ProblemSpec hashesが固定されている。

PQ2のgrid-independent downforceはPQ3開始の必須条件ではない。PQ3はStage T loopの成立を調べる
段階であり、最終改善の主張はPQ5まで保留する。

### 最小campaign

1. 単一flow case、単一downforce objective、projected-volume inequality、必要最小限のgeometry gate。
2. backendは現在のprojected-gradientまたはSLSQP bounded proposalを使い、実装名どおりに記録する。
3. parentでprimal+adjointを一度実行し、trialはprimal value-onlyで評価する。
4. trialはobjective、全constraints、geometry gate、solver qualificationを満たした場合だけ受理する。
5. reject時は同じparentへrollbackし、move radius/penaltyを更新する。
6. 各accepted stateでrho系列、solver field、primitive responses、gradients、constraint、hashを保存する。
7. 中断・resume runと連続runが同じaccepted historyを生成することを確認する。

### 合格条件

- 少なくとも一つの非自明なaccepted stepがあり、実primal objectiveが登録した予測/不確かさの範囲で改善する。
- accepted stateは全solver/constraint/geometry gateを満たす。
- reject後にparent artifactが変化しない。
- resumeがaccepted historyとfinal rho hashを再現する。
- 同一seed/run profileで再現可能である。
- 最終候補がhandoff preregistrationを持つ。`ready_for_stage_s` はPQ4の抽出結果で判定する。

### 停止条件

- PQ1 Path BでFD bracketが提案方向の符号を支持しない。
- trialのprimalが収束しない、制約を改善しない、geometry gateを繰り返し破る。
- objective改善がStage T数値不確かさを超えない。

停止時はbackendを強くする前に、gradient、feasibility、transform、constraint scalingのどこで
止まったかを分離する。actual MMA/GCMMA導入を失敗隠しに使わない。

---

## 9. PQ4 — T-to-S handoff と Stage S の最初の一歩

### 作業

1. PQ3の最終accepted candidateへ登録threshold sweepを実行する。
2. volume差、watertightness、component、self-intersection、feature survival、revoxelized差を測る。
3. thresholdは事前登録したrange/ruleから選び、観測後のbest threshold選択をしない。
4. downforceとdragの各adjoint surface sensitivityをsolver suffixで分離して取得する。
5. surface gradientを法線方向の中心差分で符号・scaleまで検証する。
6. 最初のshape updateは既存OpenFOAM capabilityの`volumetricBSplines` + morpherを優先する。
7. remesh後に全geometry/mesh/response gateを再評価し、失敗時はrollbackする。

### 合格条件

- `ready_for_stage_s=true` の実candidateが得られる。
- 選択thresholdと未選択rowが全てhash付きで残る。
- downforce/drag surface gradientが登録FD gateを通る。
- 一つのStage S stepが非線形primalで受理され、constraintとgeometryを維持する。

### 停止条件

抽出差またはremesh差がresponse改善より大きい場合、Stage Sを進めずhandoff layerを修正する。
custom CutFEM/ghost-node solverは、この既存body-fitted経路が原理的に不可能と示されるまで導入しない。

---

## 10. PQ5 — 独立 Stage V verification

### 比較対象

- baseline
- PQ3のStage T candidate
- PQ4のStage S candidate

required pairsは最低でも `baseline -> Stage T` と `Stage T -> Stage S` を事前登録する。

### 実行と判定

1. 同一のdeclared domain、clearance preflight、flow condition、force normalizationで各候補を評価する。
2. 各候補は最低三つのqualified grid levelを持つ。grid level欠落をuncertainty 0として扱わない。
3. pressure、viscous、total force、moment、mesh/residual/stationarity gateを保存する。
4. numerical uncertaintyとextraction/remesh uncertaintyを候補・response別に保存する。
5. required pairの改善を登録combined-uncertainty ruleと比較する。
6. Stage V結果はoptimizerへ戻さず、`used_in_optimization=false` を強制する。

### 判定語

- `improved`: 正しい方向の差が登録combined uncertaintyを超え、両候補の全gateが通る。
- `unresolved`: 差がband内、抽出未測定、またはdownforce referenceが限定bandしか持たない。
- `regressed`: 誤った方向の差がbandを超える。
- `gate_failed`: どちらかの候補がmesh/residual/stationarity/geometry gateを満たさない。

downforceが`unresolved`でもdragのqualified結論を消さない。応答ごとに結論を分離する。

### PQ5 exit

`baseline -> T` と `T -> S` がdownforceで`improved`なら、縮約caseでのT→S→V architectureを
qualifiedとする。これは依然としてreduced laminar caseの結論であり、FSAE vehicle/Reynolds
numberへは外挿しない。

---

## 11. PQ6 — production optimizer と target-physics ladder

PQ5で縮約caseが成立した後だけ開始する。

### 11.1 robust length scale

1. eroded/intermediate/dilated三場を同一loopへ統合する。
2. dilated fieldのvolume constraint gradientをFD検証する。
3. worst-case objectiveのactive fieldとtie/subgradient ruleをartifact化する。
4. 三場が同じtopologyを持つことをa posterioriに確認する。これを保証の代用にしない。
5. outer iterationあたり三組のprimal/adjoint costをbudget manifestに入れる。

### 11.2 actual MMA/GCMMA backend

moving asymptotes、separable convex approximation、conservative inner iteration、KKT residualを
実装または既存libraryから導入した時点で初めてMMA/GCMMAと呼ぶ。選定は再現性、license、
sparse scaling、checkpoint stateを基準にし、PQ3のbackendと同一問題・同一合否規則で比較する。

### 11.3 physics ladder

各levelは前levelの独立検証をentry gateとする。

1. reduced laminar porous/body-fitted parity
2. turbulence bridgeでporous sourceとwall distance/`nut`の相互作用を分離
3. finite wing、end condition、multi-element geometry
4. moving ground、ride-height/yaw/multipoint
5. full-vehicle interference
6. mesh/solver/model-form uncertaintyを伴うtarget-Re verification
7. wind-tunnelまたは走行計測によるphysical validation

どのlevelでも、前levelのthresholdを黙って流用しない。ProblemSpec、qualification profile、
uncertainty、required comparisonsをlevelごとに登録する。

---

## 12. 実行順、並行性、計算資源

| 順序 | 作業 | 並行可否 | 主な計算負荷 |
| --- | --- | --- | --- |
| 1 | PQ0 integration closure | 単独で先行 | unit/integration tests |
| 2A | PQ1 gradient qualification | PQ2と並行可 | Stage T primal/adjoint FD campaign |
| 2B | PQ2 Stage V domain/boundary factor | PQ1と並行可 | heavy OpenFOAM three-grid/factor runs |
| 3 | PQ3 first real closed loop | PQ0必須、PQ1判定必須 | repeated Stage T primal/adjoint |
| 4 | PQ4 Stage S | PQ3 candidate必須 | extraction + body-fitted adjoint/morphing |
| 5 | PQ5 independent Stage V | PQ3/PQ4 candidate固定後 | 3 candidates × 3+ grids |
| 6 | PQ6 production/physics | PQ5 pass後 | robust 3-field、target-physics campaigns |

計算資源は、cheapなcontract/FD fixtureから先に使う。Stage Vの長時間runは登録manifestと
stop ruleがあるcampaignだけに限定する。同じ不合格条件で格子やiteration上限を無制限に増やさない。

---

## 13. マイルストーンと decision gate

| Milestone | 完了条件 | 次の判断 |
| --- | --- | --- |
| M0 | PQ0全合格、declared==solved、one transform owner | Stage T数値campaignをproduction code pathで実行可 |
| M1 | PQ1 Path A/B/No-Go確定 | Path AはPQ3、Path Bは限定PQ3、No-Goはsolver修正 |
| M2 | PQ2 grid-qualified/bounded/unusable確定 | PQ5で使えるdownforce evidence範囲を固定 |
| M3 | PQ3 accepted closed-loop candidateと再現可能restart | extractionへ進む |
| M4 | `ready_for_stage_s=true`、surface FD、Stage S一歩 | independent comparisonへ進む |
| M5 | baseline→T、T→S required pair verdict | architecture pass/unresolved/regressedを決める |
| M6 | robust/backend qualification | target-physics ladderへ進む |
| M7 | target caseの数値・model-form・physical validation | 実車設計判断に使える範囲を宣言 |

---

## 14. 共通 evidence と検証規則

各sliceは、少なくとも次を別fieldで残す。

- command、return code、environment、git commit
- ProblemSpec / transform / candidate / solver dictionaryのpathとSHA-256
- mesh、primal residual、adjoint residual、force stationarity、geometry gate
- raw response、gradient、constraint、uncertainty
- evidence class: contract / capability / numerical / reduced-physics / target-physics / physical
- pass、bounded、unresolved、No-Goのmachine verdict
- 結論で除外したclaim

コードまたはdocsを変えたsliceでは次を実行する。

```bash
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest -q
git diff --check
```

OpenFOAM campaignでは、full test通過とsolver run成功を混同しない。solver outputはcampaign
manifestとqualification reportを通して初めてevidenceになる。

---

## 15. 明示的に保留すること

- Stage T solverの全面置換
- 固定形状rankingだけを根拠にしたproduction optimization claim
- 現在のmerit/trust controllerをGCMMAと呼ぶこと
- P6 mismatchの経験的な一律scale補正
- downforceのGCIまたはgrid-independent claim
- 既存の不合格fixtureを使ったStage S成功claim
- PQ5前のrobust three-field production投入
- reduced steady laminar evidenceからFSAE/full-vehicle performanceへの外挿
- 独立検証前のStage V結果によるoptimizer tuning

この保留はアーキテクチャを弱めるものではない。何が実装され、何が数値的に正しく、何が
対象物理で有効かを分けることで、次の計算が実際に判断を前へ進めるようにする。

---

## 16. 直近の一つの作業

次のreviewable sliceは **PQ0 production integration closure** である。I1–I11を一括で雑に
直すのではなく、次の順で小さく閉じる。

1. projected-volume constraintとgradient-space API
2. compiler-only solved setとDesignTransform接続
3. parent-gradient / trial-value oracle分離
4. checkpoint/hash binding
5. extraction/uncertainty/three-grid fail-closed修正
6. integration fixture、mutation tests、full validation

PQ0が通るまで、長時間のproduction optimizer run、actual GCMMA導入、robust三場campaignは
開始しない。PQ2の登録済みdomain/boundary factorだけは、独立したreference campaignとして
計算資源に余裕があれば並行実行できる。
