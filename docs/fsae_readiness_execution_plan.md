# FSAE全車高速空力最適化へ向けた実行計画

作成日: 2026-09-11  
状態: 実装計画  
対象ブランチ: `feat/p0-semantic-binding`

## この文書の位置づけ

この文書は [`phase_plan.md`](phase_plan.md) の下位にある実行計画である。
プロジェクトの唯一のロードマップ、G0--G4のゲート、対応範囲、証拠の扱いは
`phase_plan.md`を正とする。この文書は、そこに記載された「直ちに実行する順序」を、
実装単位、成果物、依存関係、Go/No-Go判定、ブランチ順序まで具体化する。

両文書が矛盾した場合は`phase_plan.md`を優先し、この文書を修正する。P0--P8は
この文書で管理する作業パッケージ名であり、`development_plan_2026_09.md`にある
別のP0--P5計画や、`phase_plan.md`のG1--G4ゲートを置き換えない。G1--G4は
引き続き必須であり、Pの完了だけで物理妥当性や製品化を宣言しない。

最終目標はFSAE全車の高速空力最適化である。ただし、FSAE全車の目的関数、運転条件、
車両部品の設計範囲は、この計画の最後まで確定しない。先に、FSAEの問題設定を載せても
意味論と検証経路が壊れない汎用の最小閉ループを成立させる。

## 最終的に作る経路

```text
ProblemSpec v2
  -> geometry / resolution / semantic gates
  -> Stage T: fixed-grid rho / Brinkman topology exploration
  -> cell-centered rho -> iso-surface -> SDF
  -> Stage S: sharp-interface shape refinement
  -> Stage V: independent body-fitted CFD verification
  -> reproducible accepted design and evidence bundle
  -> FSAE full-vehicle profile
```

各段階は、直前の段階の成功を自動的に引き継がない。特に、次の三つを別の責務として
維持する。

- density/Brinkmanは、材料の発生・消滅を含むトポロジー探索の候補生成器。
- SDFは、抽出された境界を連続的に改善する形状表現。
- body-fitted CFDは、最適化経路から独立した空力監査と最終評価器。

LBM、CUDA、Metalなどの高速バックエンドは、同じ問題、同じ応答定義、同じ合否条件で
総時間とメモリの優位性が実測できた範囲だけを昇格させる。高速なソルバが動くこと自体を
FSAE空力の成立とは扱わない。

## 現時点で確定していることと、まだ言えないこと

2026-09-10の [アーキテクチャ有効性レポート](architecture_effectiveness_2026_09.md)
から、現時点で言えることを次に限定する。

| 区分 | 現時点の判定 | 根拠と限界 |
| --- | --- | --- |
| Stage Tの局所数値能力 | 限定条件で確認 | 8192セル固定格子Brinkmanケースでprimalとdrag/downforce随伴が収束し、`epsilon=1e-4`の方向微分が有限差分と2.23--4.35%で一致した。単一ケースの局所結果である。 |
| 小さな目的単独step | 限定条件で確認 | `move_limit=1e-4`で同一fidelity再評価の実変化/予測変化が約0.955、再評価誤差4.51%だった。制約付き反復の証明ではない。 |
| 大きなstep | 不成立 | `move_limit=0.03`では比が約0.2815に低下し、dragと効率制約が悪化した。局所線形予測を大stepへ外挿できない。 |
| 制約付き最適化 | 未成立 | 記録された基準は`g_eff=3CD-CDF=9.601...`、active-cell mean `rho=0.01925`で、使用した効率・density下限を満たさない。connectivityも未評価である。 |
| Stage T -> Stage S | 変換能力のみ接続、資格未成立 | T5のcell-data `rho`からiso-surface/SDFと自己完結した診断bundleを生成できる。現T5は変換後の体積を保持せず、required lineageと定量fidelity gateもないため、同一候補をStage Sへ投入できる証拠にはならない。 |
| Stage S -> Stage V | 未実証 | sharp-interface refinement後のbody-fitted再評価と三格子のcross-fidelity判定がない。 |
| Mac/Windows高速化 | 未実証 | Macの小規模Docker実行だけがあり、Windows RTX 4070 Ti、CUDA、対象規模、peak memory、改善候補までの総時間は未測定である。 |
| FSAE全車 | 未着手 | 最終問題設定は閉ループとfront-wing級ベンチマークの資格化後に定義する。 |

したがって、現在の成果を「アーキテクチャ全体の実証」「空力最適化の成立」「FSAEに
適用可能」と表現してはならない。現在の証拠は、Stage Tの狭い局所数値制御に限る。

## 証拠の分類と報告境界

すべての実行結果は、次の証拠クラスをartifactの`evidence_class`と報告文の両方に持つ。

