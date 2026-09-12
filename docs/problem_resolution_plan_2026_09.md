# 問題解決計画 — Stage T/S/V アーキテクチャの再資格化

- 作成日: 2026-09-12
- 対象: `docs/problem_register_2026_09.md` で整理された P1–P10
- 用途: 実装担当（Claudeを含む）へ渡す、具体的な修正・検証指示

## 1. 結論

採用済みの全体構成、すなわち

```text
密度/Brinkmanでトポロジーを生成
    -> SDFで境界を明示化・形状改善
    -> body-fitted OpenFOAMで独立検証
```

は、現時点で捨てる必要はない。ただし、代理モデルの順位保存は未資格であり、現在の
否定的な順位結果だけから Brinkman 方式全体を棄却することも、二値化した最新実行から
成立を主張することもできない。

`problem_register_2026_09.md` は「主な未分離因子は二値化と Stage T 解像度」と読む
限り妥当である。しかし「原因候補は2つに絞れた」という記述は強すぎる。少なくとも
次の因子がまだ混ざっている。

1. 灰色密度と中実STLの物理的不一致
2. Stage T の格子解像度と、46,080セル設計場から8,192セル流体格子への平均化
3. Brinkman係数 `betaMax` の有限値・格子依存性
4. cell-to-point変換、等値面抽出、再voxel化による形状差
5. Stage V のmesh-quality失敗、solver収束未判定、downforceの格子未収束
6. 応答名、随伴収束、候補provenance、射影所有者に残る実装契約違反

特に6は、順位検定とは別に、最新の最適化履歴を科学的証拠として無効にする。したがって
**二値化ループを先に長く回すのではなく、契約修復を最優先にする。** 修復後、既知形状を
固定した実験で1因子ずつ分離し、最後にだけ最適化を再開する。

## 2. 現時点で保持するもの

次の判断と資産は保持する。

- `ProblemSpec -> canonical artifact -> Stage T -> Stage S -> Stage V` の制御面
- topology birth は density/Brinkman、連続形状改善は SDF、最終判定は body-fitted
  OpenFOAM とする役割分担
- OpenFOAM native ISQP は使わず、Python側に最適化器を置く判断
- Stage T と Stage V の絶対値一致ではなく、候補の改善方向・順位保存を採用条件にする判断
- 否定的結果を含む既存artifact。過去の実行は上書きせず、診断資料として残す
- 既存の canonical transfer、cell-order実測、符号規約、T→S→Vのlineage

次の挙動は停止する。

- `adjoint_iterations=1` の結果を設計勾配として使う
- `drag` と宣言しながら `topOSensdownforce` を渡す
- 新しい候補NPZへ初期候補のprovenanceを流用する
- 射影係数 `b` を変えた直後に、前の `b` の目的値・勾配と比較する
- raw `rho` の平均を、物理的な投影後体積の代用として制約する
- Stage TではOpenFOAM正則化後の場を解き、Stage SではPython射影場を輪郭化する
- 最適化で生じた別形状を使って、解像度や射影の効果を同時に比較する

## 3. 最優先の正しさ修復

### C0. 随伴計算を収束させ、未収束勾配をfail-closedにする

#### 現在の問題

`scripts/stage_t_python_loop.py::_run_case` は `adjoint_iterations=1` を渡す。
`src/cfd_sdf/fixed_grid_primal.py::_patch_optimisation_dict` はテンプレート内の
`nIters 4000;` を `nIters 1;` に置換する。実生成ケースでも drag/downforce の両随伴が
1反復で終了している。一方、ループの `_extract` は `primal_converged` と目的値の有限性
しか確認せず、その後 `topOSens` を消費する。

初回のP0勾配は随伴713/1143反復で収束していたが、最初の受理ステップ以降の勾配は
同じ資格を持たない。この欠陥は既存の固定候補順位評価を説明するものではないが、
最適化軌跡と最新候補を証拠として使えなくする。

#### 実装

1. API引数を次の二つへ分離する。
   - `topology_cycles`: 設計更新の回数
   - `adjoint_max_iterations`: 各随伴ソルバの最大反復数
2. `optimisationDict` の書換えを、値 `4000` の一括置換ではなく、対象辞書パスと
   solver IDを指定する構造化パッチへ変更する。
3. 既定値はテンプレートの2000/4000相当を保持する。診断で1反復を使う場合は
   `audit_only=true` をartifactに記録し、gradient exportを禁止する。
