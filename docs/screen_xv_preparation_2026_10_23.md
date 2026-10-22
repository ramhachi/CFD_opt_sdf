# SCREEN/XVの次の登録判断 — FID01_GO受領後、2026-10-23

**PREPARATION_ONLY。** [phase_plan](phase_plan.md)に従う具体化資料であり、
SCREEN/XVの登録・凍結・計算開始ではない。[FID受領票](fid01_to_screen_xv_handoff_2026_10_23.md)
が結果・単位・副ラベルの引継ぎ元。GEOM-03の形状・seed・閾値には影響しない。
元のFID分析やT2-0の結果も変更しない。

## SCREENで次に決めること

1. **geometry pathを先に固定する。** GEOM03_PASSなら検証した研究用profileの版・hashと
   他のgeometry/volume/drag拘束を登録する。NO_GO/INCOMPLETEならR0-clean fixed set/parent経路へ
   戻し、その有限集合の生成・geometryによる選別規則・選択バイアスをforceを見る前に明記する。
   R3だけを差し替えて他の拘束を免除しない。
2. **heaveの扱いを明示する。** 最初はheaveを固定したwide-mode案を検討する。これは新しい
   設計選択であり、FIDがheave係数0を義務化したわけではない。pure heaveはFAILだが、
   heave−31.1+pitch+.7はPASSしている。局所/narrow modeはFID§6.4の除外を維持する。
   残す各mode・amplitude・符号・phi-space合成・volume処理は実装builderとhashで束縛する。
   当面の候補はpitch3.1°、camber19.7mm、reflex29.3mm、twist1.1°、sweep11.3mmをA*で
   正規化する5mode。これらはMODEのgeometry prescreen範囲であり、全parameter boxのfidelity資格ではない。
   [FID登録§2](fid01_registration_2026_10_21.md)に近いjoint analytic parameter構成とharness再構成を
   第一案とし、GEOMのnon-SDF linear phi-space組合せを無条件に最適化器へ流用しない。
3. **推定量をfloorと分ける。** g_min=0.027030580470324268とJ_b48の受領だけでは、
   SCREENのprimary numerator、phase平均、flow_48確認集合は全部決まらない。
   同位相のparent/candidate対差分、parent正規化、改善/dragの推定量と判定を登録する。
   flow_32の提案とflow_48確認を残し、FID副ラベルから発火しない追加義務を作らない。
   具体案は`I32=mean_k(F_DF,candidate,32,k−F_DF,parent,32,k)/0.26577921974115387N`を
   primaryとし、flow_48の確認を別に定める形。ただしこの推定量の選択自体は新しいSCREEN登録事項。
4. **選択と確認を分けて有限にする。** 同世代は共通phase、手作業対照と同予算random-direction対照、
   上位modeの小さな応答曲面、finalistの全phase確認を具体的なstate/job表へ落とす。
   最大state数、phase数、GPU/CPUとwall cap、同一infra retry、NO_GAIN/INCOMPLETEを先に固定する。
   過去の概算表はbudget authorityではない。結果からphaseや候補を足さない。
   3変数のfull quadraticなら係数は10個であり、design matrixがfull rankになる点集合を先に示す。
   既知FID形状をmanual対照にする場合は事前可視性を明示し、random対照も同じ5mode/A*とgeometry規則を使う。
   phaseは既使用R2 k=0..10と分ける案を具体化し、探索世代と封印したfinal確認集合を区別する。
5. **XVへの受渡しを決める。** parent/finalistのNPZ・phi・mask・grid・constraint margins、
   campaign入力、geometry profile、phase/job manifest、選択規則をhashで固定する。
   XVの判定専用結果を見たcandidate調整はしない。

