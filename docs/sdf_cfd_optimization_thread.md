# 符号付き距離場を用いたCFDメッシュ生成と形状最適化

> このファイルは、このスレッド内のユーザー／アシスタント発言を発言順にまとめたものです。  
> 非表示のシステム指示・開発者指示・内部処理は含みません。

---

## User

符号付き距離場を使用した時の効率的なcfdのメッシュの制作方法を考えたい  
論文や研究を徹底的に調べてアイデアをまとめてほしい

---

## Assistant

研究系統を「SDFから直接メッシュ生成」「埋め込み境界／カットセル」「Octree・AMR」「高品質境界層生成」「GPU・自動化」に分け、一次資料を中心に整理します。最後に、車両CFD向けの実装案と研究テーマ候補まで落とし込みます。

---

## Assistant

現時点では、SDFの価値は「表面抽出」よりも、①格子細分化の判定、②内外判定、③法線・曲率・局所厚みの取得、④境界層点列の生成を同じ場で統一できる点にあります。特に、車両形状の反復最適化ではCAD修復と再メッシュの手作業を削減できる可能性が大きいです。

---

## Assistant

# 結論

学生フォーミュラ車両や空力部品のように、**形状変更を繰り返しながら外部流CFDを多数回実行する用途**では、最も有望なのは次の二段構成です。

1. **探索・最適化段階**  
   SDF＋Octree Cartesian格子＋埋め込み境界／カットセル／壁モデルで、ほぼ自動的に高速計算する。

2. **最終評価段階**  
   SDFから生成したオフセット面を用いて境界層プリズムを作り、外側をOctreeベースのHex／Poly格子で埋める。