4. 目的応答に対応する随伴について次をすべて要求する。
   - 終了ログに収束マーカーがある
   - 最終残差が事前閾値以下
   - `topOSens` が要求した最終timeに存在する
   - 配列が有限でセル数が一致する
5. 一つでも失敗したら候補の目的値は診断用に記録してよいが、勾配更新・受理・次反復を
   禁止する。

#### テスト

- `adjoint_max_iterations` が2つの随伴辞書だけへ正しく入る
- primalの `nIters` や無関係な辞書値は変わらない
- primal収束・adjoint未収束なら gradient export が失敗する
- 指定応答の随伴だけが未収束でも受理されない
- 収束ログと出力場を改変するmutation testが失敗する

### C1. ProblemSpec応答とOpenFOAM随伴を意味的に束縛する

#### 現在の問題

P0の `work/p0_closed_loop/project.yaml` は `drag` 応答しか宣言していない。一方、ループは
`ADJOINT_SOLVER_ID="downforce"` で再構成した `topOSensdownforce` を
`RESPONSE_ID="drag"` として転送する。現行ガードは「response_idがProblemSpecに存在する」
ことしか確認せず、方向・符号・OpenFOAM objective・adjoint solverとの対応を検証しない。
provenanceにも `problem_spec_response_id: drag`、`openfoam_adjoint_solver_id: null` が残る。

#### 実装

1. 対象fixtureのProblemSpecに `downforce` 応答を明示する。
   - force direction: `[0, 0, -1]`
   - objective sense: `maximize`
   - 単位、`Aref`、`rho_ref`、`U_ref` を明記
2. case compilerが次のbinding artifactを生成する。

```json
{
  "problem_spec_response_id": "downforce",
  "flow_case_id": "...",
  "physical_direction": [0, 0, -1],
  "objective_sense": "maximize",
  "canonical_objective_sign": -1,
  "openfoam_objective_name": "downforce",
  "openfoam_adjoint_solver_id": "downforce",
  "units": "N or dimensionless coefficient",
  "problem_spec_sha256": "..."
}
```

3. field reconstructionは実際に指定・検出した `adjoint_solver_id` をprovenanceへ必ず書く。
4. canonical transferは上の全項目と入力artifactのhash一致を検証する。
5. `response_id=drag` と `topOSensdownforce` の組合せを明示的に拒否する。
6. 修正後のspecで、符号を含むP0有限差分試験を再実行する。旧artifactは削除せず
   `pre-semantic-binding diagnostic` として扱う。

### C2. 候補ごとに真正なprovenanceを作る

#### 現在の問題

二値化ループは各試行で新しい `source_state.npz` を書くが、注入時に
`work/p0_closed_loop/source_state/provenance.json` を毎回渡す。注入器はkindとgrid identityを
検査する一方、provenance内のartifact SHA-256と実NPZ、配列hash、candidate bindingの一致を
検査しない。そのため内容の違う候補が初期候補のlineageとして受理される。

#### 実装

1. optimizerから注入器へ任意の「NPZと別provenance」を渡すAPIを廃止するか、少なくとも
   完全一致を必須にする。
2. 各trial candidateについてcanonical candidate artifactを先に作る。
3. canonical-to-source transfer APIで、その候補固有の次を一度に出力する。
   - NPZ file hash
   - exported array hash、dtype、shape、cell order
   - canonical candidate ID/hash
   - source/target grid hash
   - transfer matrix hash
   - projection/filter profile hash
4. injectionはNPZ file hashとarray hashを再計算し、provenanceと照合する。
5. 注入後のtopology stateには新しいcandidate IDとparent hashを記録し、`rho`、
   `rho_filtered`、`rho_projected`、`alpha`を同一世代として書く。
6. candidateを受理しなかった場合もtrial artifactはimmutableに残し、`rejected` と理由を
   manifestに書く。

#### テスト

- NPZを1 byte変更すると拒否
- 別候補のprovenanceへ差し替えると拒否
- 配列のdtype/shape/orderを変えると拒否
- gridが同じでもcandidate hashが違えば拒否
- 注入後4配列が同じ世代の値・hashを持つ

### C3. 射影・フィルタの所有者をPythonに一本化する

#### 現在の問題

現案はPythonで `beta=H_b(rho)` を作るが、OpenFOAMケース側は
`regularise true; function linear;` のままである。実際の評価鎖は概ね次になる。

```text
canonical rho
 -> Python tanh projection beta
 -> conservative averaging P
 -> OpenFOAM raw alpha
 -> OpenFOAM Helmholtz regularisation alphaTilda
 -> OpenFOAM beta
 -> Brinkman alphaMax * beta
```