| クラス | 意味 | それだけで言えないこと |
| --- | --- | --- |
| `contract` | ProblemSpec、ID、単位、hash、役割、artifact namespaceの整合 | solverが収束した、物理が妥当、最適化に成功した |
| `capability` | あるCLI、backend、変換、またはsolver操作がcanonical fixtureで実行できた | 対象Reの空力が正しい、独立検証を通った |
| `numerical` | 残差、質量収支、定常性、随伴、勾配、Taylor/FD gateを満たした | body-fitted形状、乱流、車両空力への外挿 |
| `target_physics` | 宣言した運転条件、物理モデル、格子収束、cross-fidelityを満たした | 別の運転条件、別の車両、実走行性能 |
| `benchmark` | 定めたgeometry familyと三格子・制約・再現性の受入集合を満たした | 任意の形状やFSAE全車への一般化 |
| `performance` | 同一品質に到達するend-to-end時間とpeak memoryを測定した | 物理精度の向上、未資格の高速backendの採用 |

`execution_ready: true`、return code 0、solverの終了マーカー、短いsmoke run、
LBMのTaylor--Green、単体solverの`ClockTime`は、上位の証拠クラスを代用しない。
`work/`にある生成物は履歴・診断の根拠として扱い、再計算した物理資格の証拠とは区別する。

## 依存関係と実行順序

### 全体依存グラフ

```text
G1 contract (既存)
        |
        v
P0 shared semantic binding / canonical fixture
        |
        +--------------------+
        v                    v
P1 T rho -> SDF bridge    P3 feasible T loop
        |                    |
        v                    v
P2 same-candidate Stage V  P4 G3 + B0--B2
        +---------+----------+
                  v
        P5 production Stage T
                  |
                  v
        P6 Stage S + Stage V + B3--B5
                  |
                  v
        P7 Mac/Windows qualification and fast backend
                  |
                  v
        P8 FSAE full-vehicle entry
```

P1のbridgeとP3のtrust-region制御の骨格はP0の後に並行して設計できる。ただし、P3の
candidate再評価とaccept/rejectの統合はP2で確定した再評価形式に依存するため、P2の
出力なしに閉ループのGo判定は行わない。P2はP1の出力を使う。P5をproduction optimizer
として昇格するには、P0、P3、P4のGo条件が必要である。P6はP5の候補生成を使うが、
Stage Vのbody-fitted基準評価器はP2で先に作り、P5の完成を待ってから新規に作り始めない。

| パッケージ | 依存するもの | 役割 | 次へ進む条件 |
| --- | --- | --- | --- |
| P0 | G1、現行G2数値fixture | 共通意味論、実行環境、canonical fixture、勾配gateを固定 | semantic bindingと局所勾配gateがpass |
| P1 | P0、G3の基本voxel情報 | T5 cell-data `rho`をSDF・表面へ渡し、変換誤差を定量化 | fail-closed handoffとfidelity reportがpass |
| P2 | P0、P1、G2 runtime、G3の必要部分 | 同一baseline/candidateをStage Vで独立再評価 | 三格子cross-fidelity gateがpass、または原因を特定してNo-Go |
| P3 | P0、P2の候補・再評価形式 | 可行性回復、trust region、accept/reject、rollback、checkpoint | 可行baselineと3 accepted step、1 rejectが再現可能 |
| P4 | P1、P3、G2 qualification | 完全なG3とG4 B0--B2、幾何・解像度・接続性 | B0--B2と全geometry gateがpass |
| P5 | P0、P3、P4 | production Stage Tの一般応答・制約・backend | nonlinear反復を実CFD再評価付きで資格化 |
| P6 | P2、P4、P5 | Stage S refinement、Stage V RANS、B3--B5 | 三格子、圧力/摩擦分解、cross-fidelityがpass |
| P7 | P6、固定した品質・時間・メモリ基準 | Mac/Windowsと候補高速backendを同一条件で比較 | 品質を落とさずend-to-end優位性を実測 |
| P8 | P6、P7、B5、全entry gate | FSAE全車の問題定義、baseline、段階導入 | 全車baselineが資格化し、段階的候補がVで確認 |

## P0 — 共通意味論と最小canonical fixture

### 目的

Stage TとStage Vが同じ物理量・符号・基準量を評価していることを、実行前に機械的に
検証できるようにする。ここで現行の診断fixtureを勝手に「可行」と読み替えない。
2026-09-10の結果は診断用履歴として保存し、閉ループ用には可行なseedと明示した制約を
持つ別profileを作る。閾値を結果に合わせて緩めることは禁止する。

### 実装内容

- `ProblemSpec v2`へ、座標系、SI単位、`Uref`、流体密度、動粘性/粘性、`Aref`、基準長、
  モーメント中心、力・モーメント方向、符号を束ねる。
- Stage Tの応答が係数かNかを明示し、Stage Vと比較する際は同じ量へ変換する。
  `porousDirectionalForce`の係数を未証明のまま力[N]として扱わない。
- `rho`、filter、projection、Brinkman係数、設計セルmask、固定物、禁止領域、rootの
  意味をbindingに記録する。
- OpenFOAM cell labelとcanonical uniform Cartesian gridの対応を、origin、spacing、
  extent、ordering、hash付きで固定する。
- aggregate objective/constraintとtopology-policy constraintのID/scopeを区別する。
- primal/sensitivity/geometry/handoffの全artifactに、`problem_id`、
  `problem_spec_sha256`、`candidate_id`、`parent_candidate_id`、solver/profile、
  input hashを持たせる。