以上は[既存SCREEN issue #64](https://github.com/ramhachi/CFD_opt_sdf/issues/64)、
FID登録§8と既存R1–R6を具体化する項目。各数値budgetやsampling choiceはまだ登録していない。
[v18 MODE計画](v18_mode01_plan_2026_10_19.md)のN_phi<=8272、v17 baselineに対する10% smoothed-volume band、
clearance>=0.15m等は意味論とhashを保ってSCREENへ束縛する。drag capと不確かさの扱いは未登録。
同位相drag差分の非増加を片側の不確かさ込みで判定する案でも、係数・phase最小数・未解像の分類を先に決める。

## XVの単一finalistではV2にもSEの不足がある

[analyzerのlevel_stats](../scripts/fid01/analyze_fid01.py#L165-L195)は、V1をdesign自身のmirror-pair平均、
V2を複数designからpoolしたpair variance、V3をtier-Aの複数design回帰の残差で扱う。
したがって、single finalistでV2が1有効pairだけになると、自身のpair varianceを計算できない。
V3だけを直しても不足する。FIDの有限ensembleで通った登録判定は維持し、XVへの一般化を別に設計する。

観測単位の案は、grid g、mirror pair jについて
`d_gj=((F_candidate,g,j+−F_parent,g,j+)+(F_candidate,g,j−−F_parent,g,j−))/2`。
±を独立な2標本として数えない。新しい判定専用pairをV1/V2/V3で共有し、性能推定に用いるV1全pairと
grid整合に使う共通subsetを区別する。grid contrastは同じpairの`d_gj−d_hj`を扱い、
根拠なくgrid間の共分散をゼロにしない。

| 登録候補 | case数（parent/finalist×mirror±） | 限界と停止 |
|---|---:|---|
| A: V1=16pair、V2/V3=各2pair | 2×2×(16+2+2)=80 | V2/V3各1自由度。varianceを計算できる最小候補だが精度は保証しない。未解像はUNRESOLVED |
| A′: V1=16、V2/V3=各4pair | 96 | 各3自由度。最初からこのrun set/budgetを選ぶ。Aの結果を見て追加する方式ではない |
| B: 既存calibrationのdiscrepancyを利用 | 本資料では未確定 | 現8-design残差はplacementとdesign-dependent grid departureを分離しておらず、single-finalist measurement SEとしては採用根拠不足 |

A/A′でもsamplingと区間の意味を先に解決する必要がある。
[現shift生成](../scripts/prepare_kaggle_xfid_gridphase_x3.py#L43-L58)は固定Halton配列であり、iid random sampleではない。
固定panelの経験的ばらつきに限定するか、未使用catalogからの確率抽出等をprospectiveに定めるかを選ぶ。
`s/sqrt(n)`を計算しただけで所定の頻度論的coverageを得たとはしない。
[NISTの平均の区間](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm)も標本数・自由度を伴う推論であり、
2pairでは自由度1となる。適用母集団・抽出法・分布/coverage仮定をXV登録に書く。

[runner](../infra/kaggle/kernel_openfoam_xfid_gridphase_x3/runner.py#L193-L202)は固定templateへSTLだけを平行移動し、
[bottom wall](../infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template/system/blockMeshDict)は固定される。
そのため3D shiftのばらつきに境界との距離変化も含み得る、というのがソースからの推論である。
純粋なmesh noiseや物理的な姿勢不変性に読み替えない。

## 使えない近道と、残る登録欄

- [force_window](../infra/kaggle/kernel_openfoam_xfid_gridphase_x3/runner.py#L129-L150)の最後25%の反復値は、
  iterative convergenceの診断である。`window_std/sqrt(window_rows)`を配置SEに代用しない。
  [NASAの反復収束](https://www.grc.nasa.gov/www/wind/valid/tutorial/iterconv.html)もresidualと目的量の安定性を扱う。
- FIDの回帰残差1.45e−3 Nを新finalistのmeasurement SEとしてコピーし、全項を新shift数の平方根で縮めない。
  calibrationを使うならmeasurement SEと別のprediction/discrepancy項とし、optimizer-selected designへの適用域を説明する。
  [NISTの新観測の予測区間](https://www.itl.nist.gov/div898/handbook/pmd/section5/pmd512.htm)はfitと新観測の不確かさを区別する。
- G3-setのsingle-finalistへの適応とV3 conflictの分類を計算前に固定する。
  比のゼロ近傍を避けて`d3−0.6d1`、`1.67d1−d3`のmarginで扱う案はあるが、
  区間全体の合格を要求するならFIDのpoint-pass ruleより厳しい新しい適応であり、既存規則とは称さない。
- OF floor 0.012674959854238867の推定量とparent正規化、実際のdrag制約・margin、反復安定性、
  有効pair最小数、CPU/wall cap、再実行上限を登録する。V3が8caseになるAでも、既存7–12h/caseの
  planning rangeを掛ければ56–96CPU hの概算となる。新しい測定値やwall ETAではない。
- 完了・解像した違反だけFAIL、欠損/予算停止はINCOMPLETE、完了していてSE等が識別不能ならUNRESOLVED。
  追加phaseや候補調整による救済を行わない。
- 3meshの有限な整合確認をGCI/格子独立性へ広げない。
  [NASAの格子収束](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html)は漸近範囲等の確認を要する。

次の登録でまずsamplingの意味と費用を比較し、A/A′等の一つの有限案を選ぶ。
Bの現在のcalibrationをSEに流用する案は採用しない。
[既存XV要件](xv01_registration_requirements_2026_10_22.md)の不変なholdout/constraint条件を満たしてから凍結する。
本資料で新しい物理閾値・資格・計算開始を宣言していない。