Stage SはPython側の `rho_projected` を輪郭化するため、Stage Tが実際に流れ場へ使った
OpenFOAM正則化後のbetaと同一ではない。また、随伴が返す感度の独立変数がraw alphaか
solver betaかを契約で明記しないまま、Pythonの `d beta / d rho` を追加している。

#### 推奨する一本化

Pythonを唯一の設計正則化所有者にする。

```text
rho --H--> rho_tilde --h_b--> beta_target --P--> beta_source -> OpenFOAM
```

- `H`: mask-aware、体積重み付き、正規化された密度フィルタ
- `h_b`: tanh Heaviside射影
- `P`: 保存的なtarget-to-source transfer
- OpenFOAM: `regularise false`、`function linear`
- Stage S: solver評価に使ったものと同じ `beta_target` をcontourする

勾配鎖を次で固定する。

```text
g_beta_target = P.T @ g_beta_source
g_rho = H.T @ (h_b'(rho_tilde) * g_beta_target)
```

`H` が正規化演算を含む場合は、その正確なtranspose作用を実装する。最小診断では
`H=I` として射影だけを検証してよい。production optimizerへ進む前に明示的な `H` を入れる。

OpenFOAM側を所有者とする案は、solver内の実betaを再構成し、その状態をcanonical gridへ
戻す別の状態転送を必要とする。現行の `P.T` は勾配のpullbackであり状態の逆写像ではない。
実装量と曖昧さが増えるため採用しない。

### C4. continuationを同一問題間の更新として実装する

#### 現在の問題

初期 `current_J` と勾配は `beta=rho` の既存P0から来るが、最初のcandidateは `b=1` の
射影場で評価される。`b` を上げる反復でも、現在値・勾配は前の `b` のままである。
したがって `actual_delta_J` には設計更新と射影関数変更が混ざり、一次予測との比較や
Armijo判定は数学的に成立しない。move limitをリセットしても解決しない。

#### 実装

1. 各 `b` を一つの固定された最適化問題として扱う。
2. `b` が変わったら `rho` を固定し、新しい `b` の `beta` を作る。
3. その状態でprimalと対応随伴を収束させ、`J_b(rho)` と `g_b(rho)` を新baselineにする。
4. このbaseline評価を continuation transition として別行に記録し、設計改善量に数えない。
5. 同じ `b` のbaselineからだけcandidateの予測量・実測量を比較する。
6. `b` は固定反復数ではなく、現在の `b` で次を満たしたときに上げる。
   - KKT/投影勾配ノルムが閾値以下、または改善がplateau
   - 物理体積制約が許容内
   - primal/adjointがすべて収束
7. 棄却反復はcontinuation回数を進めない。
8. `b` 上昇で目的が悪化しても、それをline search rejectionとはしない。新問題のbaseline
   として記録し、必要なら一段前の `b` へ戻す。

### C5. 物理体積を制約し、制約付きsubproblemを解く

#### 現在の問題

現ループはactive cellのraw `rho` 平均を目標へ合わせる。実際の固体体積は
`beta=h_b(Hrho)` のセル体積積分であり、continuation中は両者が大きく異なる。
さらにOC更新は目的勾配だけで乗数探索し、物理体積の導関数を使っていない。

#### 実装

ProblemSpecで体積の定義を固定する。

```text
V(beta) = sum_i(cell_volume_i * beta_i) / sum_i(cell_volume_i)
```

導関数は

```text
dV/drho = H.T @ (cell_volume_weight * h_b'(rho_tilde))
```

である。更新には既存依存のSciPyを用いたSLSQP、または既存の
`fixed_grid_optimizer` の制約付きsubproblemを使う。新しいQP実装は作らない。各局所問題は
最低限、次を含む。

```text
minimize   g_J^T delta + 0.5 * lambda_reg * ||delta||^2
subject to V(beta) + g_V^T delta <= V_limit
           lower <= rho + delta <= upper
           |delta| <= trust_radius
           fixed/forbidden cells: delta = 0
```

非線形な実制約はcandidate生成後に再計算し、許容外ならCFDを回す前に棄却または再投影する。
CFD実評価後の受理には次を要求する。

- primal/adjoint convergence
- 実物理体積が許容内
- 目的改善がsolver repeatability/noise marginを超える
- actual/predicted reduction ratioが事前範囲内