- 現行の効率式、active-cell mean `rho`下限、volumeの意味を検査し、目的の改善と
  可行性回復を別profileにする。
- residual、normalized mass imbalance、response stationarity、adjoint residualを
  fresh processの実行から収集する。終了マーカーだけで合格にしない。

### 成果物

```text
canonical_fixture/
  problem.yaml
  problem_snapshot.json
  semantic_binding.json
  grid_mapping.json
  baseline_contract_report.json
  gradient_validation.json
```

加えて、再実行に必要なsolver image、case template、Python環境、実行コマンド、
主要ファイルのSHA-256をmanifestに残す。生成データそのものが大きい場合は、Git管理外の
保存先とhashを結び付ける。

### 勾配gate

`epsilon=3e-5, 1e-4, 3e-4, 1e-3`程度のlog sweepを行い、既存の正規化方向と、seed固定の
filtered-random方向を少なくとも2本検査する。局所範囲で、

- 有限差分と随伴の符号が一致する。
- `FD/adjoint`が暫定的に`0.8--1.2`へ入り、相対誤差10%以内である。
- perturbationがsolverの応答ノイズ床より十分大きい。
- filter/projectionのchain ruleを含む設計変数の意味がartifactに残る。

を要求する。`epsilon=1e-4`の一方向で既に得られた2.23--4.35%は合格材料だが、P0の
全方向gateを代替しない。

### No-Go

単位、符号、hash、grid mapping、response selector、`rho`勾配の意味のいずれかが
曖昧なら、P1以降へ進めない。FD/随伴が2回の独立試行で失敗した場合は、optimizerを
調整せず、response assembly、solver収束、filter chain、cell orderingのどこで不一致が
起きたかを特定する。

## P1 — T5 cell-densityからSDFへのhandoff

### 目的

T5が生成するcell-centered `rho`を、別の候補として再生成するのではなく、同一候補の
系譜を保ったままiso-surface、閉じたsurface、SDF、再voxelizationへ変換する。legacyの
point-data density経路は参照実装・履歴証拠として使ってよいが、T5の成功を証明する代用に
しない。

### 実装内容

1. `rho` fieldとtopology stateを読み、grid metadataとhashを検証する。
2. 抽出対象がraw、filtered、projectedのどれかをProblemSpecで固定する。
3. iso値と内外符号（固体内負、流体側正）を記録してsurfaceを抽出する。
4. watertightness、face orientation、degenerate face、self-intersectionを検査する。
5. surfaceからSDFを再構築し、必要なら同じgridへ再voxelizeする。
6. fixed solid、forbidden、design domain、rootのgeometry roleを再bindする。
7. 元のdensityと変換後の形状について、体積、表面位置、component、root、厚さ、隙間、
   hard-maskを比較する。

### 必須artifact

```text
handoff_manifest.json
  source_topology_state.json
  source_density.vti
  iso_surface.stl
  signed_distance.vti
  revoxelized_density.vti
  geometry_binding.json
  fidelity_report.json
```

manifestには、source/derivedのhash、iso値、grid transform、SDF符号、抽出対象、失敗理由を
含め、hashで固定した`geometry_binding.json`へ座標系、problem identity、candidate lineageを
記録する。現行T1/T5のようなlegacy入力は、欠落項目を`missing_lineage`に記録した
`status=diagnostic_only`のbundle生成だけを許可し、必ず`ready_for_stage_s=false`とする。
資格実行では`problem_id`、`problem_spec_sha256`、`candidate_id`を必須とし、欠落、hash不一致、
または変換前に確定する入力不正はartifactを発行せずfail-closedで拒否する。

### fidelity gate

数値閾値は、最初のcanonical fixtureを実行する前にmanifestまたはProblemSpec profileへ
固定する。初期提案は次の通りである。

- `rho`の上下限違反は`1e-7`以下、design mask外の変更はゼロ。
- 正規化されたhard constraint違反は`1e-3`以下。
- 体積差、表面/Hausdorff差は`Delta x`と基準体積で正規化し、fixtureで定めた範囲内。
- nominal/erodedのcomponent数と必須root接続は一致する。
- 最小固体幅、最小空隙幅、最小gapが抽出後も成立する。
- forbidden regionへの交差はゼロ。

体積誤差やsurface誤差の閾値を、結果を見て後から広げてGoにしてはならない。閾値変更が
必要な場合は新しいprofileと再認定として記録する。

### No-Go

surfaceが閉じない、component/rootが失われる、forbiddenに侵入する、grid mappingが
一意でない、または再voxelization後に制約が変わる候補はStage S/Vへ渡さない。単純な
形状でbridgeが通らない場合は、Stage S solverの実装に進まず、抽出・SDF・役割maskの
どこを修正するかを限定する。

## P2 — 同一candidateのStage V独立再評価

### 目的

P0で固定したbaselineと、既存T5で得られた小さなcandidateを、同じProblemSpecの
body-fitted OpenFOAMへ渡す。目的は、Tで検出した改善方向がsurface/SDF変換後にも残るかを
調べることであり、T5の目的単独再評価をStage Vの成功として数えない。

