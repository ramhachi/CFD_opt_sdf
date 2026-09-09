# CFD_opt_sdf 高速化・両OS対応アーキテクチャレビュー

採用判断：本レビューの条件を反映した構成を、2026-09-09にプロジェクトの本採用アーキテクチャとした。個別バックエンドの利用可否は、ロードマップに定めた数値・物理ゲートで引き続き判定する。

2026-09-06。対象は添付提案と公開リポジトリmainのcommit fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287。XLBはcommit 9470e54a8d7ccd68d8e5563ca7a573040841ea8cも参照した。

問題設定、物理モデル、設計変数、随伴法、計算資源、移行順序を評価した。ソースの可読性の採点、ソース変更、CFD実行は行っていない。数値は既存の記録・今回の算術見積もり・未検証の目標を区別する。貼付文は等号や減号が一部欠落しているため、復元できる式は通常の定義に沿って解釈した。

**判定：方向性は有望だが、そのままのアーキテクチャ確定・全面移行には反対。既存基盤を維持した条件付き研究計画として採用する。**

対象の物理モデル、定常随伴が成立する条件、探索可能なトポロジー、随伴線形解法が未確定なのに、SDF一本化と新ソルバへの置換を先に決めている点が問題である。

## 採否

| 提案 | 判定 | 修正 |
|---|---|---|
| ProblemSpec・幾何役割・履歴追跡の再利用 | 採用 | 問題宣言と物理的な検証完了を分離 |
| 高速探索と独立した高精度評価 | 採用 | OpenFOAMを絶対的な真値とは扱わない |
| SDFを形状更新の主表現にする | 条件付き採用 | 固定トポロジーでは自然。任意トポロジーの唯一の変数にする根拠は不足 |
| density/Brinkman経路を凍結・交換 | 現時点では不採用 | 同じ精度・制約・問題で実測比較 |
| Sharp-SDF LBMを本命に確定 | 保留 | 対象Re、壁面、地面、隙間、遷移・乱流モデルを先に検証 |
| 定常implicit discrete adjoint | 条件付き採用 | 定常離散問題に限定。非定常統計量は別設計 |
| LKSからLBMへ順に開発 | 非推奨 | 初期は一つのLBM系。LKSはメモリが実測で支配した場合 |
| Augmented Lagrangianで随伴を集約 | 採用可能 | 不等式、乗数更新、複数条件の計算数を明示 |
| 静的2-level refinement | 後段で採用可能 | 単一格子の流れ・力・勾配を先に検証 |
| 簡略DWR指標 | 要修正 | 同一格子の収束残差では離散化誤差を検出できない |
| porous nucleation probe | 研究仮説として保留 | 有限サイズの固体と支持部を含めて再評価 |
| ML/POD warm start | 初期計画から外す | 直前のCFD解の再利用を基準にする |
| Mac/Windows両対応 | 採用 | 共通の物理・契約と異なる実行基盤を分離 |
| 新repoと広いAPIを初週に固定 | 非推奨 | 既存repo内の実験バックエンドから開始 |
| 6か月で3D随伴・AMR・両OS・高Reを完成 | 根拠不足 | 期間ではなく通過条件で分ける |

## 1. 元リポジトリの理解を修正する