`actual_delta_J <= 1e-9` だけで同値または数値no-opを受理しない。ratioに応じてtrust radiusを
拡大・縮小する。

### C6. design gridとsolver gridの実現可能性を一致させる

#### 現在の問題

設計・Stage Sの `beta_target` は46,080セル、Stage T solverが見るのは8,192セルの
`P @ beta_target` である。`P` のnullspaceに入る細部はStage Tから不可視だが、Stage Sでは
実形状になる。同じsource平均を持つ多数の高解像度形状を、Stage Tは区別できない。

#### P0で採用する解決

再資格化では **design grid、Stage T grid、handoff fieldを同一格子にする。** まず
`T1=60x32x24=46,080`セルで同じbinary fieldを直接評価し、46k→8k転送を外す。

メモリ・計算量が問題なら、design variableをsource grid上の `z_source` とし、明示的な
prolongation `Q` で `beta_target=Q z_source` を作る。`P.T` を状態の逆写像として使っては
ならない。

同一格子で順位保存が成立した後にだけ、46k→8k transferを一因子として再導入する。

### C7. Stage Vを独立基準として資格化する

#### 現在の問題

既存のbody-fitted A/B各3格子、計6ケースはすべて `checkMesh` が1項目失敗している。
原因はconcave cellであり、件数は次のとおりである。

| 候補 | coarse | medium | fine |
| --- | ---: | ---: | ---: |
| A | 285 | 641 | 2504 |
| B | 258 | 503 | 2438 |

さらに生成ケースの `simpleFoam` は収束条件を持たず、ログには
`no convergence criteria found. Calculations will run for 500 steps.` と出る。したがって
既存証拠が示すのは「6ケースが完走してforce fileを生成した」ことまでであり、meshが有効、
solverが収束、forceが格子独立、Stage Vが決定的な参照値、とはまだ言えない。

dragの順位反転が3格子で一貫する事実は重要な否定的観測として保持する。ただし、
reference-side numerical errorを修復または上限評価するまで、一般的なsurrogate No-Goへ
昇格させない。

#### 実装

1. `checkMesh -allGeometry -allTopology` をStage Vのhard gateにする。
2. 既定はfailed mesh checksが0。snappyHexMeshでconcavityを完全除去できない場合は、結果を
   見る前に許容件数・severityをprofileで定義する。
3. mesh cleanup/remeshing前後で各force coefficientの差が許容内、かつ順位が不変であることを
   示す。示せなければそのmeshを参照値に使わない。
4. `residualControl` 等の明示的収束条件を設定し、固定反復完走を収束と呼ばない。
5. pressure/velocity残差、continuity error、force最終windowの平均・標準偏差・傾き、反復数、
   termination reason、`checkMesh` 全要約をartifactへ保存する。
6. 最後の2格子でdrag/downforceの変化が事前閾値内になるまでrefineする。downforceが
   非単調またはゼロ近傍なら、relative toleranceだけでなくabsolute `Q_scale` を使う。

#### テスト

- `checkMesh` が1項目でも失敗したrunはqualification reportがfailになる
- 500反復完走だけでは `solver_converged=true` にならない
- force historyが最終windowでdriftするrunはfailになる
- invalid meshを含むcandidateはranking集計から除外される

## 4. 問題台帳の表現を直す箇所

台帳の観測値は有用だが、Claudeが実装時に誤った因果を固定しないよう、次の表現として扱う。

| 台帳の表現 | 採用する表現 |
| --- | --- |
| 原因候補は2つに絞れた | 二値化とStage T解像度が主要仮説。penalty、抽出、Stage V品質、force functionalも未分離 |
| `function linear`なので構造的に0/1へ向かわない | sharpeningを無効にする欠陥であり寄与原因。ただし変数が0.5を越えることを数学的に禁止はしない |
| 勾配と宣言応答はガード済み | response membershipのみガード済み。solver/direction/sign/unitsの意味的bindingは未修正 |
| 正則化を無効化すると悪化したので連鎖律欠落は棄却 | forward problem自体も変わる交絡試験。正則化transposeの因果的棄却にはならない |
| native ISQPの方向が非降下 | line-search失敗は観測済み。方向そのものの非降下を断定するにはdirectional derivativeが必要 |
| Stage V三格子で検証した | 三格子を実行した。全meshにfailed checkがあり、solver/force収束も未資格 |

P4bの体積制約不能、P2の候補非二値、P4eの宣言条件不一致、P7のstale field、P8のno-op、
P9の境界成分は強い根拠がある。P3、P5の機構、P6の原因は仮説として残す。