### 実装内容

- baselineとcandidateで、同じ流入、出口、壁、moving-wall、物性、`Aref`、`Uref`、
  力・モーメントの向きを使う。
- 最初は同じ単純形状とmedium格子でcase生成、mesh quality、primal収束、質量収支、
  response stationarityを確認する。
- その後coarse/medium/fineの三格子でbaseline/candidateを再計算する。
- pressure force、skin-friction force、total force、必要なmomentを別々に保存する。
- Stage Tのporous response、Stage S surface、Stage V body-fitted responseを一つの
  lineage manifestへ結び付ける。

三格子で、最小化目的`J`、baselineを`b`、candidateを`c`、medium/fineを`m/f`として、
結果を見る前に固定した正の`J_scale`で次を記録する。

```text
I_f = (J_b,f - J_c,f) / max(abs(J_b,f), J_scale)
S_b = abs(J_b,f - J_b,m) / max(abs(J_b,f), J_scale)
S_c = abs(J_c,f - J_c,m) / max(abs(J_b,f), J_scale)
```

暫定Go条件は、fineで改善符号が正、coarse/medium/fineで符号が変わらず、
`I_f > 2 * max(S_b, S_c)`、かつ全hard constraintがpassすることとする。改善量が
solver noiseやmesh uncertaintyより小さい場合は、改善と呼ばず`inconclusive`とする。

### 成果物

```text
stage_v_audit/
  baseline/{coarse,medium,fine}/
  candidate/{coarse,medium,fine}/
  cross_fidelity_summary.json
  force_decomposition.json
  mesh_quality_summary.json
  lineage_manifest.json
```

### No-Go

TとVの改善符号が反転した場合、全車への拡張、GPU化、最適化step数の増加を止める。
原因をdensity-to-surface transfer、Brinkman近似、response binding、body-fitted mesh、
対象物理のいずれかへ分類し、該当箇所の再実験を行う。P2を通らないcandidateは、
「最適化候補」ではなく診断データとして保存する。

## P3 — 可行性回復とStage Tの最小閉ループ

### 目的

目的関数の局所改善だけでなく、candidateの安価な制約検査、同一fidelityのprimal再評価、
actual/predicted判定、accept/reject、rollback、trust-radius、checkpointを一つの反復へ
まとめる。

### 実装順序

1. baselineが可行なら通常モードへ入る。不可行なら目的改善を始めず、
   
   `Phi(rho) = sum_i w_i * max(0, c_i(rho))^2`

   を使うfeasibility-restoration profileへ入る。
2. `rho` bounds、fixed/forbidden mask、volume、efficiency、nominal/eroded
   connectivity、最小幅・gapをcandidate生成前後に検査する。
3. 初期`||Delta rho||_inf=1e-4`から始め、candidateごとの予測目的・制約変化を保存する。
4. 同じmesh、BC、solver設定、ProblemSpecでfresh primalを実行する。baselineのresponseと
   gradientはradius retryの間は再利用し、不要なadjointを繰り返さない。
5. 最小化目的について、

   `r = (J_base - J_actual) / (J_base - J_predicted)`

   を計算する。予測変化がsolver noise floorの3倍未満ならratioは`inconclusive`とし、
   acceptの根拠にしない。
6. accept時だけcheckpointとcandidateを昇格する。reject時はbaselineへ完全rollbackし、
   candidateを最良解として保存しない。

### trust-region初期規則

| 条件 | 動作 |
| --- | --- |
| solver/contract/hard constraint失敗、または符号不一致 | reject、rollback、radius `x0.5` |
| `r < 0.25` | reject、rollback、radius `x0.5` |
| `0.25 <= r < 0.5` | 通常最適化ではreject。修復モードでは違反減少を条件に限定accept |
| `0.5 <= r <= 2.0`かつ可行性を満たす | accept |
| `r > 2.0` | accept可能だがモデル不一致としてradiusを拡大しない |
| 良好なacceptが2回連続し、制約余裕が増えた | radius `x1.25`、上限は初期`1e-3` |
| 3回連続reject、またはradius `<=1e-6`で改善なし | `STOP: trust-region stalled` |

### P3の閉ループGo条件

一つのcanonical fixtureで、次を同時に示す。

- 可行baseline、または明示的なrestorationによる可行化。
- `0.5 <= r <= 2.0`を満たすaccepted+revalidated stepを3回。
- 意図的なoversize stepを1回rejectし、直前のaccepted stateへrollback。
- hard constraint違反ゼロ、通常モードの全制約pass。
- checkpointからcandidate ID、親ID、hash、response、gradientを再現。
- 同じseed、同じ環境で履歴の順序と判定が再現する。

ここを通るまでは、既存のprojected-gradient/SLSQP adapterを配管検証に使ってよいが、
production optimizerや「最適化済み形状」と呼ばない。`move_limit=0.03`の結果は回帰用の
非線形性fixtureとして残す。

## P4 — G3完全化とG4 B0--B2

### 目的

実形状に対して意味のある幾何・解像度・接続性を評価し、production Stage Tを開始できる
最低限のbenchmark ladderを作る。

