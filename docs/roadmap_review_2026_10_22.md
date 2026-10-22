# 最新結果に基づく計画修正と先行研究の照合（2026-10-22）

本書は、ユーザーの「現状の分析と最新の結果を踏まえた計画の修正、そしてイシューの起票」という依頼による調査・計画記録である。
順序と状態の権威は引き続き [phase_plan.md](phase_plan.md)。本書は新しい CFD の登録、評価器の採用、製品範囲の最終決定ではない。
元の研究記録・閾値・判定は保持し、将来の仮説には「未検証」と明記する。

## 1. 判断と調査範囲

現在の課題は、最適化手法を高度化することより先に、**改善を解像でき、独立 CFD へ転写できる評価器と形状の許容範囲を確定すること**にある。

1. UNC-01 は、大きな pitch/reflex の対差分について有望な証拠を追加した。既存の FID-01 を凍結済みの規則で完結させる価値がある。
2. T2-0b/c/d はすべて登録済み NO-GO。従来の「WaterLily の分岐も失敗したら T2-0 評価器へ移る」は移行先を失った。M4 に評価器の回復・範囲限定・終了の判断を戻す。
3. M3b の前には、滑らかな形状を配置依存で落とす幅規則の独立検証が必要。探索済み R3 をそのまま採用してはならない。
4. 高 Re の次案は、一次データとの対応を確定する作業と、固定メッシュ上での安価な定常解法の検証を分ける。計算資源の変更だけではモデル・基準データの不一致は解決しない。

照合した checkout は、統合 `1467af14`、進行中 FID-01 の公開ブランチ `claude/m3a-fid01` の `78e1e76f`、GitHub #57–#67 とその関連記録。
調査開始場所 `625d` の HEAD `fa3a42e0` は最新ではなかったため、最新統合から専用作業ブランチを作った。元の未追跡ファイルは対象外。
調査後の再確認・検証結果・参照ファイルの SHA-256 は [監査記録](evidence/roadmap_review_2026_10_22/validation.json) に記録する。

## 2. 証拠から分かる現在地

| 対象 | 確認済みの結果 | 計画への意味と主張の上限 |
| --- | --- | --- |
| 最終目標 | canonical SDF を持つ剛体の形状・トポロジー最適化器。最終用途は高 Re・乱流・地面効果の FSAE 空力。期限なし | Re 80 の独立検証 L2 と、目標物理 L3 を引き続き分ける。2D 断面を車両の適格性へ広げない |
| M2 UNC-01 | `M2_COMPLETE`。v18、Re 80、flow_32、広いモードの downforce の配置対差分 SD は約 2.1–5.5e-4 N。pitch +3.1° の flow_32/48 比は 0.980、90%区間 [0.962, 0.999] | この親・モード・位相集合に対する有限の証拠。全モードの格子収束や一般的な配置不変性ではない |
| M2 の転写 | 粗い OpenFOAM 格子で pitch/reflex の downforce 対差分保持率は 0.63–0.71、drag は 0.67–0.80 | 符号と一定の保持を支持するが、FID-01 の複数格子判定も、最適化後の XV-01 も代替しない |
| 小さな応答・対照 | D0 downforce は flow_24/32 で符号反転。1セル x 並進は flow_32 で約 −1.65e-3 N。局所 bump の粗い OpenFOAM 応答は約20倍 | flow_24 を判定へ戻さない。並進をゼロ対照と仮定しない。表現・抽出・有限箱を誤差要因として残す |
| FID-01 #62 | freeze 3、flow_32 の4 kernel と flow_48 出力の検証までコミット済み。WaterLily だけから決めた tier A は8設計、tier B は4設計。OpenFOAM を含めた最終登録判定は未確認 | **進行中**。tier A の成立や run の収束を `FID01_GO` と読まない。進行中キャンペーンの基準・設計・analyzer を変更しない |
| T2-0b | `T20B_NO_GO`。G2、G3b、G6 が不合格 | med30 の実験曲線との近さは、細分化後の正しさを保証しなかった |
| T2-0c | `T20C_MORPH_NO_GO`。h/c=0.224 ではモーフィング後に全 gate 通過。0.134 は基準メッシュ依存、0.09 は最細格子で定常計算が収束しない | 固定トポロジーの変形は有用。単一の高さの成功を広い範囲の evaluator GO にしない |
| T2-0d | `T20D_NO_GO`、DATA=`FAIL_INPUT`、DIFF=`FAIL_VALUE`、費用=`NOT_AFFORDABLE`。中央値92.4分、最大134.0分/評価 | 高 Re 評価器の自動採用を停止。#57 は研究完了として closed、評価器は不採用のまま |
| 幅規則 | WIDTH-RULE は `EXPLORATORY_COMMITTED`、`NO_CANDIDATE_MEETS_K1_K6`。R0 は v18 の最適化に似た組合せ200個中190個を落とす | M3a は登録通り R0 を保持。連続振幅を探索する M3b の許容規則は別途資格化する |
| 勾配・再初期化 | AD は BLOCKED、原因未特定。登録済み再初期化は親上で有界でない | #23 の研究枠、#28 の再開条件を保持。新しい DIAG や backend 実装を critical path に足さない |