## 5. handoff gateの修正

現行の `M_nd <= 0.01` と `max(beta) >= 0.9` は暫定診断には使えるが、ソース定数として
事後的に固定してはいけない。また `max(beta)` は1セルだけ0.9を超えても通る。

閾値と定義をProblemSpecまたはversion付きqualification profileへ移し、run開始前にhash固定
する。最低限、次を報告する。

- global discreteness: `mean(4 beta (1-beta))`
- material-normalized grayness:
  `sum(4 beta (1-beta)) / max(sum(beta), eps)`
- `0.1 < beta < 0.9` のセル数と物理体積
- `beta >= 0.9` のセル数・体積・最大連結成分比
- 固体体積、component数、root接続
- 最小厚さ、最小gap、禁止領域侵入
- contour後のwatertightness、degenerate/self-intersection
- 元betaとSTL再voxel化のIoU、体積差、centroid差、Hausdorff/Chamfer距離

`max(beta)` はレポート値として残してよいが、単独の合否条件にはしない。FSAEへ進む前には
最小厚さ・root・component条件を物理寸法で定義する。

qualification modeではactive maskを必須にし、mask欠落時に全domainへfallbackしない。
optimizerはroot cellを設計更新から除外するか `beta=1` へhard pinし、各candidateの受理前に
root connectivityと禁止領域侵入を検査する。Stage Sのconsumerは単なる `ok=true` ではなく、
`ready_for_stage_s=true` と全hard gateの通過を要求する。

## 6. アーキテクチャを判定する最小実験

### 6.1 共通条件を固定する

最初の再資格化は低Re層流の縮約問題に限定し、次を全実験で固定する。

- `U = (1,0,0) m/s`
- `rho_fluid = 1`
- `nu = 0.01 m^2/s`
- `Aref = 0.64 m^2`
- `lRef = 0.8 m`
- laminar
- drag direction `+X`
- downforce direction `-Z`
- OpenFOAM v2512 / container digest
- boundary conditionsと数値scheme
- mask、設計領域、force normalization
- candidate、field、grid、transfer matrix、STLのSHA-256

これらを一つのexperiment manifestへ書き、各runはそのhashを参照する。FSAEの
`Re ~ O(10^6)` と乱流・地面・回転輪はこの資格化が通ってから別phaseで導入する。

### 6.2 optimizerを使わない固定形状を用意する

A/Bの2候補だけでは一つのpair signしか得られず、順位相関を評価できない。次の二段階にする。

1. **最短診断:** 既存A/Bのraw `rho`を固定し、linearとHeaviside投影だけを変える。
2. **資格化:** 解析的に定義できる8候補以上のbinary geometryを用意する。厚さ、迎角、camber、
   gapなどを一軸ずつ変え、期待順位を仮定せず両fidelityで測る。

解析形状から高解像度anchor STLとbinary occupancyを同時生成し、どちらを起点にしても同じ
geometry IDへ束縛する。これによりoptimizer pathと抽出誤差を分離できる。

### 6.3 入れ子の実験行列

完全直積は回さず、前段を通った条件だけを次へ進める。

| Block | 実験 | 固定するもの | 分離する因子 |
| --- | --- | --- | --- |
| P | A/B x `{linear, H_b}` at T0 | raw rho、grid、betaMax | 射影・二値化 |
| E | 1–2候補 x `{anchor, iso .45/.50/.55}` at V2 | density、Stage V条件 | STL抽出感度 |
| V | binary STL x `{V0,V1,V2}` | 同一STL、物理条件 | Stage V mesh error |
| T | binary field x `{T0,T1,T2}` | 同一物理形状、betaMax | Stage T resolution/transfer |
| A | 1–2候補 x `betaMax` sweep | binary shape、収束grid | penalty/Brinkman bias |
| R | 5候補以上、収束T/V | 全ての通過条件 | 順位保存 |

Stage T grid:

- `T0 = 32x16x16 = 8,192` cells（現行source）
- `T1 = 60x32x24 = 46,080` cells（現行canonical、同一格子試験）
- `T2 = 120x64x48 = 368,640` cells（各軸2倍）

Stage V grid:

- `V0`: voxel size 0.1 m
- `V1`: 0.05 m
- `V2`: 0.025 m
- `V3`: 0.0125 m。V1→V2で対象応答が未収束のときだけ追加