### G3で実装する検査

- STLの単位、座標、watertightness、orientation、self-intersection、degenerate face。
- fixed-solid/design-domain/forbidden/rootの役割別mask。
- minimum solid width、void width、gap、clearanceのcells-per-feature。
- erosion/dilation半径が表現解像度未満になっていないこと。
- density-to-SDF体積・表面/Hausdorff・component/root・hard-mask・feature survival。
- nominal/eroded connectivityの実評価。

少なくとも「1セル幅bridgeはfail」「表現可能な幅のbridgeはpass」「孤立島はfail」
「rootから切れた形状はfail」「no-op erosionは製造証拠にならない」をfixtureで固定する。

### G4 B0--B2

既存の汎用CLIとYAML/STL差し替えで進め、benchmarkごとの特殊コアコードを作らない。

1. B0: sphere、box、thin plate、multiple components、invalid STL。
2. B1: islands、2--6セルbridge、cellwiseおよびfiltered-random gradient check。
3. B2: channel、cylinder、NACAのlaminar 2D/2.5D、coarse/medium/fine。

各benchmarkは、grey-density、抽出後geometryの制約状態、solver収束、主要response、
hash、環境、seedを保存する。P4のGoなしに、GCMMA調整やメッシュ階層を増やさない。

## P5 — production Stage T

### 目的

P3の閉ループを、単一の診断fixtureに依存しない一般response・aggregate objective・
constraint・topology policyへ拡張する。production開始は、`phase_plan.md`に従いG2 runtime
qualificationと関連G3/G4 gateの後である。

### 実装順序

1. 実solverからnative v2 primal/sensitivity artifactを出すsemantic bindingを資格化する。
2. flow responseからobjective、aggregate constraint、multipoint contributionを組み立てる。
3. nominal/eroded connectivityとminimum-feature constraintを、定義した意味に対応する
   derivativeまたは安全な評価器へ接続する。
4. filter/projection continuationとchain-rule metadataを固定する。
5. re-evaluation、acceptance/rollback、move bound、checkpoint/resume、deterministic
   artifactを一般反復へ移す。
6. 既存optimizer interfaceの背後にGCMMAまたは同等の疎でスケーラブルなbackendを置く。
7. uniform fixed-grid profileが資格化した後に限り、mesh epochと保存的なstate/gradient
   transferを追加する。

新しいparametric candidate generatorはこの順序へ入れない。密度設計変数とSDF形状変数の
意味を混ぜず、どちらの勾配かを各artifactへ書く。

## P6 — Stage S refinementとStage V資格化

### Stage S

P1で作ったhandoffを入力にして、まずbody-fitted-firstを基準とする小さなnormal
deformationをSDFで行う。root、fixed-solid、forbidden、最小寸法を固定し、再初期化後の
ゼロ等値面、体積、接続性を再検査する。

初期の形状自由度は、数個から十数個の滑らかなnormal-displacement basisでよい。形状
勾配または有限差分/Taylor testを確認してから、Hamilton--Jacobi更新、curvature control、
ghost-node IBM、cut-cell、output-based adaptationを比較する。高機能なsharp-interface
solverを先に作らない。

### Stage V

body-fitted OpenFOAMでcoarse/medium/fineを実行し、pressure、skin friction、total force、
moment、mesh quality、mass balance、stationarityを保存する。Stage T、Stage S、Stage V
の候補を同じID系譜で追跡する。

### G4 B3--B5

1. B3: flat plateとNACAのturbulent bridge、porous/body-fitted比較、壁面処理。
2. B4: finite wing、bluff body、multi-component objectのgeneric 3D。
3. B5: isolated front wing、moving ground、root/endplate、必要に応じたvehicle profile。

Stage VのGoは、三格子で改善符号が変わらず、fine-grid改善がgrid uncertaintyを上回り、
圧力・摩擦・合力・モーメントの意味が一致し、hard constraintが全てpassすることとする。

## P7 — Mac/Windowsと高速backendの資格化

### 比較対象

OpenFOAM Stage T/Vを独立した参照経路として残し、candidate高速backendは同じProblemSpec、
初期形状、受入条件、精度条件で比較する。Macは32 GB unified memory、Windowsは32 GB host
RAMとRTX 4070 TiのVRAMを別予算として記録する。VRAM容量をhost RAMに合算しない。

### 測定範囲

```text
ProblemSpec検証開始
  -> geometry / mesh生成
  -> primal / adjoint
  -> candidate生成
  -> rejectを含む再評価
  -> T->S handoff
  -> Stage V三格子監査
  -> 最初の合格artifact書込み
```

`T_total`は上記全体のwall timeとし、solver単体のClockTimeや反復数を性能証拠にしない。
setup、solver、I/O、geometry変換、reject retry、peak host memory、GPU/Metal allocation、
precision、convergence、最終判定を分けて保存する。

CUDA/Metal/LBMの採否は、target physicsとP6の品質を満たした上で、同じE1/E2品質に到達する
end-to-end時間が短く、メモリ予算内で完走することを要求する。物理・境界・力積分・adjoint・
SDF couplingが未資格のbackendを、速度だけで昇格しない。