純粋なCartesianカットセルだけでは高Reynolds数境界層の解像が難しく、NASAでも2026年時点で「自動メッシュ生成の利点を維持しつつ粘性境界層を扱うこと」が主要課題として扱われています。したがって、**SDFを単なる内外判定に使うのではなく、境界層・狭隘部・曲率・解適合を統一する幾何学エンジンとして使う**のが適切です。([nas.nasa.gov](https://www.nas.nasa.gov/pubs/ams/2026/02-05-26.html?utm_source=chatgpt.com))

---

# 1. SDFを使う本質的な利点

形状境界を

\[
\Gamma=\{\boldsymbol{x}\mid \phi(\boldsymbol{x})=0\}
\]

として表し、流体側と固体側で符号を変えると、理想的な符号付き距離関数では

\[
|\nabla \phi|=1
\]

となります。

ここから次の幾何情報をほぼ同じデータ構造で得られます。

\[
\boldsymbol{n}=\frac{\nabla\phi}{|\nabla\phi|}
\]

は壁面法線、

\[
\boldsymbol{x}_{\Gamma}
\simeq
\boldsymbol{x}-\phi(\boldsymbol{x})\nabla\phi(\boldsymbol{x})
\]

は壁面上の最近接点です。さらに、壁面近傍では射影したHessian

\[
\mathbf{P}\nabla^2\phi\mathbf{P},
\qquad
\mathbf{P}=\mathbf{I}-\boldsymbol{n}\boldsymbol{n}^{\mathsf T}
\]

から主曲率と主方向を推定できます。SDFの勾配を用いて壁面法線方向に点や層を進める考え方は、2025年のSDF-guided point-cloud研究でも、複雑形状の境界層解像に利用されています。([royalsocietypublishing.org](https://royalsocietypublishing.org/rspa/article/479/2277/20230080/101078/Orthogonal-signed-distance-coordinates-and-vector?utm_source=chatgpt.com))

また、複数の壁面が等距離になる場所ではSDFの勾配が不連続になり、ridgeやmedial axisが現れます。この性質は欠点でもありますが、逆に、

- 狭い隙間
- プリズム層同士が衝突する場所
- 局所肉厚
- concave cornerでの層停止位置

を検出するために利用できます。([eprints.gla.ac.uk](https://eprints.gla.ac.uk/348425/2/348425.pdf))

---

# 2. 研究動向の整理

## 2.1 SDFそのものを高速・堅牢に作る研究

Roosingらは、三角形表面からCartesian格子上の**狭帯域SDF**をCUDAで生成するCharacteristic/Scan Conversion法を提案しています。全面的な密格子を計算せず、表面近傍だけを処理することで、数万から数百万の表面要素を持つ形状にも対応しています。論文では複雑な車体形状をカットセル化する例も想定されています。([arxiv.org](https://arxiv.org/pdf/1903.00353))

Takedaらは、穴、重複面、法線反転を含む「dirty STL」に対して、Cartesian CFD前処理用のSDFを頑健に生成する方法を示し、NASA Common Research Modelで検証しています。産業形状では「完全なCAD修復をしてからメッシュ生成」するより、SDF側である程度の欠陥を吸収する方向が有効です。([jtam.pl](https://jtam.pl/pdf-165954-89931?filename=89931.pdf&utm_source=chatgpt.com))

OpenVDBは、疎な階層データ構造による狭帯域Level Setの実装候補です。公式の`MeshToVolume`は、閉じた表面を前提としつつ、非多様体、自己交差、縮退面、面法線の不整合を含むメッシュからもSDFを生成できるとしています。([openvdb.org](https://www.openvdb.org/documentation/doxygen/MeshToVolume_8h.html?utm_source=chatgpt.com))

さらに、穴や自己交差を含む不完全形状については、FengとCraneのGeneralized Signed Distanceが、明示的に穴埋めした表面を作らず、拡散方程式に基づいて符号を推定する方法を提案しています。ただし、CFDでは意図した冷却口まで自動的に閉じる危険があるため、これは無条件のCAD修復ではなく、診断・補助用途と考えるべきです。([dl.acm.org](https://dl.acm.org/doi/10.1145/3658220?utm_source=chatgpt.com))

## 2.2 SDF＋Cartesian／カットセル

Cartesianカットセルでは、SDFからセルの内外、壁面交差位置、法線、流体体積率を求めます。形状に沿った複雑な接続情報を作らずに済み、Octree AMRとの相性も良好です。

一方で、境界がセルの端をわずかに切ると極小体積のsmall cut-cellが生成され、陽解法では時間刻みが著しく制限されます。対策として、

- セル結合
- flux redistribution
- state redistribution
- cut-cellだけ陰的に解く
- 全体を陰解法にする

などが研究されています。Xieの2022年の手法は、陰的時間積分と整合的な質量・運動量流束を用い、追加のsmall-cell処理なしで3次元複雑形状を扱っています。([orca.cardiff.ac.uk](https://orca.cardiff.ac.uk/id/eprint/151788/1/1-s2.0-S0045782522004881-main.pdf))

AMReXのEB2は、陰関数またはSTLからEmbedded Boundaryデータベースを構築でき、Boolean演算、移動、回転、拡大縮小も提供しています。ただし、粗いレベルで1セルを境界が複数回切るmulti-valued cellは制約になるため、狭隘部を粗くしすぎない設計が必要です。([amrex-codes.github.io](https://amrex-codes.github.io/amrex/docs_html/EB.html))

Basiliskでも、STLから体積率を生成し、境界と速度場に基づくOctree AMRを組み合わせた実例があります。([basilisk.fr](https://basilisk.fr/sandbox/ghigo/src/test-stl/wind-turbine-flow.c?utm_source=chatgpt.com))

## 2.3 SDF／Octreeから境界適合Hexを作る研究

HybridOctree_Hexは、

1. 曲率と狭隘領域を検出
2. 強平衡Octreeを構築
3. 事前定義された遷移テンプレートでall-hex coreを生成
4. core境界点を元表面の最近接点に接続
5. Jacobian制約付き最適化で品質改善

という構成です。複雑形状に対して手動調整なしで実行できることを示しており、BSD-3-Clauseでコードも公開されています。([arxiv.org](https://arxiv.org/html/2401.05984v2))

ただし、これは一般的なHex体積メッシュ生成技術であり、高アスペクト比のCFD境界層を直接最適化したものではありません。車両CFDでは、これをそのまま使うより、**外側のcore mesh生成部分として利用し、壁面側は別のSDFプリズム層生成器にする**方が合理的です。

## 2.4 SDFによる境界層生成

2025年のZhangらの研究では、壁面点をSDF勾配方向に進めて層状点群を作り、

- convex部では点を挿入
- concave部では点を削除
- 各点を目的とするSDF等値面に再投影

する方式が提案されています。SDF勾配が発散する凸部では点間隔が広がり、収束する凹部では点が衝突するため、挿入・削除は不可欠です。([eprints.gla.ac.uk](https://eprints.gla.ac.uk/348425/2/348425.pdf))

従来のmedial-object型境界層メッシュでも、局所厚みを使ってプリズム／Hex層の成長量を制御することで、単純なadvancing-layerより層厚を安定して管理できることが示されています。([arxiv.org](https://arxiv.org/abs/1901.00992?utm_source=chatgpt.com))

---

# 3. 推奨するメッシュ生成アルゴリズム

## 3.1 保持する幾何情報

単一の\(\phi\)だけでは不十分です。SDFボクセルまたはOctree leafごとに、少なくとも次を持たせます。

\[
\left\{
\phi,\;
\nabla\phi,\;
\mathrm{ID}_{component},\;
\mathrm{ID}_{patch},\;
\boldsymbol{x}_{closest},\;
d_{feature}
\right\}
\]

ここで`patch ID`は翼面、タイヤ、床、ラジエータ入口などの境界条件を保持するために必要です。SDF化して表面を再抽出すると、元CADの面ラベルや鋭角エッジが失われやすいため、**最近接三角形IDとfeature-edge距離をSDFとは別に保存**します。

複数部品については、

\[
\phi_{\mathrm{union}}=\min_i \phi_i
\]

だけを保存せず、最小値と2番目に小さい値、対応する部品IDも保持します。これにより、翼と翼端板、タイヤと地面、複数エレメント間のgapを検出できます。

## 3.2 疎な狭帯域SDF

全解析領域に高解像度SDFを作る必要はありません。帯域幅を

\[
W=
\max
\left(
T_{\mathrm{BL}},
N_s h_{\mathrm{surface}},
W_{\mathrm{cut}}
\right)
\]

とし、\(|\phi|<W\)だけをOpenVDBまたはOctree上に保持します。

- \(T_{\mathrm{BL}}\)：予定する境界層メッシュ総厚
- \(h_{\mathrm{surface}}\)：表面近傍セル幅
- \(N_s\)：SDF補間に必要な安全セル数
- \(W_{\mathrm{cut}}\)：カットセル幾何処理に必要な幅

表面近傍はBVHや空間binによる三角形最近接計算で正確に求め、遠方はFast Sweeping等で伝播させます。三角形数と格子点数が大きい場合はGPU化し、形状最適化では変更された部品のbounding box周辺のbrickだけ再生成します。GPU-nativeなOctree voxelizationとAMRを一体化する研究も2025年に提示されています。([arxiv.org](https://arxiv.org/html/2512.01251v1))

## 3.3 SDFから目標セル幅を決める

単純な「壁からの距離」だけでなく、複数の制約を合成します。

### 距離制約

\[
h_d(\boldsymbol{x})
=
\operatorname{clip}
\left(
h_{\min}+a|\phi(\boldsymbol{x})|,
h_{\min},
h_{\max}
\right)
\]

壁面から離れるほど徐々に粗くします。

### 曲率制約

局所的な幾何誤差許容値を\(\varepsilon_g\)、最大主曲率を\(\kappa_{\max}\)とすると、円弧と弦の近似から初期目安として

\[
h_\kappa
\approx
\sqrt{\frac{8\varepsilon_g}{|\kappa_{\max}|+\epsilon}}
\]

を使えます。

### gap制約

対向面間距離を\(g\)、gap内に最低\(N_g\)セル必要とすれば、

\[
h_g=\frac{g}{N_g}
\]

です。最初の研究実装では\(N_g=6\sim10\)程度をパラメータスタディし、gap流量や圧力差の収束から決めるのが妥当です。

### feature-edge制約

\[
h_f=f(d_{\mathrm{feature}})
\]

を入れ、翼後縁、フロア端部、翼端板角部などを別途細分化します。

最終的には

\[
h_{\mathrm{geo}}
=
\min
\left(
h_d,h_\kappa,h_g,h_f,h_{\max}
\right)
\]

とし、Octreeレベルを

\[
l(\boldsymbol{x})
=
\left\lceil
\log_2\frac{h_0}{h_{\mathrm{geo}}(\boldsymbol{x})}
\right\rceil
\]

で決定します。隣接leafは2:1 balanceにします。

---

# 4. SDF境界層メッシュ

壁面上の初期点または表面メッシュ節点を、SDFの等値面

\[
\phi=d_j
\]

へ移動して層を生成します。

第1層高さを\(\Delta n_1\)、成長率を\(r\)、層数を\(N\)とすると、

\[
\Delta n_j=\Delta n_1r^{j-1},
\qquad
T_{\mathrm{BL}}
=
\Delta n_1\frac{r^N-1}{r-1}
\]

です。

ただし、層厚は局所feature size \(L_{\mathrm{LFS}}\) と曲率半径によって制限します。

\[
T_{\mathrm{BL}}
\le
\min
\left(
\beta_g L_{\mathrm{LFS}},
\frac{\beta_\kappa}{|\kappa_{\max}|+\epsilon},
T_{\mathrm{physical}}
\right)
\]

ここで、

- \(L_{\mathrm{LFS}}\)：最近傍medial axisまでの距離
- \(T_{\mathrm{physical}}\)：物理的に必要な境界層厚
- \(\beta_g,\beta_\kappa<1\)：安全率

です。

さらに各層で、

- SDF勾配が発散する凸部：点／面を分割
- SDF勾配が収束する凹部：点／面を結合または層を停止
- \(\nabla\phi\)が不安定なmedial ridge：成長停止
- 鋭角部：feature normalを使用
- 各成長後：Newton反復で\(\phi=d_j\)へ再投影

を行います。

この仕組みが、既存のsnappyHexMeshのlayer additionより研究価値の高い部分です。snappyHexMeshも最近接面までの距離やmedial-axis型の制御を使いますが、SDF場として曲率、gap、複数部品ID、局所feature sizeを一貫して扱う構造ではありません。([doc.openfoam.com](https://doc.openfoam.com/2312/tools/pre-processing/mesh/generation/snappyhexmesh/layers/?utm_source=chatgpt.com))

---

# 5. 解適合との統合

SDFで生成できるのはあくまで**幾何学的に妥当な初期メッシュ**です。wake、剥離剪断層、タイヤ後流、翼端渦は形状距離だけでは予測できません。

したがって粗い初期計算後に、

\[
h_{\mathrm{target}}
=
\min
\left(
h_{\mathrm{geo}},
h_{\omega},
h_{\nabla p},
h_Q,
h_{\mathrm{adj}}
\right)
\]

として再適合します。

- \(h_\omega\)：渦度
- \(h_{\nabla p}\)：圧力勾配またはHessian
- \(h_Q\)：Q criterion等
- \(h_{\mathrm{adj}}\)：抗力、ダウンフォース、前後空力バランスに対する随伴重み付き残差

特に最適化では、単なる渦度ベースAMRより、**目的関数に効く領域だけを細分化する随伴ベース適合**が有効です。Cart3DではEmbedded-Boundary Cartesian格子と随伴誤差推定を組み合わせ、出力誤差を直接低減する自動適合が実装されています。([nas.nasa.gov](https://www.nas.nasa.gov/publications/software/docs/cart3d/pages/publications/AIAA_2019-3488_mn_dlr_ma.pdf?utm_source=chatgpt.com))

実装上は、異方性非構造格子ならmetric tensorの交差を使います。

\[
\mathbf{M}
=
\mathbf{M}_{\mathrm{geo}}
\cap
\mathbf{M}_{\mathrm{flow}}
\cap
\mathbf{M}_{\mathrm{adj}}
\]

Octreeの場合は異方性を直接表現しにくいため、各条件が要求する最大refinement levelを採用します。

---

# 6. Formula TMU向けの現実的な構成

## 段階A：既存OpenFOAMを維持した研究試作

まずはソルバを作り直さず、次の前処理を実装するのが妥当です。

```text
STEP / STL
   ↓
表面三角形化・patch ID保持
   ↓
OpenVDB narrow-band SDF
   ↓
曲率・gap・feature距離・medial ridge計算
   ↓
OpenFOAM cellSet / refinement region生成
   ↓
snappyHexMesh
   ↓
粗計算
   ↓
渦度・圧力・目的関数感度による再細分化
```

OpenFOAMにはSDFベースIBMの公開実装`SdfIBM`や、Level Setとvolume penalizationを組み合わせた研究実装があります。これらは境界層精度の最終解ではありませんが、低忠実度スクリーニング環境の出発点になります。([github.com](https://github.com/ChenguangZhang/sdfibm?utm_source=chatgpt.com))

この段階では、SDFから直接最終メッシュを出す必要はありません。SDFで

- refinement level
- wake refinement領域
- gap refinement
- layer成長禁止領域
- patchごとの層厚

を自動決定するだけでも、手動設定は相当削減できます。

## 段階B：独自のSDFプリズム＋Octree core

次に、

```text
SDF zero surface
   ↓
surface triangle / quad mesh
   ↓
SDF iso-surfaceに沿ったプリズム層
   ↓
Octree all-hex core
   ↓
pyramid / polyhedron transition
```

を実装します。

core部分にはHybridOctree_Hexの考え方を流用でき、SDF層とcoreの間だけpolyhedral transitionにする構成が現実的です。

## 段階C：探索用Embedded Boundaryソルバ

トポロジー変更を含む空力最適化では、毎回プリズム層を作ると計算前処理が重くなります。そこで探索用には、

- AMReX EB2
- Basilisk
- OpenFOAM SDF-IBM
- 独自Cartesian cut-cell

のいずれかを使い、最終候補だけbody-fitted meshで再計算します。

---

# 7. 研究テーマとして有望な順序

## 1位：Medial-axis-aware SDF境界層生成

**題目例**

> 符号付き距離場と局所feature sizeを用いた複雑車両形状向け自動境界層メッシュ生成

新規性の中心は、

- SDF等値面による層生成
- medial ridgeによる衝突予測
- convex／concaveでの局所再接続
- gap幅に応じた層厚・セル幅制御
- 翼後縁や交差部のfeature保持

です。

実装難度と研究価値のバランスが最も良く、OpenFOAMにも接続しやすいテーマです。

## 2位：形状最適化用の差分更新SDFメッシャ

各設計案でSDF全体を再計算せず、

\[
\Omega_{\mathrm{update}}
=
\mathrm{BBox}
\left(
\Gamma_{\mathrm{old}}
\triangle
\Gamma_{\mathrm{new}}
\right)
\oplus W
\]

の領域だけ再構築します。

翼型、gap、overlap、翼端板形状を変更した場合に、

- SDF更新時間
- Octree更新時間
- 全再メッシュとの差
- 形状変更量に対する計算量

を評価します。GPU narrow-band SDFとの相性が良いテーマです。

## 3位：SDF幾何metricと随伴metricの統合

\[
\mathbf{M}
=
\mathbf{M}_{\mathrm{SDF}}
\cap
\mathbf{M}_{\mathrm{adjoint}}
\]

により、「形状を正確に表すためのメッシュ」と「ダウンフォース／抗力を正確に求めるためのメッシュ」を統一します。

これは理論的価値が高い一方、随伴ソルバとメッシュ適合器の両方が必要なので実装規模は大きくなります。

## 4位：dirty CADに対するCFD誤差保証

SDFは穴や法線異常を吸収できますが、修復した形状が物理的に正しいとは限りません。

そこで、

- 元STL
- 修復後SDF
- 再抽出表面

間のHausdorff距離、体積変化、開口面積変化を測り、CFD出力の不確かさまで評価します。

---

# 8. 評価方法

比較対象は最低でも次の3系統が必要です。

| 系統 | 基準 |
|---|---|
| 従来法 | snappyHexMeshの手動refinement |
| 提案法A | SDFによる自動refinement＋snappyHexMesh |
| 提案法B | SDFプリズム＋Octree core |
| 探索用 | SDF＋IBM／cut-cell |

形状は次の順で複雑化します。

1. 円柱・球  
2. NACA翼型  
3. 2エレメント翼  
4. 3次元翼＋翼端板  
5. タイヤ＋地面  
6. FSAEフルカー

評価指標は、

### 前処理

- メッシュ生成時間
- peak memory
- ユーザー操作回数
- 失敗率
- 差分形状更新時間

### 幾何

- Hausdorff距離
- 法線誤差
- 表面積・体積誤差
- gap保持誤差
- feature-edge位置誤差

### メッシュ

- セル数
- non-orthogonality
- skewness
- Jacobian／scaled Jacobian
- layer coverage
- 第1層高さ誤差
- 層間成長率
- 負体積セル数

### CFD

- \(C_L,C_D\)
- 圧力分布
- 壁面摩擦
- 剥離位置
- wake速度欠損
- 反復収束性
- 格子収束率
- 単位精度当たり計算時間

で比較します。

---

# 最終提案

Formula TMUの空力最適化を主用途とするなら、研究開発順序は次が最も合理的です。

```text
第1段階
OpenVDBでSTL→疎なSDF
曲率・gap・feature距離からOpenFOAM refinementを自動生成

第2段階
SDF等値面に沿う境界層プリズム生成
medial axisによる衝突・層停止制御

第3段階
Octree coreと接続して完全自動ハイブリッドメッシャ化

第4段階
粗計算結果または随伴解によるsolution adaptation

第5段階
形状差分に対するSDF・メッシュの局所更新
```

研究上の中核は、**「SDFで表面を再構築すること」ではなく、「SDFの勾配・Hessian・medial ridge・部品間距離を用いて、境界層とOctree細分化を一貫して決定すること」**です。これなら、既存のsnappyHexMeshを置換せずに研究を開始でき、最終的にはトポロジー変更を含む空力最適化用の自動CFD基盤へ発展させられます。

---

## User

このメッシュの目的は随伴法のような最適化アルゴリズムを用いて、形状最適化をかけることを目的としています(揚抗比の制限ありダウンフォース最適化、または抗力最小化)  
また、レギュレーションを考えて物体が存在できる部分を拘束することと、ひとつなぎ(バラバラな物体は存在できない)ことを制限として加える必要があります

このことを考えて有効なアルゴリズムやシステムを考えてほしいです

---

## Assistant

前提を「外部流の形状最適化」「随伴感度」「SDF/level-set表現」「レギュレーション領域拘束」「単一連結性」に固定して、候補手法を比較します。特に、単なる形状更新ではなく、位相変化を許すかどうかで最適な構成が大きく変わるため、その分岐も明示します。

---

## Assistant

重要な分岐が見えてきました。今回の要件では、通常の「表面節点を動かす形状最適化」だけでは単一連結性を保証しにくく、**設計領域内のSDF/level-set自体を設計変数にしつつ、連結性を別のPDEまたはグラフ制約で監視する方式**が適しています。

---

## Assistant

# 推奨構成

今回の要件には、単純な「SDF表面を随伴感度で移動する形状最適化」より、次のハイブリッド構成が適しています。

> **規則領域を固定SDFで表現し、接続先となるルート領域を指定したうえで、粗いトポロジー探索と高精度なSDF形状最適化を分離する。**

具体的には、

1. **トポロジー探索**  
   固定格子上の密度／phase-field＋Brinkman penalization
2. **単一連結性制約**  
   root-connected virtual diffusion constraint
3. **形状精密化**  
   SDF＋sharp immersed boundary／cut-cell＋離散随伴
4. **最終検証**  
   body-fitted RANSメッシュ

という四層構成です。

高Reynolds数の外部流トポロジー最適化では、Darcy項が乱流モデルや壁距離に影響するため、通常のSSTモデルをそのまま使うのは危険です。修正SSTなどによる研究例はありますが、Darcyモデルでは壁面直近の剪断応力に依然として誤差が残るため、最終形状まで密度法だけで決定しない方が安全です。([arxiv.org](https://arxiv.org/pdf/2207.11711))

---

# 1. 最適化問題の定義

ダウンフォース係数を

\[
C_{\mathrm{DF}}=-C_L>0
\]

と定義します。

## 1.1 ダウンフォース最大化＋効率制約

揚抗比を直接割り算で制約すると、抗力が小さい領域で数値的に不安定になるため、

\[
\frac{C_{\mathrm{DF}}}{C_D}\ge E_{\min}
\]

を

\[
g_E(\phi)
=
E_{\min}C_D(\phi)-C_{\mathrm{DF}}(\phi)
\le 0
\]

と書き換えます。

最適化問題は、

\[
\begin{aligned}
\min_{\phi}\quad&
J(\phi)=-C_{\mathrm{DF}}(\phi)
\\
\mathrm{s.t.}\quad&
E_{\min}C_D-C_{\mathrm{DF}}\le0,
\\
&
g_{\mathrm{conn}}(\phi)\le0,
\\
&
\Omega_s(\phi)\subseteq D_{\mathrm{allow}},
\\
&
g_{\mathrm{length}}(\phi)\le0,
\\
&
R(\boldsymbol{q},\phi)=0
\end{aligned}
\]

です。

ここで、

- \(\phi\)：形状を表すSDFまたはlevel-set
- \(\Omega_s=\{\boldsymbol{x}\mid\phi<0\}\)：固体領域
- \(D_{\mathrm{allow}}\)：レギュレーション上、物体を配置できる領域
- \(R=0\)：RANSなどのCFD残差

です。

## 1.2 抗力最小化

抗力最小化では、ダウンフォースの下限制約にします。

\[
\begin{aligned}
\min_{\phi}\quad&
C_D(\phi)
\\
\mathrm{s.t.}\quad&
C_{\mathrm{DF,min}}-C_{\mathrm{DF}}(\phi)\le0
\end{aligned}
\]

この方が、

\[
J=C_D-\lambda C_{\mathrm{DF}}
\]

のような重み付き和よりも、重み係数による解の変化を避けられます。

外部流のトポロジー最適化で、揚力最大化、抗力最小化、抗力上限制約を組み合わせた研究例は既にあり、2025年の研究では流体体積制約と抗力制約を含む外部流問題が扱われています。([repositorio.usp.br](https://repositorio.usp.br/directbitstream/f60efc2b-7a0c-43d4-a3c7-f4a0813ee58e/3271200_manuscrito.pdf))

## 1.3 実車用途で追加すべき制約

ダウンフォース総量だけでは、最適化が極端な空力中心位置を選ぶ可能性があります。したがって、少なくとも次を追加するべきです。

\[
x_{\mathrm{CoP,min}}
\le x_{\mathrm{CoP}}
\le x_{\mathrm{CoP,max}}.
\]

または前後配分

\[
\beta_{\min}
\le
\frac{C_{\mathrm{DF,front}}}{C_{\mathrm{DF,total}}}
\le
\beta_{\max}.
\]

さらに、複数条件を用います。

\[
J=
-\sum_{k=1}^{N_{\mathrm{op}}}
w_k C_{\mathrm{DF}}^{(k)}
\]

対象条件としては、

- 基準車高
- ピッチ状態
- ロール状態
- ヨー角
- 低速／高速
- 操舵状態

を設定し、効率制約は各条件で満たすか、KS関数で最悪条件を集約します。

---

# 2. レギュレーション領域の表現

設計対象のSDFとは別に、規則を表す固定SDFを持たせます。

\[
\phi_{\mathrm{allow}}(\boldsymbol{x})
\]

を、

- 内側：負
- 外側：正

とします。

設計領域は

\[
D_{\mathrm{allow}}
=
\{\boldsymbol{x}\mid
\phi_{\mathrm{allow}}(\boldsymbol{x})\le0
\}
\]

です。

データとしては最低限、次の三領域に分離します。

\[
D
=
D_{\mathrm{design}}
\cup
D_{\mathrm{forbidden}}
\cup
D_{\mathrm{fixed}}
\]

- \(D_{\mathrm{design}}\)：最適化可能
- \(D_{\mathrm{forbidden}}\)：常に流体、物体配置禁止
- \(D_{\mathrm{fixed}}\)：取付部や既存車体などの固定固体

## ロバストな領域拘束

製造誤差やSDF離散化誤差を考えると、公称形状ではなく膨張形状を使うべきです。

SDFでは固体の膨張領域を

\[
\Omega_s^{\mathrm{dil}}
=
\{\boldsymbol{x}\mid\phi(\boldsymbol{x})<r_{\mathrm{rule}}\}
\]

と簡単に定義できます。

これに対して

\[
\Omega_s^{\mathrm{dil}}
\subseteq D_{\mathrm{allow}}
\]

を要求します。

数値制約として書くなら、

\[
g_{\mathrm{rule}}
=
\int_D
\chi_{\mathrm{dil}}
(1-m_{\mathrm{allow}})
\,d\Omega
\le
\varepsilon_{\mathrm{rule}}
\]

です。

ただし、固定された規則領域については、最適化制約にするよりも、

- 禁止領域では設計変数を更新しない
- 更新後に必ず流体へ投影する
- 許可領域境界の内側に安全マージンを置く

という**ハードマスク処理**の方が確実です。

複数のレギュレーション領域は、各規則のSDFの交差として管理します。固定されたマスクなので、滑らかなBoolean演算にこだわる必要はありません。

---

# 3. 「ひとつなぎ」を保証する方法

## 3.1 単なる連結成分数の検査では不十分

更新後のボクセルに対してflood fillを実行すれば、連結成分数は判定できます。しかし、これは離散的で微分不能なので、随伴勾配を使った最適化制約には直接組み込めません。

また、単に「連結している」だけでは、

- 1セル幅の細い接続
- 製造不能な針状ブリッジ
- 数値的な中間密度による擬似的接続

が発生します。

したがって、

1. 微分可能な連結性制約
2. 最小接続厚さ
3. 離散的な最終検査

を組み合わせます。

---

## 3.2 推奨：root-connected virtual diffusion

車体や取付部に必ず接続する固定領域を

\[
D_{\mathrm{root}}\subset D_{\mathrm{fixed}}
\]

として指定します。

形状の固体指示関数を

\[
\chi(\phi)=H_\epsilon(-\phi)
\]

とし、仮想的な熱伝導問題を解きます。

\[
-\nabla\cdot
\left(
k(\chi)\nabla T
\right)
=
q\chi
\quad\mathrm{in}\ D_{\mathrm{allow}}
\]

境界条件は、

\[
T=0
\quad\mathrm{on}\ \Gamma_{\mathrm{root}},
\]

\[
\boldsymbol{n}\cdot k\nabla T=0
\quad\mathrm{on\ other\ boundaries}.
\]

熱伝導率は、

\[
k(\chi)
=
k_{\mathrm{void}}
+
(k_{\mathrm{solid}}-k_{\mathrm{void}})\chi
\]

とし、

\[
k_{\mathrm{solid}}\gg k_{\mathrm{void}}
\]

とします。

固体内に仮想熱源があり、rootだけが熱を逃がせる構成です。

- rootに接続した固体：温度が低い
- rootから分離した固体：仮想熱が逃げず、高温になる

したがって、

\[
g_{\mathrm{conn}}
=
\operatorname{KS}_\rho(T)-T_{\max}
\le0
\]

とすれば、全固体をrootへ接続する方向に最適化できます。

Virtual Temperature MethodやPoisson方程式型の制約は、固体島・空洞島の検出に使われており、比較研究では計算コスト面で有利な手法の一つと評価されています。ただし、境界条件の置き方が最終形状に強く影響するため、rootの選定が重要です。([arxiv.org](https://arxiv.org/html/2501.09402v1))

### 重要な注意

複数の取付部すべてを

\[
T=0
\]

にすると、

- 部品Aが取付部1に接続
- 部品Bが取付部2に接続
- AとBは相互に非接続

でも制約を満たす可能性があります。

したがって、**単一のroot領域を決め、すべての固体をそのrootへ接続させる**必要があります。複数の取付点を必須とする場合は、すべての取付点が同一rootに接続されるよう、各取付点からの接続制約を追加します。

---

## 3.3 最小厚さを含む二重連結性制約

SDFの利点は、侵食形状を直接定義できることです。

公称固体：

\[
\Omega_s
=
\{\phi<0\}
\]

侵食固体：

\[
\Omega_s^{\mathrm{ero}}
=
\{\phi<-r_{\min}\}
\]

とします。

対応する指示関数は、

\[
\chi_0=H_\epsilon(-\phi),
\]

\[
\chi_{\mathrm{ero}}
=
H_\epsilon(-\phi-r_{\min}).
\]

そして二つの連結性問題を解きます。

\[
g_{\mathrm{conn}}(\chi_0)\le0
\]

\[
g_{\mathrm{conn}}(\chi_{\mathrm{ero}})\le0
\]

意味は次のとおりです。

- 公称形状の制約：小さな分離部品を禁止
- 侵食形状の制約：細すぎる接続を禁止

侵食後にも接続が残れば、接続部にはおおむね

\[
2r_{\min}
\]

以上の厚さが必要になります。

これは単なる連結性制約より重要です。連結性だけを課すと、最適化は空力的に有利な物体を極細の棒でrootに接続する可能性があるためです。

---

## 3.4 スペクトルグラフ制約

設計セルをノード、隣接関係をエッジとする重み付きグラフを構成し、グラフLaplacian

\[
\mathbf{L}=\mathbf{D}-\mathbf{W}
\]

の第2固有値

\[
\lambda_2
\]

を用いる方法もあります。

理想的な二値グラフなら、

\[
\lambda_2>0
\]

はグラフが連結であることを意味します。

制約は、

\[
g_{\mathrm{spec}}
=
\lambda_{\min}
-
\lambda_2(\mathbf{L}(\chi))
\le0
\]

です。

第2固有値を使う連続的な連結性モデルは2D・3Dトポロジー最適化で提案されています。([link.springer.com](https://link.springer.com/article/10.1007/s00158-023-03526-8))

ただし、

- 反復ごとに固有値問題が必要
- 固有値重複付近で感度が不安定
- 中間密度の細い経路でも\(\lambda_2>0\)になり得る
- 3次元大規模問題ではコストが高い

という問題があります。

したがって本システムでは、

> virtual diffusionを主制約、スペクトル法を定期的な検査または比較対象

にするのが適切です。

連結性手法の2025年の比較研究でも、スペクトルグラフ制約は比較的一貫した結果を示す一方、すべての問題に対して唯一最良の手法はなく、連結性制約自体が最終形状に大きく影響するとされています。([arxiv.org](https://arxiv.org/html/2501.09402v1))

---

# 4. 推奨する二段階最適化

## 第1段階：トポロジー探索

固定Cartesian／Octree格子上に連続設計変数

\[
0\le \rho(\boldsymbol{x})\le1
\]

を持たせます。

- \(\rho=0\)：流体
- \(\rho=1\)：固体

とし、Navier–Stokes方程式にBrinkman／Darcy項を追加します。

\[
\boldsymbol{R}_{\mathrm{mom}}
=
\cdots+
\alpha(\rho)\boldsymbol{u}=0
\]

\[
\alpha(0)\simeq0,
\qquad
\alpha(1)=\alpha_{\max}.
\]

この段階では、

- 形状の大まかな配置
- 翼型的な物体の発生
- Gurney flap的な突起
- 流路を誘導する構造

を探索します。

2025年の外部流研究では、固体・流体分布を設計変数とし、揚力、抗力、エネルギー散逸、渦度を目的関数または制約として扱い、感度を自動微分で取得しています。([repositorio.usp.br](https://repositorio.usp.br/directbitstream/f60efc2b-7a0c-43d4-a3c7-f4a0813ee58e/3271200_manuscrito.pdf))

### トポロジー探索で必要な正則化

\[
J_{\mathrm{reg}}
=
\gamma_A
\int_D
\delta_\epsilon(\phi)
|\nabla\phi|
\,d\Omega
\]

のような表面積ペナルティを加えます。

これにより、

- 格子スケールの凹凸
- 鋸歯状表面
- 過度に複雑な枝分かれ
- 非物理的な高周波形状

を抑えます。

さらに、Heaviside投影とDarcy係数を段階的に強くします。

```text
初期：
広い界面、弱いDarcy抵抗、緩い連結制約

中期：
界面を薄くする、Darcy抵抗を増加

終期：
ほぼ二値化、侵食形状にも連結制約
```

最適化器は、多数の設計変数と少数の大域制約に適したGCMMAを第一候補とします。

---

## 第2段階：SDFによるsharp-interface形状最適化

第1段階の結果から

\[
\rho=\rho_{\mathrm{iso}}
\]

の等値面を抽出し、SDF

\[
\phi(\boldsymbol{x})
\]

へ変換します。

流れ解析は、

- ghost-cell immersed boundary
- sharp cut-cell
- XFEM
- body-conformal cut finite volume

のいずれかに切り替えます。

ここではDarcyの中間密度を使わず、

\[
\phi=0
\]

を明確な壁面として扱います。

NASAの2024年の研究では、ghost-node immersed boundaryと離散随伴を組み合わせて、翼の抗力低減最適化まで実施しています。source-term型IBMでは随伴方程式の収束が悪化した一方、ghost-node型はより良好な収束を示しました。([ntrs.nasa.gov](https://ntrs.nasa.gov/api/citations/20240008173/downloads/8173-Lowe_Aviation2024_Paper_final.pdf))

ただし、immersed boundaryでは、

- 前縁
- 翼と翼端板の接合部
- 高曲率部
- 壁面剪断応力
- 抗力評価

に誤差が残ることがあります。NASAの比較でも、圧力分布は比較的良好だった一方、前縁や接合部のskin friction、粗い格子での抗力に差が確認されています。([ntrs.nasa.gov](https://ntrs.nasa.gov/api/citations/20240008173/downloads/8173-Lowe_Aviation2024_Paper_final.pdf))

したがって、sharp IBMは最適化用、body-fittedメッシュは最終検証用と分離します。

---

# 5. SDFの更新方法

随伴法から得られる形状感度を

\[
G_J(\boldsymbol{x})
=
\frac{dJ}{d\Gamma}
\]

とします。

各制約の感度を含めた拡張感度は、

\[
G_{\mathrm{aug}}
=
G_J
+
\lambda_EG_E
+
\lambda_{\mathrm{conn}}G_{\mathrm{conn}}
+
\lambda_{\mathrm{rule}}G_{\mathrm{rule}}
+
\lambda_{\mathrm{struct}}G_{\mathrm{struct}}.
\]

法線速度を

\[
V_n
=
-\mathcal{F}
\left[
G_{\mathrm{aug}}
+\gamma_\kappa\kappa
\right]
\]

とし、Hamilton–Jacobi方程式

\[
\frac{\partial\phi}{\partial\tau}
+
V_n|\nabla\phi|
=0
\]

で更新します。

\(\mathcal{F}\)はHelmholtzフィルタなどの空間フィルタ、\(\kappa\)は曲率です。

更新後には、

1. 禁止領域を流体へ投影
2. 固定領域を固体へ投影
3. SDF再初期化
4. 連結成分検査
5. 最小厚さ検査
6. 許可領域検査

を実施します。

---

# 6. メッシュの扱い

## 6.1 最適化中に毎回リメッシュしない

メッシュを毎反復変更すると、

- 目的関数がメッシュ変更で不連続になる
- 随伴感度と実際の目的関数変化が一致しにくい
- quasi-Newton履歴が壊れる
- 微小形状変更よりメッシュ誤差が大きくなる

という問題が起きます。

したがって、**mesh epoch方式**を推奨します。

```text
メッシュ固定
    ↓
10～30回程度の形状更新
    ↓
primal＋adjoint誤差からメッシュ適合
    ↓
SDFと流れ場を転送
    ↓
最適化器の履歴をリセット
    ↓
次のepoch
```

揚抗力問題に対して、reaction–diffusion型トポロジー最適化と等方・異方・body-fittedメッシュ適合を組み合わせる研究も実施されています。([link.springer.com](https://link.springer.com/article/10.1007/s00158-022-03314-w))

## 6.2 初期メッシュ

設計領域内では、形状がまだ存在しない場所にも物体が成長する可能性があります。そのため、

- 設計可能領域全体：中程度に細かい
- 現在の\(\phi=0\)近傍：さらに細かい
- wake候補領域：流れ方向に細かい
- 地面・タイヤ・翼端・gap：最細
- 遠方場：粗い

という構成にします。

SDF距離だけでなく、随伴重み付き残差

\[
\eta_K^{\mathrm{adj}}
\]

を使い、

\[
h_K
=
\min
\left(
h_{\mathrm{SDF}},
h_{\mathrm{flow}},
h_{\mathrm{adj}}
\right)
\]

として適合させます。

---

# 7. 全システム構成

```text
レギュレーションCAD・車両CAD
        │
        ├─ allowed-region SDF
        ├─ forbidden-region SDF
        ├─ fixed-solid SDF
        └─ root/mount region
        │
        ▼
設計場 ρ または φ
        │
        ├─ nominal geometry
        ├─ eroded geometry
        └─ dilated geometry
        │
        ▼
固定Octree CFD格子
        │
        ├─ primal RANS
        ├─ objective/constraint evaluation
        ├─ flow adjoints
        └─ virtual-diffusion connectivity PDE
        │
        ▼
感度統合
        │
        ├─ aerodynamic sensitivity
        ├─ connectivity sensitivity
        ├─ rule-envelope sensitivity
        ├─ minimum-thickness regularization
        └─ optional structural sensitivity
        │
        ▼
GCMMA / augmented Lagrangian
        │
        ▼
設計変数更新
        │
        ├─ hard regulation projection
        ├─ SDF reinitialization
        ├─ flood-fill validation
        └─ line search
        │
        ▼
定期的なmesh adaptation
        │
        ▼
sharp-interface shape refinement
        │
        ▼
body-fitted RANSによる最終検証
```

---

# 8. 推奨する制約セット

実装時には次の組合せが妥当です。

| 制約 | 実装 |
|---|---|
| ダウンフォース効率 | \(E_{\min}C_D-C_{\mathrm{DF}}\le0\) |
| 抗力最小化時の性能 | \(C_{\mathrm{DF,min}}-C_{\mathrm{DF}}\le0\) |
| レギュレーション | 膨張SDFを許可領域内にハード投影 |
| 単一連結 | nominal形状にroot diffusion |
| 接続部最小厚さ | eroded形状にもroot diffusion |
| 最小部材寸法 | SDF erosion／dilation＋フィルタ |
| 表面複雑度 | 表面積または曲率ペナルティ |
| 空力中心 | CoPまたは前後配分制約 |
| 強度 | 線形弾性complianceまたは変位制約 |
| 最終離散検査 | flood fillによる連結成分数＝1 |

特に強度制約は有効です。連結性と最小厚さだけでは、空力荷重に耐えない細い支持部が残る可能性があります。

簡易構造解析として、

\[
\mathbf{K}(\chi)\boldsymbol{d}
=
\boldsymbol{f}_{\mathrm{aero}}
\]

を解き、

\[
g_{\mathrm{comp}}
=
\frac{
\boldsymbol{f}_{\mathrm{aero}}^\mathsf{T}\boldsymbol{d}
}{
C_{\max}
}-1
\le0
\]

を入れれば、空力的な「極細接続」をかなり抑制できます。

---

# 9. 実装の優先順位

## Phase 1：2次元検証

- 固定Cartesian格子
- laminar Navier–Stokes
- density／Brinkman
- 抗力最小化＋揚力下限
- 許可領域マスク
- nominal root-connectivity
- flood-fill検査

まず、円柱またはNACA形状から開始します。

## Phase 2：ロバスト連結性

- eroded形状の連結性制約
- 最小厚さ
- surface-area penalty
- mesh epoch
- GCMMA continuation

ここで「細い棒で接続する解」が除去できるかを確認します。

## Phase 3：高Reynolds数

- modified SSTまたはsharp IBM
- 離散随伴
- 圧力抗力と摩擦抗力の個別評価
- body-fitted結果との比較

高Reynolds数のDarcy型トポロジー最適化では、乱流場・壁距離・Darcy係数を整合させる必要があることが既存研究で示されています。([arxiv.org](https://arxiv.org/pdf/2207.11711))

## Phase 4：3次元車両部品

- フロア
- ディフューザ
- サイド部品
- ウイング
- 翼端板
- タイヤ近傍

へ拡張します。

---

# 最終的なアルゴリズム案

最も実用性が高い構成は次です。

\[
\boxed{
\text{密度型トポロジー探索}
\rightarrow
\text{root連結制約}
\rightarrow
\text{SDF変換}
\rightarrow
\text{sharp-IBM随伴形状最適化}
}
\]

連結性については、

\[
\boxed{
\text{nominal root diffusion}
+
\text{eroded root diffusion}
+
\text{flood-fill検査}
}
\]

を採用します。

レギュレーションについては、

\[
\boxed{
\Omega_s^{\mathrm{dil}}
\subseteq
D_{\mathrm{allow}}
}
\]

という膨張形状に対するハード拘束にします。

この構成であれば、

- 形状・ある程度の位相変化を探索できる
- バラバラな空力物体を排除できる
- 極細接続も排除できる
- レギュレーション領域を厳密に守れる
- 固定格子で再メッシュ回数を削減できる
- 最終的には明確な壁面を持つSDF形状へ収束できる

という要件を同時に満たせます。

---

## User

このスレッドのすべての会話記録をmdファイルに直して