現在のStage V downforceはAが `0.0132 -> 0.0358 -> 0.0449`、Bが
`0.0417 -> 0.0321 -> 0.0413` と動き、V2までで収束したとは言えない。coarseだけの順位一致を
根拠にしない。

### 6.4 Brinkman penaltyを無次元量で診断する

現行値 `nu=0.01 m^2/s`、`alphaMax=2500 1/s` なら、penalization length scaleは

```text
ell_p = sqrt(nu / alphaMax) = 0.002 m
```

であり、T0のセル幅0.075–0.1 mより大幅に小さい。これは係数が悪いことの証明ではないが、
penalization layerが格子で解像されず、stiffnessや漏れ速度が格子依存になる可能性を示す。

`alphaMax = {2500, 10000, 40000}` を盲目的な正解値として採用せず、まず3点sweepとして使う。
各点で次を記録する。

- `Da = nu / (alphaMax L^2)`
- cell-scale `chi = alphaMax Delta^2 / nu`
- solid領域内の速度漏れ `||U||/U_ref` の平均・最大・95 percentile
- force、mass balance、momentum balance
- primal/adjoint残差と反復数
- grid refinementに対するforceと順位の安定性

alphaMaxを上げて漏れは減るが収束性と格子依存が悪化する場合、最大値を選ぶのではなく、
事前の漏れ・収束・順位基準を同時に満たす範囲を選ぶ。満たす範囲がなければ、そのgridで
Brinkman surrogateはNo-Goである。

### 6.5 forceの違いを記録する

Stage Tはporous reactionの体積積分、Stage Vはpressureとviscous tractionの表面積分である。
絶対値は機械的に一致しない。各runで次を別々に保存する。

- Stage T porous reaction force
- control-volume momentum balance
- Stage V pressure force
- Stage V viscous force
- Stage V total force
- 共通のdimensionless coefficient

同一geometry・物理条件・格子収束・penalty収束を確認した後に順位を比較する。

## 7. GateとStop/Go基準

閾値は結果を見て調整せず、experiment manifestに事前登録する。以下はP0向け暫定値であり、
本番FSAEの基準ではない。

### Gate 0 — contract integrity

すべて必須。

- ProblemSpec response、force direction、sign、adjoint solverが完全一致
- candidate/NPZ/array/grid/transfer/projection hashが一致
- primalと要求随伴が収束
- field order、shape、dtype、finite、cell countが一致

失敗時はそのrunを診断用として保存し、設計更新とランキングへ使わない。

### Gate 1 — binary/handoff integrity

- version付きdiscreteness profileを通過
- mask/root/component/minimum-featureを通過
- anchorとの体積差・表面差・Hausdorffが事前閾値内
- 再voxel化IoUとforceのiso-threshold感度が事前閾値内

anchorがない場合、E blockは「抽出感度の上限」だけを与え、Brinkman biasと断定しない。

### Gate 2 — Stage T numerical qualification

- T1→T2の各対象応答変化が暫定2%以内、または事前absolute tolerance以内
- A/Bまたは資格化候補のpair signがT grid間で安定
- solid leakage、mass/momentum balance、solver convergenceが閾値内
- alphaMax sweepで選択範囲が存在する

2%はscaleが十分な応答にだけ使う。ゼロ近傍のdownforceには事前に `Q_scale` とabsolute
toleranceを固定する。

### Gate 3 — Stage V numerical qualification

- V1→V2が許容内。未達ならV3を追加
- pressure/viscous/totalの各成分とpair signが安定
- checkMesh、mass balance、residual gateを通過

### Gate 4 — cross-fidelity ranking

最短診断ではA/Bのpair signを使う。正式資格化では8候補以上についてSpearman rho、
Kendall tau、全事前指定pairの改善符号を報告する。

候補 `b` から `c` へのfine-fidelity改善量と不確かさを、例えば次で定義する。

```text
I_f = (J_b,f - J_c,f) / max(abs(J_b,f), J_scale)
S_b = abs(J_b,f - J_b,m) / max(abs(J_b,f), J_scale)
S_c = abs(J_c,f - J_c,m) / max(abs(J_b,f), J_scale)
```

抽出感度 `S_extraction` も含め、暫定的に

```text
I_f > 2 * max(S_b, S_c, S_extraction)
```

を「改善を解像できた」条件とする。`J_scale` は実験前に固定する。

- 同符号かつ差が不確かさを超える: ranking pass
- 差が不確かさ内: unresolved。passと数えない
- binary・T/V収束・抽出制御後も反転: その応答についてBrinkman surrogate No-Go