## P8 — FSAE全車への入口と段階導入

### FSAE問題を定義してよい条件

次を全て満たすまで、FSAE全車の最終目的関数を固定しない。

- P0の共通ProblemSpec、response units、sign、reference、grid mappingが資格化。
- P1のT cell-density -> surface/SDF handoffがhashとfidelity gate付きで動作。
- P2の同一candidateがStage V三格子で独立評価できる。
- P3の可行性回復、accept/reject、rollback、checkpoint/resumeが再現可能。
- G3のmask、root、component、minimum width/gap、nominal/eroded gateが完成。
- P4のB0--B2が完了し、少なくとも三つのgeometry familyで汎用性を示す。
- P5で実solverの一般response/constraint derivativeと非線形再評価が資格化。
- P6のStage SとStage V、B3--B5で三格子cross-fidelityが通る。
- pressure、skin friction、total force、moment、mass balance、mesh qualityを記録できる。
- moving groundと、対象に含める場合のrotating wheelの意味が実装・検証済み。
- P7でMac/Windowsの合否が同じ品質基準で再現し、32 GB予算を超えない。

### 段階導入

1. 全車の非最適化baselineを一つのProblemSpecで作り、三格子・全response・全constraintを
   先に資格化する。
2. 全車candidateを一つだけ作り、T/S/Vを通して改善符号と制約余裕を確認する。
3. isolated front wing、underfloor、diffuserなど、設計責務が分離できる領域から自由度を
   増やす。
4. yaw、ride height、pitch/heave、速度、moving ground、wheel rotation、部品間干渉を、
   一度に一要素ずつ追加する。
5. 複数条件のweighted objective、front/rear aero balance、drag/downforce、momentを、
   各responseの単位・重み・許容幅とともに明示する。

FSAE全車の問題定義で決める項目は、drag/downforce、aero balance、pitch/yaw/roll moment、
速度・yaw・ride height・姿勢、wheel/ground motion、設計可能部品、シャシー・driver・
タイヤ等の禁止領域、root/取付、製造最小寸法、CFD時間予算である。これはP8でbaselineを
資格化した後に確定し、現在の診断式や単純fixtureへ遡及的に適用しない。

## Go / No-Go / Stopの共通規則

| 判定 | 意味 | 次の動作 |
| --- | --- | --- |
| `GO` | 当該gateの全条件とartifactが揃った | 依存する次パッケージへ進む。`phase_plan.md`のstatus更新は別PRで行う |
| `NO-GO` | 現条件では物理・意味・再現性を主張できない | 次段階へ進まず、失敗artifactを保存し原因を限定する。必要なら実装を捨てて作り直す |
| `STOP: stalled` | trust region、予算、solver、meshなどが規定回数で進まない | 最後のaccepted stateを保持し、再開可能なcheckpointで停止する |
| `INCONCLUSIVE` | 改善がnoise/mesh uncertaintyより小さく判定不能 | 閾値を緩めず、格子、摂動、収束、応答定義を再評価する |

全パッケージ共通の即時No-Go条件は、ProblemSpec/hash不一致、未対応responseの黙殺、
非有限値、必要artifact欠落、solver収束不明、hard constraint違反、再現不能なseed、
または結果を見た後の閾値変更である。

### 最小閉ループの正式な終了条件

`CLOSED_LOOP_PASS`は、次を全て満たした時だけ発行する。

- P0 semantic bindingと3方向以上のFD/adjoint gate。
- 可行baseline、または明示的restorationでの可行化。
- Stage Tで3 accepted+revalidated step。
- 1 oversize candidateのrejectとrollback。
- accepted stepのtrust ratioが`0.5--2.0`、hard constraint違反ゼロ。
- T5候補からSDF、surface、Stage Vまで同じcandidate lineageとhash。
- Stage Vの三格子比較で改善または、改善不能の理由が定義済み判定に入る。
- checkpointからの再現と、固定した時間・メモリ予算内の完走。

可行性を維持したまま相対objective改善が`1e-3`未満で2回連続、またはnormalized
projected-gradientのinf-normが`1e-3`以下なら`OPTIMIZATION_STOP`とする。これは失敗ではなく、
停止理由付きの最適化終了である。semantic/hash failure、勾配gateの反復失敗、3回連続
reject、restorationの3回連続無改善、native V再評価未完、予算超過は`NO_GO`または
`budget_exhausted`として記録する。

## 成果物と保存方針

各candidateは、少なくとも次の関係を持つ。

```text
problem_spec_sha256
  -> baseline_id
      -> candidate_id
          -> rho / sensitivity / predicted response
          -> handoff surface / SDF
          -> Stage V cases / actual response
          -> accept or reject decision
          -> checkpoint / parent candidate
```

保存するものは、入力ProblemSpec snapshot、solver/compiler manifest、primal/adjoint summary、
field hash、gradient validation、candidate delta、cheap constraint report、handoff fidelity、
Stage Vの三格子結果、accept/reject理由、時間・メモリ、実行環境である。大容量VTKやcaseは
Gitへ無理に入れず、`work/`等の保存先とSHA-256を機械可読summaryへ残す。