主な一次記録: [UNC-01 analysis](evidence/unc01_2026_10_20/analysis.md)、[T2-0 全体整理](t20_summary_for_m4_2026_10_22.md)、
[T2-0d verdict](evidence/t20d_registered_2026_10_21/verdict.json)、[T2-0d 実行後の記述](evidence/t20d_registered_2026_10_21/note_2026_10_22_after_analysis.md)、
[幅規則の提案](width_rule_decision_2026_10_20.md)、[FID-01 freeze 3 の公開記録](https://github.com/ramhachi/CFD_opt_sdf/issues/62#issuecomment-6324411553)。

## 3. 解釈を修正する点

### 3.1 対差分の SD と、全誤差・最小改善を分ける

同じ配置 p の候補と親から d_p = J(candidate,p) − J(parent,p) を作ると、共通の配置誤差が相殺する。
その SD が sigma_d であり、親の絶対値の配置 SD sigma_F と異なる。バイアス、未標本化の z 位相、格子誤差、モデル誤差、実験不確かさをすべて含む量ではない。
位相数を増やしても系統的な格子・物理モデル誤差は消えない。既定の決定的な配置列から得た区間を、実際の物理的な乱れの確率として解釈しない。

M2 の downforce E2 入力は S_b≈0.0067、S_c≈0.0101、S_d≈0.0034。
文字どおりの E2 は約2.0%、対差分版は約0.68%になるが、**後者で現行の閾値を置き換えない**。
FID-01 は tier A に2.0%（5.363e-3 N）を使い、tier B に対差分版の床を使って M3b の最小改善を登録済みの写像で決める。
M3b はその最終記録を参照し、本レビューで係数を新設しない。
なお M2 の pitch +3.1° は downforce の記述的改善約15.6%と同時に drag が約11%増える。
大きく安定した応答があることと、drag 制約を満たす改善方向があることは別で、#64/#65 の制約確認を省略しない。

### 3.2 T2-0d は「物理的な非定常性が原因」を立証していない

有効な URANS 58 run は登録した分類で定常状態へ落ち着いた。非定常と分類された5 run は、実行後の記述では遅い過渡であって振動ではない。
これは**その2D SAモデルと数値条件**の結果であり、実験流れが定常である証拠ではない。
また DIFF の `FAIL_VALUE` は細粗格子間で有意な矛盾を確定したという意味ではなく、fine30 の基準メッシュ依存によって差分整合を証明できなかった登録結果である。

実行後の記述では、dt を半減するごとに定常 Cl が約0.18%動き、見かけの次数は約0。PIMPLE と SIMPLEC の解にも0.25–0.91%の差がある。
局所時間刻みで安くなる可能性はあるが、**固定 dt の URANS に近いだけで正解としない**。離散定常方程式の残差、保存、初期値依存、時間刻み項の扱いも照合する。
同じく24分という warm start の費用は未実行の推算であり、92.4分の実測値に置き換えない。

### 3.3 実験との対応が未確定なまま乱流モデルを調整しない

既存 G2 は Genua (2009) Fig.6 から読み取った二次曲線との一致である。計算は sharpened TE の Tyrrell026S、2D、全乱流の SA-WF。
参照は有限翼幅・端板・有限後縁厚を持つ実験に由来し、balance と midspan 圧力積分のどちらか、対応する迎角、trip 条件の系列同定は完了していない。
既存の ±0.005 Cl はデジタイズの帯であり、実験・モデル・幾何の総不確かさではない。

Genua 本文は全乱流、Tu=0.3%、長さスケール1 cm、後縁の尖鋭化を明記する。一方、Zerihan–Zhang は遷移固定の影響を報告している。
従って遷移、後縁、有限翼幅、境界条件は**原因候補**であり、今回の誤差の原因が遷移だと結論しない。
一次条件との対応が確定しなければ、条件を公開した別の検証ケースを選ぶ。

### 3.4 幅規則の代替は複合 gate として検証する

R0 の1セル突出は二値化した cell occupancy の性質。閾値を下げると真の薄板も通るため、単なる緩和は解決にならない。
R3 は trilinear な表現物体への球による opening の欠損を測る既存候補で、単独では全 K1–K6 を満たさなかった。
新規 seed・形状・組合せに対して、R3 + frozen-node margin + 固定トポロジーの複合規則を一度だけ検証する。
薄い neck の分離、solid/void の細部、斜め板、wedge、凍結境界の rim mismatch、phi の正の定数倍を含める。
R3 は CAD の真の最小肉厚や製造の資格を与えない。失敗時は R0-clean な固定集合に限定するか親の選択へ戻り、半径や許容を試し直さない。

## 4. 先行研究から使う方針と限界

すべて2026-10-22に一次資料または公式文書で確認。本文全体を読めたものと、著者要旨・公式仕様までの確認を区別する。
以下は手法を選ぶ根拠であり、本プロジェクトでの有効性の実証ではない。

| 資料 | 確認した内容と利用する方針 | 適用限界・次の検証 |
| --- | --- | --- |
| Zerihan & Zhang (2000), [Aerodynamics of a Single Element Wing in Ground Effect](https://doi.org/10.2514/2.2711); [著者所属機関の要旨](https://researchportal.hkust.edu.hk/en/publications/aerodynamics-of-a-single-element-wing-in-ground-effect/)、[Zerihan thesis](https://eprints.soton.ac.uk/426058/) | moving ground の実験、剥離と遷移固定の影響。実験系列・trip・迎角・force 定義を先に同定する | 原論文の書誌と著者要旨まで。thesis PDF は取得できず、Genua 曲線がどの原系列かは未解決 |
| Genua (2009), [A CFD Investigation into Ground Effect Aerodynamics](https://repository.tudelft.nl/record/uuid%3Af18687c0-adf2-43dc-8485-ee90716c1d5d)、[本文 PDF](https://repository.tudelft.nl/file/File_ec8400ef-f0a8-48d5-9c67-f266aa15a07b) | 本文の幾何・流れ条件・メッシュ・分類の記述を照合。再現対象は特定の2D計算で、原実験とは分ける | 原 CFD に対する一次資料であり、Zerihan 実験には二次資料。特定の粗い格子での良い一致を収束と同一視しない |
| [Turbulence Modeling Resource: NACA0012 validation](https://tmbwg.github.io/turbmodels/naca0012_val.html) と [numerical analysis](https://tmbwg.github.io/turbmodels/naca0012numerics_val.html) | 公式の座標、格子族、データとモデル形を再利用する候補。検証の入口を、実装・格子の照合と実験比較に分ける | Re=6e6、自由流のケースで地面効果ではない。NASA 由来サイトの公式移転先。選択するなら原データ・BCをそのまま登録し、高Re地面効果の資格へ拡張しない |
| Langtry & Menter (2009), DOI [10.2514/1.42362](https://doi.org/10.2514/1.42362)、[公式 SST-LM 記述](https://tmbwg.github.io/turbmodels/langtrymenter_4eqn.html) | 遷移モデルの式、モデル variant と流入乱流条件を固定する。SA-WF と LM を区別する | LM を正解と置かない。現在の LM は約3.5時間/件で in-loop に未適格。trip・Tu が不明なデータへ後付けで合わせない |
| Eça & Hoekstra (2014), [JCP 262:104–130](https://www.marin.nl/en/publications/a-procedure-for-the-estimation-of-the-numerical-uncertainty-of-cfd-calculations-based-on-grid-refinement-studies), DOI 10.1016/j.jcp.2014.01.006 | 系統的に細分化した格子族から不確かさを推定し、scatter を評価する方針 | 現在の固定第一層の格子列や Poisson-confounded flow_40 にそのまま GCI を適用しない。実現値差と細分化差を分けた後に使う |
| Oliver et al. (2014), [Estimating uncertainties in statistics computed from DNS](https://arxiv.org/abs/1311.0828), DOI 10.1063/1.4866813 | 相関を考慮した時間平均の統計誤差を、離散化誤差から分ける | DNS の手法の参考。未収束過渡を定常確率過程として扱わず、決定的な配置列を時間標本と混同しない |
| OpenFOAM [localEuler 公式仕様](https://doc.openfoam.com/2306/tools/processing/numerics/schemes/time/rtm/localEuler/)、[v2512 pimpleFoam source](https://api.openfoam.com/2512/pimpleFoam_8C_source.html) | 定常計算用の pseudo transient / LTS と、v2512 の既存 LTS 分岐を確認。独自 solver を作らず限定試験の候補にする | localEuler の擬似時間を物理時間やスペクトルに使わない。ビルドでの作動・収束・差分精度・費用は未検証。source は検索索引までの確認 |
| Jakobsson & Amoignon (2007), [Mesh deformation using radial basis functions for gradient-based aerodynamic shape optimization](https://doi.org/10.1016/j.compfluid.2006.11.002) | 境界変形を既存メッシュに伝播する文献上の代替。固定メッシュ上で形状差分を測る方針を支持する | 現在の解析的 morph を先に使う。必要が確認されるまで RBF 実装や依存を加えない。本文公開部分・著者要旨まで |
| Alexandrov et al. (2000), [First-Order Model Management With Variable-Fidelity Physics Applied to Multi-Element Airfoil Optimization](https://ntrs.nasa.gov/citations/20000097390) | 低忠実度モデルは高忠実度の改善傾向を予測できる範囲で使う。FID → screening → 独立検証という順序を維持する | Euler/RANS、transonic の実証を Re80/高Re の橋渡しの証拠にしない。局所補正や trust region は、転写が確認され必要が出た時の候補 |
| Sigmund (2007), [Morphology-based black and white filters for topology optimization](https://doi.org/10.1007/s00158-006-0087-x) | solid/void の長さスケールを形態演算で制御する考え方を参考にする | density 構造最適化のフィルタの研究。現在の R3 のパラメータや SDF 幾何 gate を資格化する根拠ではない。出版社要旨まで |

## 5. 修正後の順序と分岐

### 5.1 今行う作業

| 優先 | 作業 | 終了条件 |
| --- | --- | --- |
| 1 | FID-01 #62 を既存の登録のまま完結する。別担当の実行中ブランチは読み取りのみ | 完全性の検証、凍結済み analyzer の最終 verdict と原因・secondary labels の記録。進捗を GO としない |
| 並行 | M4 #66 の判断資料を前倒しで整える。T2-0 の fallback 不成立と選択肢を既存証拠から記録する | 判断資料の完成。M4 の最終製品・評価器決定は M3 の必要な結果が揃った時に行う |
| 並行 | EVAL-VALID-01：高Re評価器の一次データ・検証条件の同定 | validation matrix、判明/不明な条件、候補ケース、未解決時の中止規則。CFD は不要 |

### 5.2 FID-01 の登録結果による分岐

| 登録結果 | 次に進む先 | 進まないもの |
| --- | --- | --- |
| `FID01_GO` | GEOM-03 の独立検証、#64 の登録、#65 の判定専用格子での独立検証 | GO だけで最適化済み改善や FSAE 対応を主張しない |
| `FID01_NO_GO`, cause=`WL_OF` | 登録が指定する滑らかな対流スキームの安価な WaterLily 比較を1回。発火時に別 issue で予算・規則を固定 | 事前に失敗を仮定して実装・試験しない。AD 診断を混ぜない |
| `FID01_NO_GO`, cause=`OF_MESH` | OpenFOAM 参照格子の問題として M4 に戻す。必要なら新規登録の参照回復研究を選ぶ | 滑らかな WaterLily スキームを自動起動しない |
| `INCONCLUSIVE_*`, `INCOMPLETE`, `INVALID` | 正確な種類を保持し、再登録可能回数など FID-01 自身の規則に従う | 欠損を物理 No-Go に変換しない。任意の再実行を加えない |

旧 fallback の最後の「T2-0 評価器へ移る」は、**M4 が新しい評価器研究か範囲限定・終了を選ぶ**へ修正する。
#57 の3件の NO-GO は変更せず、#67 は新しい登録済み evaluator GO と M4 の範囲決定まで blocked。
L1/L2 が成立しても、高Reの評価器採用が未解決なら L3 は未達のまま残す。

### 5.3 M4 が高Re評価器の新しい研究を選ぶ場合

1. EVAL-VALID-01 の条件表と B5（U、L、Re、迎角、地上高、乱流、trip、2D/3D、目的量）を固定する。
2. EVAL-PT-01 の solver-free な離散方程式・参照の監査を行い、再利用する基準メッシュを content hash で入力にする。
3. 参照と停止規則を事前登録してから、既存の `pimpleFoam` LTS の小さな比較を行う。対象は attached control、peak、強い剥離の代表点と、同一 mesh の ±形状変化。
4. 反復誤差・保存・初期値、時間項の影響、差分の再現性と費用を先に判定する。その後に一次データとの validation と系統的な格子・モデル比較を行う。
5. いずれかが不成立なら bounded No-Go / unresolved を記録して M4 に戻る。LM/3D/別 solver/計算資源の変更を自動では連鎖させない。

これは新しい条件付き研究の設計であり、T2-0e という継続や #57 の試行上限の解除ではない。
費用は実行予定 backend・並列数・メッシュ生成を含めて測る。Kaggle の92.4分とローカルの時間を直接割って速度改善としない。
R5 の旧27.5分は比較用の要求で、新backend・3Dへ無条件に持ち込まない。変更するなら M4 で理由を登録する。

## 6. 起票する課題と既存 issue の役割

| 課題 | 目的・成果物 | 依存・停止規則 |
| --- | --- | --- |
| [EVAL-VALID-01 #68](https://github.com/ramhachi/CFD_opt_sdf/issues/68) | 原実験への source chain、geometry/TE、trip/Tu、迎角、地上高、span/端板、係数の定義と実験不確かさを表にする。原データが不足なら公式の別ケースを比較し、scope と必要な橋渡しを提案 | M4 #66 の子。条件同定は今可能。新規 CFD は別登録。曖昧な条件を CFD の tuning で埋めない |
| [EVAL-PT-01 #69](https://github.com/ramhachi/CFD_opt_sdf/issues/69) | 固定メッシュ入力と既存 LTS/定常参照の bounded feasibility。solver-free 監査、差分・残差・費用の登録済み判定 | M4 の新研究選択と EVAL-VALID-01。高Re evaluator GO とは別の数値・費用 gate。参照を作れない場合は unresolved |
| [GEOM-03 #70](https://github.com/ramhachi/CFD_opt_sdf/issues/70) | 表現物体に対する幅・void・連結・凍結境界の複合 gate を新データで一度だけ資格化 | M3b に採用する場合の必須前提。M3a の登録 gate は変更しない。失敗時は R0-clean 固定集合または親の再判断 |

新 issue の具体的な受け入れ規則は issue 本文に記録する。計画と起票が今回の作業範囲で、新しい CFD キャンペーン・GPU 測定は開始していない。全 pytest が実行する既存のローカル CPU/Julia 回帰 fixture は、コード検証として別に記録する。
既存 #63 は実行インデックス、#66 は最終判断、#67 は目標物理での最適化、#64/#65 は Re80 の L1/L2 として保持する。
M1/#59、M1'/#60、M2/#61 の完了、B1=v18 の選択を投影へ反映する。新しい親課題・optimizer・共通 framework は追加しない。

## 7. 検証と残る不確かさ

調査では元の結果 analyzer の `--write` を実行しない。T2-0d と UNC-01 の既存 SHA256SUMS を既存 checker で検証し、必要ファイルの hash を残す。
文書のリンク・用語・issue 依存を確認し、compileall、全 pytest（既存 CPU/Julia 回帰 fixture を含む）、diff check の実際の結果を監査記録に保存する。
既存の未回収 log を含む他キャンペーンの manifest までは合格と主張しない。

未解決なのは、FID-01 の最終判定、一次実験系列の同定、代替 gate の新データでの合格、LTS の解・費用、高Re の最終 scope と資源である。
この計画は、それらが判明した順に次の限られた判断をできるよう依存を修正するもので、未検証の方式を採用済みの成功へ置き換えない。