同一格子のbinary形状でもNo-Goなら、transferやoptimizerを改良しても救えない。Stage Tを
別surrogateへ置換する判断へ進む。passならtransfer、filter、optimizerを一つずつ戻す。

## 8. 勾配検証の再設計

P6の約10%バイアスを次の順に分離する。

1. source=targetの同一格子、`P=I`、`H=I`、固定 `b` でFD
2. 同一格子、`H` とHeavisideを有効化してFD
3. 整数比のnested grid transferでFD
4. 現行の非整数比overlap transferでFD

各段で勾配方向に加え、少なくとも2つのseedのrandom direction、4段階のepsilonを使う。
mask・boundsでclipした後の実perturbationを用いて方向を再正規化する。制約で固定されたセルは
方向から除く。

これで同一格子から失敗するならsolver/regularisation chain、整数transferで初めて失敗するなら
transfer実装、非整数比で初めて失敗するならoverlap weightingを主因として切り分けられる。

## 9. 最新二値化ループの扱い

現在実行中または作業ツリー上の `scripts/stage_t_binarized_loop.py` は、次の考え方を実証する
diagnostic prototypeとして残す。

- tanh射影と導関数
- move limitのfloor
- no-op拒否
- projected fieldをhandoff対象にする

ただし次の理由により、その最終形状・目的改善・cross-fidelity結果を資格化証拠にしない。

- 反復後の随伴が1反復
- response bindingが `drag` / `downforce` で不一致
- 候補provenanceが初期状態から流用
- Python射影とOpenFOAM regularisationが二重
- `b` 遷移時のbaselineが未再評価
- raw rho体積を制約
- target design gridの形状がsource solver gridで一意に見えない

runは最後まで保存してよい。結果manifestに
`qualification_status: diagnostic_only_not_eligible` と理由一覧を残す。途中artifactを削除せず、
修正後runと同じrun IDを使わない。

2026-09-12の24 outer-iteration実行は完了し、85 trial中5件を受理した。受理は `b=1` の3件、
`b=2` の1件、`b=4` の1件で、その後は受理できなかった。最後の受理状態は
`downforce_coefficient=2.9436`、raw体積率0.07347、projected体積率0.03730である。
projected fieldは `M_nd=0.08781`、`max(beta)=0.86377`、`beta>0.9` が0セルであり、暫定
discreteness gateにも達していない。これは「射影を入れれば直ちに二値化が成立する」という
仮説を支持しないが、上記7つの契約欠陥があるため、optimizerやアーキテクチャ自体の反証にも
使わない。

## 10. 実装順序

### Slice 1 — 証拠契約の修復

対象:

- `src/cfd_sdf/fixed_grid_primal.py`
- `src/cfd_sdf/openfoam_field_reconstruction.py`
- `src/cfd_sdf/openfoam_canonical_field_transfer.py`
- `src/cfd_sdf/fixed_grid_canonical_state_injection.py`
- ProblemSpec compiler/renderer
- 対応unit/integration tests

完了条件: C0、C1、C2のmutation testが通り、未収束随伴・response mismatch・swapped
provenanceがすべてfail-closedになる。

### Slice 2 — 単一の状態変換

対象:

- Python filter/projection operator
- transpose chain
- OpenFOAM caseの `regularise false` / `function linear`
- canonical stateの4配列同時更新
- fixed-b finite difference harness

完了条件: `P=I,H=I` の2方向x4 epsilonで勾配比がepsilon収束し、Stage Tが使った
`beta_target` とStage S入力のarray hashが一致する。

### Slice 3 — optimizerの数理修復

対象:

- fixed-b baseline refresh
- physical beta volume constraint
- SciPy SLSQPまたは既存constrained subproblem
- trust-region受理判定
- convergence/feasibility history

完了条件: 同一bで2ステップ以上、収束primal/adjoint、体積許容、予測/実測符号一致、
noise marginを超える改善を示す。continuationを始める前にここまで通す。

### Slice 4 — 固定形状の数値資格化

対象:

- analytic binary geometry generator
- same-grid T1/T2 evaluation driver
- extraction anchor/metrics
- V0–V3 mesh study
- alphaMax/leakage study

Stage V driverにはC7のmesh/solver/force-stationarity hard gateを組み込む。

完了条件: Gate 0–3を各候補が通り、各誤差源の大きさを別々に報告できる。

### Slice 5 — 順位資格化

対象:

- 8候補以上のpre-registered set
- cross-fidelity ranking report
- Spearman/Kendall/pair sign/uncertainty