失敗candidateも削除せず、次のcandidateを汚染しないread-only diagnosticとして保存する。
最良解、accepted state、未確定診断を同じディレクトリや同じsummaryへ混在させない。

## 既存資産の扱い — 再利用義務はなく、証拠は消さない

今回の方針では、既存コードを残すこと自体を目的にしない。新しいProblemSpec、artifact
lineage、G3/G4 gateに合わない実装は、置き換え、統合、または削除してよい。特に、古い
adapter、point-data専用経路、benchmark固有の分岐、意味が曖昧なwrapperを、互換性のために
無期限で維持しない。

ただし、実装を捨てることと、得られた証拠を消すことは分ける。

| 区分 | 扱い |
| --- | --- |
| authoritative docs | `phase_plan.md`、`problem_contract_v2.md`、`fixed_grid_data_contract_v2.md`、backend decisionは勝手に書き換えず、矛盾修正は専用PRで行う |
| current implementation | 新契約で不要なら大胆に削除・再設計する。削除PRに後継artifact/CLIと移行理由を含める |
| legacy compatibility | v1 readerなど、過去artifactを読むために必要なものだけ短期のread-only層として残す。新規実行の依存にしない |
| historical evidence | 2026-09-10 spikeのJSON、log、VTK、case、hash、結論は履歴証拠として保持する。新設計の成功に格上げしない |
| generated work | 大容量生成物はGit外に置けるが、保存場所、hash、ProblemSpec、commit、再実行手順を残す |
| obsolete tests/templates | 新contractのfixtureで置換できたら削除してよい。古い挙動を守るためだけのテストは残さない |

削除・置換の前に、対象の利用箇所を`rg`で確認し、後継経路がcanonical fixtureを通ることを
確認する。履歴証拠を移動・圧縮する場合はhashと保存場所を更新する。未分類のファイルを
まとめて消すことはしないが、分類後に不要と判断した実装を温存する理由もない。

## ブランチとPRの順序

リポジトリの [git branching strategy](git_branching_strategy.md) に従い、`main`を唯一の
長期ブランチとする。各PRは一つの判定可能なgateを閉じ、solver/Dockerの重い証拠は通常の
Python CIと分けて報告する。実装PRを大きなP0--P8一括変更にしない。

| 順序 | ブランチ例 | PRの責務 | merge条件 |
| --- | --- | --- | --- |
| 0 | `feat/minimal-tv-closed-loop` | この実行計画とP1 handoff capabilityの最小基盤、P0の統合方針 | 文書レビュー、focused test、実T1/T5 artifactの診断結果を確認 |
| 1 | `feat/p0-semantic-binding` | P0のcanonical fixture、response/unit/sign、grid mapping、native binding、FD gate | contractとnumerical gateのartifactが再現可能 |
| 2 | `feat/p1-rho-sdf-handoff` | T5 cell-data `rho`、iso-surface、SDF、fidelity report | fail-closed handoff fixtureがpass |
| 3 | `feat/p2-stage-v-audit` | baseline/small candidateのbody-fitted三格子監査 | cross-fidelity gateがpass、またはNo-Go理由がartifact化 |
| 4 | `feat/p3-trust-region-loop` | feasible seed/restoration、accept/reject、rollback、checkpoint | 3 accepted + 1 rejectの再現 |
| 5 | `feat/p4-g3-benchmarks-b0-b2` | G3完全化、B0--B2 fixtureと受入レポート | G3とB0--B2がpass |
| 6 | `feat/p5-production-stage-t` | generic derivatives、connectivity、filter chain、GCMMA-equivalent | 実solver再評価付きproduction loop |
| 7 | `feat/p6-stage-s-v-qualification` | SDF refinement、B3--B5、Stage V三格子資格 | target physics/cross-fidelity gate |
| 8 | `feat/p7-cross-platform-backend` | Mac/Windows、CUDA/Metal候補のend-to-end比較 | 同品質で時間・メモリ優位性を実測 |
| 9 | `feat/p8-fsae-profile` | 全車baseline、運転条件、目的・制約、段階導入 | FSAE entry conditionsを全てpass |

各feature branchは最新`main`から作り、長期化したらrebaseまたはmergeで追従する。
PRには、変更したcontract、実行コマンド、artifact path/hash、証拠クラス、Go/No-Go判定、
未達を記載する。P0の文書PRをmergeすることはP0実装のGoを意味しない。

## 最初に着手する実装スライス — P0からP2

最初のスライスでは、production optimizer、GCMMAの調整、CUDA/Metal、AMR、FSAE全車形状を
増やさない。回答すべき問いを次に固定する。

> Stage Tの小さな改善方向が、同じcandidateとしてsurface/SDFへ変換され、独立した
> body-fitted CFDでも改善方向として残るか。

実装順は次の通りである。

1. **P0:** 8192セルfixtureの意味論を再bindする。現行診断結果を上書きせず、可行baselineを
   持つ`minimal_loop` profileを定義する。response units、`Aref/Uref`、符号、rho chain、
   grid mapping、topology values、FD sweepを一つのmanifestで再現する。