元の目標は任意の剛体の外部空力トポロジー最適化で、フロントウイングは複雑ベンチマークである。提案は途中から翼のダウンフォース最大化へ狭くなる。これを限定プロファイルとして設けることはよいが、一般的な応答方向、複数運転条件、solid/void連結性を失ってはいけない。[元の問題設定](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/docs/phase_plan.md#L12-L29)

現行ロードマップでは、G1契約は完成、G2はcanonical domain変更後の実行再認定が必要。応答単位、密度勾配、メッシュからcanonical gridへの写像、topology値の接続も残る。G3の幾何・物理解像度ゲート、G4の包括的ベンチマークは未完成。Stage Sはhandoff prototype、Stage Vもprototypeである。「再利用できる検証基盤」と「検証済みの完成したtruth model」は区別する。[現行ステータス](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/docs/phase_plan.md#L76-L88)

現行Stage Tは固定格子の密度更新で、毎回のSTL抽出・body-fitted再メッシュは必須ではない。density→SDFは段階間の受け渡しであり、それだけで主要ボトルネックと断定できない。ケース生成やI/Oが流れ・随伴より重いかは計測が必要。[Stage Tの必要条件](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/docs/fixed_grid_backend_decision.md#L20-L47)

8192セル、152/663/1074反復、0.045%/7.49%/0.424%の勾配誤差は記録と一致した。ただし特定のcanonical caseの記録で、対象高Re空力の実測ではない。OpenFOAMの一反復とLBMの一sweepは作業量が違うため、反復数から速度優位を結論できない。[記録された条件と数値](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/docs/fixed_grid_backend_decision.md#L96-L112)

## 2. 最大の技術リスク：乱流モデルと定常随伴

収束した離散定常問題

\[
R(U,\phi)=0,\quad R_U^T\lambda=J_U^T,\quad
\frac{dJ}{d\phi}=J_\phi-\lambda^TR_\phi
\]

を解く方針は妥当で、反復履歴全体を保存しない点も適切。ただし残差の微分可能性、適切な基準条件での可解性、主問題と随伴の十分な収束が必要である。

KBCは衝突モデルで、それを選ぶだけで翼の乱流境界層や遷移が解決するわけではない。LES等で時間変動を計算する場合、欲しい量は通常、時間平均の力である。平均場は一般に同じ瞬時方程式の定常解ではない。「平均場に定常随伴を適用」は時間平均力の正しい勾配にならない。カオス的な流れでは通常の長時間接線・随伴も発散し得る。[NASAでの感度解析研究](https://www.nas.nasa.gov/pubs/ams/2016/07-18-16.html)

初期スコープは、定常層流で幾何・力・勾配の成立を示す段階と、対象Reで物理を検証する段階を区別する。対象空力に定常RANSを採用するなら、乱流変数、壁面処理、形状依存量まで残差と随伴の契約に含める。新LBM上でこれを構築する工数は軽くない。既存RANSを維持し、LBMを限定探索モデルとして試す選択肢を残す。

元ロードマップにあるflat plate/NACAのturbulent bridgeは重要である。圧力・摩擦、剥離、流入乱れ、翼間隙間、地面運動、壁面解像度を確認する。低Re円柱から高Reフロントウイングへ直接進めない。[元の検証順序](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/docs/phase_plan.md#L195-L209)

## 3. SDF一本化とトポロジー生成

\(\gamma=H_\epsilon(\phi)\) からBrinkman係数へ接続するchain ruleは自然だが、勾配は主に界面付近に局在する。純粋なHJ界面移動は、離れた場所の新規固体生成やsolid内部の新規穴生成を一般的に保証しない。

任意トポロジー探索の比較基準としてdensity/Brinkmanを残し、形状精緻化にはSDFを使う構成は合理的である。SDFが両方で優位かは、同じ制約下で到達できる形状とコストを比較してから判断する。

porous probeの微小な係数摂動が改善を予測しても、有限サイズのno-slip固体を入れて改善する保証はない。root-connected制約下で空中に球を追加すれば通常は失格になる。使うなら、最小寸法を満たすseedと支持部を一組にして生成し、その全体の空力・体積・連結性を再評価する。真のtopological derivativeを延期する判断は妥当だが、代替probeも実用性が確定した部品ではない。

## 4. Sharp SDFの微分経路

\[
q=\frac{\phi_f}{\phi_f-\phi_s}
\]

はリンク両端の値の線形補間であり、曲面の正確な交点とは一般に一致しない。固定された境界リンク集合では有用だが、分類が変わる時の流体状態初期化、質量保存、リンク再生成、力の直接形状微分も必要になる。

セル値としての \(dJ/d\phi\)、境界積分の形状勾配、法線速度 \(V_n\) は同じものではない。内積、界面測度、SDF符号、速度の拡張を定義してつなぐ。格子値の勾配をそのままHJ速度へ渡す仕様は未完成である。

0.2–0.4セルの移動制限でも、界面が格子点に近ければ分類は変わる。Taylor testは、微分可能な固定リンクの領域と、格子横断の有限ステップ試験を分ける。再初期化・mask適用・幾何修正後の最終候補について、流れと目的を再評価する。

## 5. 32GBと12GB VRAMを別に予算化する

ユーザー条件は両機32GB RAM、WindowsはRTX 4070 Ti。通常の4070 TiはVRAM 12GBであり、CPU RAMと合算したGPU常駐容量にはできない。[NVIDIA仕様](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4070-family/)

Macのチップ型番は未確認。Metal高速化はApple Siliconを想定する。Intel Macなら実行候補を再評価する。Apple Siliconでも32GB全量をソルバが使う前提にはしない。

提案のD3Q27 FP32 ping-pong=216 B/cellは正しいが、随伴中にも主状態が必要である。

| 配列構成の例 | populationのみのB/cell | 5百万セル |
|---|---:|---:|
| primal ping-pong | 216 | 1.08 GB |
| frozen primal 1組＋adjoint ping-pong 2組 | 324 | 1.62 GB |
| primal・adjoint各2組 | 432 | 2.16 GB |

SDF、速度、RHS、壁リンク、乱流変数、halo、テンポラリはこの外側にある。320–400 B/cellは配列再利用・再計算を規定した実装予算であり、一般的な随伴の安全な上限ではない。

full-populationを未知数にする通常のGMRES(20)では、Krylov基底21本だけで

\[
21\times5{,}000{,}000\times27\times4=11.34\ {\rm GB}
\]

になる。これは今回の算術見積もりで、XLBの実測ではない。主状態等を加えれば12GBを超える。短い再始動、少数ベクトルの反復法、固定点随伴、前処理、状態削減等を比較し、収束とメモリを同時に測る必要がある。

Windows GPUの初期常駐予算を8–9GB程度、Macのsolver working setを12–16GB程度にするのは余裕の置き方として合理的だが、保証セル数ではない。実際のpeak allocationとmemory pressureで更新する。

5M×1万sweep÷100–500 MLUPS=100–500秒も算術として正しい。しかし1万sweepも随伴の処理速度も未検証で、候補primal再評価、複数条件、HF検証は含まれない。性能指標は、同じ信頼性で改善候補を得るまでの時間とする。

## 6. 解像度をセル数の目標から逆算しない

元front-wing例はSDF用voxel 40mm、最小厚さ宣言10mmなので0.25セルである。これは初期幾何デモの設定であり、CFDメッシュの実測解像度ではない。それでも設定を読み替えるだけでは薄翼の製造可能性を検証できない具体例になる。[例の設定](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/examples/front_wing/project.yaml#L32-L56)

最小翼厚、隙間、地上高、境界層から必要な細かさを決め、近傍・後流・遠方境界を含めてセル数を求める。補間境界だけではサブグリッドの薄板・流路を解決できない。Re、格子Mach数、緩和係数、時間刻みの整合も必要で、数値安定性と空力精度を分ける。

## 7. 両OS対応の現実的な境界

Windowsの基準環境はRTXを使うWSL2/Linuxを候補にする。元repoにもlocal/WSL/Docker実行層があり、OS移植とCFD方式の変更は別問題である。[既存実行層](https://github.com/ramhachi/CFD_opt_sdf/blob/fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287/src/cfd_sdf/execution.py#L114-L155)、[NVIDIA WSLガイド](https://docs.nvidia.com/cuda/wsl-user-guide/)

XLBのWarp単一GPUとNeon多解像度は別環境で、Neon wheelはLinux向け。同居前提は置けない。随伴形状・トポロジー最適化もWIPである。[XLB環境条件](https://github.com/Autodesk/XLB#installation-with-neon-support)

確認したstepperの衝突モデルはBGK/KBC/SmagorinskyLESBGK。D3Q19 MRTを標準搭載済みとして工数を見積もれない。[固定commitのstepper](https://github.com/Autodesk/XLB/blob/9470e54a8d7ccd68d8e5563ca7a573040841ea8c/xlb/operator/stepper/nse_stepper.py#L45-L84)

曲面補間のHybridBCもmesh-distanceを使う構成であり、動的SDF→q→形状微分が完成済みとは言えない。JAXとWarpに全機能の互換性があるとも仮定しない。[固定commitの境界実装](https://github.com/Autodesk/XLB/blob/9470e54a8d7ccd68d8e5563ca7a573040841ea8c/xlb/operator/boundary_condition/bc_hybrid.py#L174-L198)

MacのMLX custom Metal/custom VJPは候補として妥当。ただしCFDや随伴線形ソルバを提供するものではなく、float64はCPUのみ。[MLX custom kernel](https://github.com/ml-explore/mlx/blob/main/docs/src/dev/custom_metal_kernels.rst)、[MLX型制限](https://ml-explore.github.io/mlx/build/html/python/data_types.html)

共通化するのは問題仕様、幾何、力、残差・勾配の契約、最適化、受入判定、成果物。バックエンドは定常/非定常、乱流、境界、形状勾配、精度、格子階層の対応可否を明示する。両GPUで同じ離散化の結果を許容誤差内で一致させ、bit単位一致や同じ速度は要求しない。

二種類の手書きカーネルを確定する前に、TaichiのCUDA/Metalのような共通記述の候補を小さく比較する余地はある。必要な微分と性能を測って採否を決め、第三の本格開発ラインにはしない。[Taichi](https://github.com/taichi-dev/taichi)、[微分の制限](https://docs.taichi-lang.org/docs/master/differentiable_programming)

## 8. 最適化・AMR・監査の修正

**不等式のAugmented Lagrangian**

提案の \(f+\lambda g+\mu[g]_+^2/2\) だけでは非活性制約や乗数更新を含む標準的な不等式処理が定義されていない。例えば \(g_i\le0\) ならPHR型は

\[
\mathcal L_\mu=f+
\sum_i\frac{[\lambda_i+\mu g_i]_+^2-\lambda_i^2}{2\mu},
\qquad
\lambda_i^+=[\lambda_i+\mu g_i]_+
\]

とできる。一つのscalar functionalに束ねれば、一つの流れ状態につき随伴RHSを一つにできる。しかし複数flow caseには原則各状態のprimal/adjointが必要で、line searchも追加primalを要する。制約が多いだけで自動的にMMAへ戻す必要もない。[拡張ラグランジュの一次資料](https://epubs.siam.org/doi/10.1137/0312021)

**候補受入**

擬似コードでは、HF検証がない回に幾何制約だけで候補を採用している。候補の幾何修正・再初期化を完了させた後にprimalを再評価し、merit functionやfilter型の目的/制約比較で受入を決める。hard gateで失敗してstepを縮め続けるだけでは制約境界で停止し得るので、可行性回復の方針も必要。

**DWR**

正しいSDFでは \(|\nabla\phi|\simeq1\) なので、これは壁までの距離を示さない。壁近傍判定は \(|\phi|<w\) 等で行う。

収束した同一格子の代数残差 \(R_h(U_h)\simeq0\) に \(\lambda_h\) を掛けても、残る空間離散化誤差を適切に推定できない。細かい空間へ写した状態での残差 \(R_{h/2}(I_h^{h/2}U_h)\) やtruncation errorと、整合した随伴情報が必要である。[NASAの誤差推定研究](https://www.nas.nasa.gov/assets/nas/pdf/staff/Aftosmis_M_Adjoint_Error_Estimation_and_Adaptive_Refinement_for_Embedded-Boundary_Cartesian_Meshes.pdf)

複合Lagrangianの随伴だけではdrag/downforceの誤差が相殺し得るため、重要な制約応答の精度も監視する。格子間補間、restriction、subcyclingの転置を含め、格子配置を固定した区間で先に勾配を認定する。

**Multifidelity**

改善の符号一致や20候補のSpearman相関0.8は診断として有用だが、制約限界付近や最良候補の正しさを保証しない。正式なtrust-regionなら、同じ高精度基準点からの実改善とモデルの予測改善の比で半径を更新する。低忠実度モデルの系統誤差があるなら、半径縮小だけでなく局所補正や精度更新が必要である。[March–Willcoxの一次資料](https://kiwi.oden.utexas.edu/papers/Multifidelity-optimization-March-Willcox.pdf)

定期監査のみの段階では、そのように呼び、trust-regionの収束保証を主張しない。OpenFOAMにも格子収束、壁面モデル、実験等との整合が必要である。監査に使った候補と最終未使用評価の形状・条件を分ける。

**Multipoint**

nominalだけを通常計算し5回に一度off-designを入れる単純切替は、宣言した重み付き目的の勾配を毎回使う方法ではない。初期は少数の決定的ケースを逐次評価する。間引くなら、確率的更新やactive-case管理として目的の推定と制約保証の範囲を明記する。

## 9. LKS・AIを初期の必須項目にしない

ALKSの最大75%削減と境界随伴の近似は一次資料と整合するが、非定常熱流体の比率を定常3D外部空力へ転用できない。論文の別の定常例では約42%である。[ALKS論文](https://arxiv.org/html/2411.03090v1)

LKSでMVPを作り、LBMで境界・力・随伴を再設計する順序は二重投資になる。初期は一つのLBM系に限定する。

MLより先に直前のCFD解や同じ格子の近い条件の解を再利用する。PODも無料ではなく、5Mセル×4場×FP32×64 modeなら基底だけで5.12GBになる。これは算術見積もりで、coarse-grid化すれば減らせる。50–150ケースで十分かは自由度と分布による。LBMでは速度・圧力からpopulationと非平衡成分へ戻す経路も必要。初期残差だけでなく実収束時間で効果を評価する。

## 10. 修正版アーキテクチャと計画

~~~text
共通 ProblemSpec / geometry roles / provenance
                     |
       幾何と物理解像度の事前検証
                     |
       適用する物理・目的を明示
                     |
    +----------------+------------------+
    |                                   |
既存density/Brinkman                 実験SDFバックエンド
任意トポロジーの比較基準             初期は定常・形状最適化
    |                                   |
    +------- 共通の応答・勾配契約 --------+
                     |
      制約付き更新 → 候補primal再評価
                     |
          受入 / 可行性回復 / rollback
                     |
    独立したbody-fitted評価・格子収束
~~~

CUDAとMetalでは同じ残差・力・精度判定を用いる。新バックエンドの優位を認定するまで既存経路を撤去しない。problem hashに加えgeometry内容、design state、grid、solver version・設定、精度、応答単位・方向、gradient variable、収束履歴を保存する。密度勾配とSDF勾配を混同しない。

以下は後続作業の提案であり、今回の実装依頼ではない。

| 段階 | 作業 | 次へ進む条件 |
|---|---|---|
| 0 問題・環境の固定 | Mac型番、使用可能VRAM、Re、地上高、最小厚さ/隙間、物理モデル、目的を定義。参照ケース再認定と内訳計時 | 何を速くするか定量化でき、比較可能な参照がある |
| 1 固定形状の前進計算 | WindowsでXLBの一構成を試す。単純ケースに加えて対象Reの翼/地面を早期比較。CPU FP64参照を残す | 力・圧力/摩擦・必要解像度・メモリが予算内。物理が不適合ならここで止める |
| 2 共通離散化と両GPU | 定常2D・単一格子のSDF境界と力を固定しMacで再現。随伴線形解法と配列寿命を決める | CPU/CUDA/Metalの許容誤差内一致、随伴可解性、peak memory確認 |
| 3 制約付き形状最適化 | dot-product、FD刻み掃引、Taylor test、形状勾配→HJを確認。候補再評価、乗数更新、rollback | 微分可能範囲の勾配が正しく、最終実形状で改善と制約充足 |
| 4 対象条件の3D | 有限翼、地面、多翼。格子・時間・乱流依存、少数multipointと独立HFを検証 | 改善が再現し、制約余裕が推定誤差を上回り、実行時間が許容 |
| 5 必要な拡張 | 計測上必要なら静的2-levelと随伴整合。新規トポロジーをdensity経路と比較 | 追加精度・探索能力が工数と時間に見合う |

最初の30日は、完成した最適化器ではなく「採用する物理モデルと高速化方式を選べる測定結果」を成果にする。順調なら2D随伴まで進めるが、primalの適合性が不明なまま先行させない。

6か月の第一目標は、限定した対象・一つの流れモデルについて両OSで同じ問題を解き、3Dの改善候補を独立評価できること。AMR、任意トポロジー生成、複数衝突モデル、MLを同時に必須にしない。担当人数と数値計算の経験が未指定なので完成時期は保証できない。

精度閾値は期待改善量と制約余裕から決める。例えば狙う改善が1%なら、3–5%の力誤差のみを許した評価では改善を判定できない。微分チェックではゼロ付近の相対誤差の不安定性を避け、絶対・相対誤差を併記する。

**現時点で推すのは「既存基盤＋実験的LBM/SDF＋同じ条件での比較」である。両OS対応はこの方針で進められる。**

公開ソースと公式資料によるレビューであり、実機の速度・収束・実メモリは未測定。既存ソースは変更せず、プログラムのcommit/pushも行っていない。