完了条件: Gate 4のpass、unresolved、No-Goを応答ごとに判定する。passするまで
「高速CFD最適化アーキテクチャが有効」とは書かない。

### Slice 6 — transferと最適化を再導入

1. same-gridでpassしたbinary fixed geometry
2. 46k→8k transferだけ追加
3. explicit filterだけ追加
4. fixed-b optimizerだけ追加
5. continuationを追加
6. Stage S shape optimizationを追加

各段で前段と同じGateを再実行し、初めて失敗した因子を特定する。

## 11. Claudeへの具体的な実装指示

以下を上から順に実行する。一つのPRに全部を混ぜず、各sliceを独立commitにする。

1. 完了した `stage_t_binarized` runを削除・上書きしない。manifestへ
   `diagnostic_only_not_eligible` と7理由を追記する。
2. `adjoint_iterations` の意味を分割し、gradientを出すrunでは対象随伴の収束を必須にする。
3. `drag` responseで `topOSensdownforce` が通るテストを先に追加し、失敗を確認してから
   semantic bindingを実装する。
4. field reconstruction provenanceへ実 `adjoint_solver_id` を記録する。
5. 候補NPZとprovenanceのhash/candidate binding mutation testsを追加し、注入器を修復する。
6. candidate generation、state transfer、injectionを一つのimmutable artifact chainにする。
7. Python側に `H` と `h_b` を置き、OpenFOAMの正則化を無効化する。両側を同時に有効に
   しないguardを置く。
8. `b` ごとにbaseline primal/adjointを再評価し、fixed-b内だけでstepを受理する。
9. raw rho平均ではなくcell-volume weighted `V(beta)` を制約する。既存SciPy/optimizer helperを
   再利用する。
10. まずsame-grid、fixed-b、2方向x4 epsilonのFDを通す。通るまで長い最適化を回さない。
11. analytic binary geometryを8候補以上作り、geometry/occupancy/STLを同一IDとhashへ束縛する。
12. Stage Vで `checkMesh -allGeometry -allTopology`、solver residual、continuity、force
   stationarityをhard gateにする。既存6ケースをqualified referenceとして流用しない。
13. 入れ子のP/E/V/T/A/R実験を実行し、各Gateを機械判定する。
14. T1/T2でStage Tが未収束ならT3を追加する。V2でdownforce未収束ならV3を追加する。
15. binary・grid-converged・extraction-controlledでも順位が反転すれば、その応答に対する
   Brinkman Stage TをNo-Goと報告する。最適化パラメータ調整で結果を救おうとしない。
16. passした場合だけtransfer、filter、optimizer、continuationを一因子ずつ戻す。

各commitで次を必ず記録する。

- 解決する問題番号と再現条件
- 変更したcontract/schema
- 追加したfail-closed条件
- 実行コマンドとenvironment/container digest
- 入力・出力artifact hash
- 通過したtestと未実行の物理検証

## 12. 今回まだ実装しないもの

次は重要だが、Stage T再資格化の前に着手しない。

- P9のdomain-boundary component除去以外の高度なsurface cleanup
- P10のHamilton–Jacobi形状更新、再初期化、曲率制御
- 高Re FSAE全車、乱流、地面効果、回転輪、過渡流
- ML surrogateや新しいCFD backend
- 多目的Pareto探索、大規模並列探索

Stage SのP9は、fixed-shape handoff試験を妨げる範囲だけ先に直してよい。P10はStage Tの
順位保存が成立してから実装する。

## 13. 証拠として主張できる範囲

現時点で主張できる。

- T→S→Vの制御経路は実行できる
- 既存gray候補ではcross-fidelity rankingが否定的だった
- 灰色密度と中実STLの不一致は明確な交絡因子である
- native ISQPをPython側optimizerへ移す判断は妥当である
- 既存Stage V全6ケースは完走したが、mesh/solver convergence gateを通っていない

現時点で主張できない。

- 原因が二値化と格子の2件に確定した
- 最新の二値化最適化が正しい勾配で進んだ
- Brinkman surrogateが成立した、または成立しないと確定した
- Stage V downforceが格子収束した
- この縮約問題の結果がFSAE全車の高Re空力へ外挿できる

この計画の判定点は明確である。**契約を修復したsame-grid binary試験で順位が保存されるか。**
ここを通れば現在のアーキテクチャを段階的に強化する。ここで失敗すれば、Stage S/Vや
optimizerを増築する前にStage T surrogate自体を入れ替える。