2. **P1:** T5のcell-centered `rho`を受け取るfail-closed bridgeを作る。iso-surface、STL、
   SDF、再voxelization、fidelity report、geometry role、hashを出す。変換後のvolume、
   surface、component/root、hard-mask、feature survivalを判定する。
3. **P2:** P0のbaselineとT5 small-step candidateを同じStage V設定で実行する。まずmedium、
   次にcoarse/medium/fineへ広げ、pressure/skin friction/total force、mesh quality、
   mass balance、cross-fidelity指標を保存する。

P2の候補がVで悪化する場合は、P3へ進んでstepを増やさず、どのbridgeまたは物理意味が
   反転原因かを分類する。P2が通った後にP3のtrust-region閉ループへ進み、P4でG3/G4を
   完全化してからproduction Stage Tへ昇格する。

### 2026-09-11の実装状態

このブランチでは、P1の基盤として次を実装した。

- Stage Tのcell-data `rho`、`rho_filtered`、`rho_projected`から、補間方法とiso値を明示して
  watertight STLと符号付き距離場を生成するhandoff CLI。
- source topology/densityの固定コピー、再voxel化density、geometry binding、入出力hash、格子、
  mask、component、rootの可用性、体積差、SDF符号を記録する自己完結manifest。
- 既存成果物を上書きしないcandidate固有のimmutable output。変換の実行成功とStage S投入資格を
  `ok`と`ready_for_stage_s`に分離し、未実装の資格gateがある間は後者をfalseに固定する。

P0は既存の`openfoam_native_artifacts.py`にあるnative v2 binding/readinessを唯一の基盤として
進める。検討中に作成した別のsemantic validatorは、既存実装と責務が重複し、実solver
artifactへ結合されていなかったため採用しなかった。Stage Vの実artifact形式ができた時点で、
既存native bindingへT/V共通情報を追加し、二つの意味体系を作らない。

P0の第一スライスでは、solver artifactの意味論とは別の候補系譜として、Stage Tの
topology/densityをProblemSpec snapshot、canonical grid、STL由来mask、candidate ID、exact hashへ
結ぶ`stage_t_candidate_binding.json`を追加した。これはnative response/unit/rho-gradient bindingを
置き換えない。さらに既存の単発FD結果を、同一目的の2方向×4 epsilonとして集約するgateを
追加した。旧T3を入力した実判定は、目的混在、coverage不足、`1e-2`での数値失敗、lineage・
clipping・noise floor不足により`fail`であり、P0完了には昇格していない。
candidate bindingはtopology state自身のproblem/candidate lineageを必須とし、gradient gateは
各direction-suite行へ同一candidate binding hashを要求する。legacy artifactへ後付けのIDを
宣言するだけでは資格化しない。

P0の第二スライスでは、検証済みcanonical candidateの選択rho配列からuniform Cartesian
OpenFOAM source gridへ`rho_source = P @ rho_target`で写す片道artifactを追加した。target/sourceの
origin、spacing、shape、cell order、grid hashを別々に固定し、両grid domainの完全被覆を必須とする。
artifactは`status=capability_only`、`qualified=false`であり、rho-to-alpha/Brinkmanのsolver field
変換はcase compilerの未実装責務として残す。さらに、OpenFOAM global label順とsource gridの
x-fastest順は同一と仮定せず、明示的なpermutation artifactをstate投入と`P.T` gradient returnの
両方で使う。direction suiteは検証済みcandidate bindingを
plus/minus topology stateへ伝播し、集約gateは両state内のbinding一致とfile hashを検証する。
詳細は`p0_canonical_transfer_2026_09.md`を参照する。

これはP0/P1の完了ではない。2026-09-10の8192セルT1候補は、補間後densityの最大値が
iso値0.5と等しいため、閉じた等値面を持たない入力として変換前に拒否された。T5候補を
実際に変換すると、STL/SDFの
生成自体は完走したが、cell threshold体積と抽出surface体積の相対差は約1.0で、root
connectivityは入力artifactに存在しなかった。そのためmanifestは
`status=diagnostic_only`、`ready_for_stage_s=false`とし、Stage Vへ投入可能な候補には
昇格させない。P1の次作業は、事前固定した体積・surface distance・minimum-feature・
self-intersection・root gateを実装し、可行なcanonical seedでpass artifactを作ることである。

## 進捗の記録方法

`phase_plan.md`のcurrent positionを更新する場合は、実装PRとは分けてもよいが、必ず対応
するartifactとgateをリンクする。「実装済み」「実行可能」「数値pass」「target physics
pass」「benchmark pass」を同じ語で表現しない。

各パッケージの完了時には、次の短い記録を残す。

```text
package: P?
gate: G? / E?
status: GO | NO-GO | STOP | INCONCLUSIVE
problem_spec_sha256: ...
commit: ...
evidence_class: ...
artifacts: ...
reproduction: ...
known_limits: ...
next_action: ...
```

この記録を積み上げ、最後にFSAE全車baselineへ入る。FSAEの最終的な設計自由度や目的を
先に決めて、未資格の経路へ問題を押し込むことはしない。
