# 揚抗比制限付き外部流形状最適化に対する実装志向の研究設計

## 要旨

このテーマに対して、いちばん筋が良いのは、**位相変化を許す固定格子トポロジー探索**と、**SDFを使う sharp-interface 形状精密化**と、**最終の body-fitted 検証**を明確に分ける三段構成です。具体的には、まず固定 Cartesian／Octree 格子上で density あるいは level-set／SDF によるトポロジー探索を行い、揚抗比制約・レギュレーション領域制約・単一連結制約を入れて粗い位相を見つけます。次にその解を SDF に落として、ghost-node IBM あるいは implicit cut-cell で sharp-interface の随伴最適化に進めます。最後に、SDF から境界層プリズムと Octree/Hex core を作って body-fitted RANS で再評価します。外部流トポロジー最適化の近年研究は、Brinkman 系で lift/drag を直接扱えること、ただし高 Reynolds 数では乱流モデルや壁距離の整合が必要であることを示しています。また NASA の 2024 年の immersed-boundary＋離散随伴研究は、ghost-node 系が source-term 系より最適化向きであることを示しており、SDF-guided の境界層生成や minimum-distance-field ベースのプリズム生成は、SDF を境界層メッシュへつなぐ実装ルートとしてかなり現実的です。citeturn26view0turn26view4turn7search4turn14view0turn14view2turn12view2turn12view4turn14view9

代表長さ 2 m、流速 11 m/s、標準大気の密度 1.229 kg/m³・粘性係数 \(1.73\times10^{-5}\,\mathrm{Pa\cdot s}\) を使うと、代表 Reynolds 数はおよそ \(1.56\times 10^6\) です。したがって、ここで考える流れは Stokes 的な「低 Reynolds 数」というより、**外部空力としては中程度から高めで、壁面摩擦・剥離・乱流モデルの選択が依然として重要**な領域だと扱う方が安全です。そのため、Brinkman 型トポロジー探索を最終解にせず、sharp-interface か body-fitted での再評価をパイプラインに組み込むべきです。citeturn34view1turn35calculator0turn7search4turn14view0turn14view2

## 問題の再定義

あなたの要件は、単なる shape optimization ではなく、**空力性能制約つきの位相・形状統合最適化**です。設計自由度としては、形状の局所変形だけではなく、翼端板・導流板・ガーニー状構造・サイドデバイスのような“生える／消える”変化も取り込みたい。その一方で、設計はレギュレーション envelope の内側に留まり、かつ部材は root からつながった単一物体でなければならない。したがって、数理的には「一般形状の shape optimization」よりも、「**固定設計領域における流体トポロジー最適化を先に行い、その後に SDF で壁面を sharp にして形状最適化へ移る**」と整理するのが自然です。近年の外部流トポロジー最適化研究でも、lift・drag・vorticity・energy dissipation を目的や制約として扱い、volume constraint や drag constraint を併用する流れが明確です。citeturn26view0turn26view2turn26view4

性能制約の書き方は、あなたが示していた形が実装上かなり良いです。ダウンフォース最大化なら、
\[
\min_{\phi}\;J(\phi)=-C_{\mathrm{DF}}(\phi)
\]
に対して、
\[
g_E(\phi)=E_{\min}C_D(\phi)-C_{\mathrm{DF}}(\phi)\le 0
\]
と置くのが安定です。抗力最小化なら、
\[
\min_{\phi}\; C_D(\phi)
\qquad
\text{s.t.}\quad
C_{\mathrm{DF,min}}-C_{\mathrm{DF}}(\phi)\le 0
\]
にするのが良いです。外部流トポロジー最適化の最近の論文でも、lift を最大化しつつ drag constraint を課す問題や、lift と drag を同時に扱う multi-objective 問題が実際に解かれていますし、SU2 も penalty を通じた多目的・制約付き形状最適化を公式チュートリアルで扱っています。citeturn26view4turn15view5

実務上はここに、少なくとも **空力中心位置**または**前後ダウンフォース配分**、そして**最小厚さ**と**接続性**を追加すべきです。総ダウンフォースだけを目的にすると、数値最適化は極端に後ろ寄りの空力中心や細い支持による“ズルい”解を作りやすいからです。さらにレース用途では単一点ではなく、車高・ピッチ・ロール・ヨー・速度の複数条件での耐性が必要なので、最初から multipoint 化して、各条件の揚抗比制約を個別に満たすか、KS 関数などで最悪条件を集約する設計にしておく方が、あとで研究システムが伸びます。SU2 の多目的チュートリアルは penalty ベースの統合を公式に示しており、Cart3D 系の適合研究は fixed-lift など出力条件込みの output-based adaptation を扱っています。citeturn15view5turn4search17turn4search7

## 文献から見た技術選択

SDF を中核に置くこと自体は正しい方向です。ただし、**SDF の役割を「壁の内外判定」だけに狭めない**ことが重要です。SDF は、壁面までの距離、局所法線、最近接点、曲率の近似、侵食・膨張による最小厚さチェック、部品間 gap の検出、そして境界層成長停止の判断を、一つの幾何学場として統合できるからです。OpenVDB の `MeshToVolume` は、閉曲面を前提としつつも、非多様体・自己交差・縮退面・法線不整合を含むメッシュから narrow-band level set を作れると明記していますし、Takeda らは「dirty STL」に対して Cartesian CFD 前処理向けの robust SDF 生成を提案しています。つまり、産業的な欠陥形状をいちいち完全修復してからメッシュを切るより、**SDF 側である程度吸収する**方が現実的です。citeturn16view0turn16view1turn38search0turn38search2

前処理時間を削る観点でも、SDF は強いです。Roosing らは triangulated surface から narrow-band SDF を GPU 上で高速生成する方法を示しており、数万から数百万要素スケールでも複雑形状前処理のボトルネックを減らせることを示しています。さらに AMReX は implicit function からでも STL からでも EB を構築でき、Boolean 演算・回転・拡大縮小・移動をサポートし、EB データとして volume fraction、centroid、boundary normal、area fraction まで持っています。これは、**SDF や implicit geometry をそのまま CFD 離散化へ渡したい**ときに非常に相性が良いです。AMReX 自体も GPU ポータビリティを重視しており、CUDA/HIP/SYCL を公式にサポートしています。citeturn8search2turn36view0turn22view0turn22view1

固定格子の流体ソルバ候補としては、AMReX 系の EB/cut-cell が最も研究向きです。AMReX の EB ドキュメントは small-cell problem と flux/state redistribution を明確に整備しており、実際に embedded-boundary データ構造まで揃っています。Basilisk も、distance field を STL から作り、その場で volume fraction・surface fraction に変換し、embed-tree で octree 上の embedded boundary を扱えるので、**プロトタイピングの速さ**では非常に魅力があります。一方、cut-cell は small cut-cell による時間刻み制限が定番の弱点で、ここは Xie の implicit cut-cell 法や state redistribution の系統が有力です。Xie の 2022 年の方法は、implicit time integration によって追加の small-cell treatment なしに安定化できることを示しており、AMReX 系の redistribution 研究も三次元での拡張が進んでいます。citeturn36view0turn25view0turn25view1turn25view2turn23view1turn23view2

ただし、**固定格子だけで最後まで行くのは勧めません**。理由は二つあります。第一に、Darcy／Brinkman の“擬似固体”は topology search には非常に便利ですが、壁面摩擦や境界層の精密評価には弱いこと。Wu らは高 Reynolds 数トポロジー最適化のために modified SST や wall-distance の工夫まで入れており、Re \(=10^6\) 級での適用を示していますが、それでもこれは「探索を可能にする」ための工夫であって、最終解の信頼性を body-fitted と同列に扱うべきではありません。第二に、NASA の ghost-node immersed boundary＋離散随伴研究では、ghost-node 方式は body-fitted に近い adjoint 収束と最適化挙動を示した一方、source-term 方式は三次元翼で adjoint の非収束が出ています。つまり、**探索段階では porous／IBM、精密化段階では ghost-node／cut-cell、最終段階では body-fitted**という役割分担が、文献的にも最も素直です。citeturn7search4turn14view2turn14view3turn14view0

そして body-fitted 側に戻すなら、SDF はそのまま境界層生成にも使えます。minimum distance field を使うプリズム／ストランド生成では、壁近傍の anisotropic prism を作り、少し離れた場所で Cartesian background へ接続する dual-mesh 構成が示されています。2025 年の SDF-guided point cloud generation も、SDF の勾配方向に沿って層を作り、concave/convex に応じて点の insertion/removal を行うことで、複雑形状でも境界層解像を安定化できることを示しています。さらに HybridOctree_Hex は、曲率・狭隘部を検知して strongly balanced octree を作り、テンプレートで all-hex core を作り、buffer zone を closest-point 接続と Jacobian 制御で埋める流れを公開コード付きで示しています。これらをつなぐと、**壁近傍は SDF ベースプリズム、外側は Octree/Hex core** という、あなたが最初に考えていた構成がかなり自然に立ち上がります。citeturn12view4turn14view9turn12view2turn14view8turn37view0turn16view2

## 推奨アルゴリズム

私が勧めるアルゴリズムは、**二相設計変数 \(\rho\)** と **sharp な SDF \(\phi\)** を分ける方式です。つまり、最初のトポロジー探索では固定格子上に
\[
0\le \rho(\mathbf{x})\le 1
\]
を持ち、運動量式に Brinkman 項
\[
\alpha(\rho)\mathbf{u}
\]
を入れて、“流体か固体か”を連続的に表現します。この段階は topology change の獲得が目的なので、壁面を幾何学的に sharp に保つ必要はありません。探索後、\(\rho=\rho_{\mathrm{iso}}\) の等値面を抽出して SDF \(\phi\) に変換し、ここから先は \(\phi=0\) を明確な壁にした sharp-interface 最適化へ移ります。高 Reynolds 数トポロジー最適化では modified turbulence model の必要性が報告されていますし、外部流の lift/drag 制御も Brinkman 系で実際に扱われています。citeturn7search4turn26view0turn26view4

制約は、次の四本を主軸にするのがよいです。第一に、**揚抗比制約**は
\[
g_E(\phi)=E_{\min}C_D-C_{\mathrm{DF}}\le 0
\]
で実装する。第二に、**レギュレーション envelope** は、設計形状の SDF とは別に固定 SDF \(\phi_{\mathrm{allow}}\) を持ち、侵食ではなく**膨張形状**
\[
\Omega_s^{\mathrm{dil}}=\{\phi<r_{\mathrm{rule}}\}
\]
が許可領域に含まれるようにします。これは soft penalty より **hard projection** の方が確実です。第三に、**単一連結性** は root-connected virtual diffusion を使う。Li らの VSFM/VTM 系は、補助的なスカラー場問題を解いて connectivity を“最大温度制約”に読み替える考え方を与えており、2025 年のレビューも connectivity constraint の選択が最終解に強く影響することを示しています。第四に、**最小接続厚さ** は、nominal 形状だけでなく SDF を \(r_{\min}\) だけ侵食した形状にも同じ root-connectivity 制約を課すことで与えます。これは既存の VTM/VSFM と SDF morphology を合成した提案で、細い一本棒での擬似接続を避けるのに効きます。citeturn19view1turn19view2turn19view0turn16view0turn16view1

連結性の代替として、グラフ Laplacian の第二固有値 \(\lambda_2\) を使うスペクトル制約もあります。Neumann-Laplacian の第二固有値の正値性で連結性を特徴づける連続モデルは、まさに connectivity の“連続緩和”として提案されています。ただし、固有値問題は高価で、密度が中間値の細い経路でも連結と見なされやすい。だから、実装の主制約は virtual diffusion、スペクトル法は**比較対象または定期検査**として使うのが現実的です。これは 2025 年の connectivity review が示す「どの制約が最良かは一概に言えず、計算コスト・単調性・パラメータ依存性を見て選ぶべき」という知見とも整合します。citeturn19view2turn19view0

探索段階の最適化器は GCMMA を第一候補にすべきです。理由は、セル数ベースの大量設計変数に対し、制約は揚抗比・体積・連結性・規則違反量・前後配分など少数の大域量になるからです。加えて、Svanberg の MATLAB 実装が公開されており、Python 実装も広く使えます。まず GCMMA で堅く回し、安定したら必要に応じて second-order 系へ進むのがよいです。citeturn16view6turn16view7

sharp-interface 段階では、ghost-node IBM か implicit cut-cell のどちらかを選びます。もし研究主題を「SDF による形状表現」と「随伴最適化」に置くなら、第一候補は ghost-node IBM です。NASA の報告では、ghost-node 法は body-fitted に近い adjoint 収束と良好な最適化挙動を示しました。一方、もし研究主題を「一般形状に対する高精度 fixed-grid ソルバ」そのものに置くなら、第一候補は implicit cut-cell です。Xie の手法は small cut-cell の時間刻み問題を陰的に回避しており、複雑形状・粘性流での堅牢性が高いです。どちらにしても、**最終の粘性抗力評価は body-fitted mesh に返す**、というルールは崩さない方がよいです。citeturn14view0turn14view2turn23view1

メッシュ適合は、幾何学 metric と出力誤差 metric を分けて考えるべきです。SDF が与えるのは、壁距離、曲率、gap、feature distance に由来する**幾何の必要解像度**です。しかし wake、翼端渦、せん断層、剥離位置は幾何だけでは決まらない。したがって、粗い primal＋adjoint の後に、lift/drag の output error に基づく adaptation をかけます。Cart3D の embedded-boundary Cartesian mesh による output-based adaptation は、まさにこの考え方を実証しており、Fidkowski のレビューは adjoint-weighted residual が出力量に対する局所誤差指標になることを整理しています。citeturn4search0turn4search7

## 推奨システム構成

私の推奨システムは、次のようなレイヤ構成です。これは**研究として新規性のある部分**と、**既存の成熟ソフトに乗せる部分**を意図的に分離しています。SDF・root-connectivity・rule projection・局所更新は自作し、既存ソルバは primal/adjoint/meshing の下請けに使います。OpenFOAM の `snappyHexMesh` は STL から split-hex を自動生成でき、small gap refinement や medial-axis 由来の layer 制御も持っています。一方で AMReX は implicit/STL EB と GPU を扱いやすく、SU2 は Windows バイナリと多目的 penalty 付き shape optimization を持っています。OpenFOAM 系には `adjointOptimisationFoam` と topology optimization の公式機能も入り、OpenCFD の v2312 リリースでは porosity-based と level-set based の topology optimization が追加されたと案内されています。DAFoam は OpenFOAM 上で shape/topology/operating-condition optimization を多数設計変数・制約付きで扱う離散随伴プラットフォームとして成熟しています。citeturn16view3turn21view0turn36view0turn22view0turn15view5turn15view4turn29search0turn29search1turn33view0turn33view1

```text
Regulation CAD / Vehicle CAD
        │
        ├─ fixed-solid SDF
        ├─ allowed-region SDF
        ├─ forbidden-region mask
        └─ root / mount region
        │
        ▼
Geometry Service
        │
        ├─ narrow-band SDF
        ├─ closest-point / normal / curvature / gap query
        ├─ erode / dilate
        └─ local SDF update
        │
        ▼
Topology Stage on Fixed Cartesian/Octree Grid
        │
        ├─ primal flow with Brinkman term
        ├─ aerodynamic adjoint
        ├─ root-connectivity diffusion PDE
        ├─ rule projection
        └─ GCMMA
        │
        ▼
Iso-surface Extraction and SDF Rebuild
        │
        ▼
Sharp-Interface Refinement
        │
        ├─ ghost-node IBM or implicit cut-cell
        ├─ output-based mesh adaptation
        └─ shape adjoint update
        │
        ▼
Final Verification
        │
        ├─ SDF-driven prism layers
        ├─ Octree / Hex core
        └─ body-fitted RANS
```

この中で、**最初に作るべきコアは Geometry Service** です。理由は、探索段階でも精密化段階でも最終メッシングでも、同じ問い合わせが必要だからです。最低限必要なのは、\(\phi\)、\(\nabla \phi\)、closest point、closest triangle/patch ID、component ID、second-nearest distance、局所 feature distance です。OpenVDB は narrow-band level set 表現のベースとして有用で、AMReX は EB と implicit function の直結先として有用です。Basilisk も distance→fraction の変換例をそのまま見せているので、検証用ミニプロトタイプには便利です。citeturn16view0turn16view1turn36view0turn25view1

公開・頒布の観点では、**最初の公開版は OpenFOAM 中心に寄せる**のが一番現実的です。つまり、Stage T は OpenFOAM の既存 topology／adjoint 機能か、それに近い density ベース拡張で回す。Stage S の sharp-interface は最初は body-fitted でもよいですが、研究価値を出すなら AMReX か独自 cut-cell ブランチを持つ。最終検証は `snappyHexMesh` か、後で自作する SDF-based prism＋Octree core で行う。これなら、最初の卒研・修論段階でも「動くもの」を出しやすく、その後に SDF 境界層生成と AMReX GPU 化を拡張できます。対して、いきなり AMReX だけで全部を作るのは研究的には美しいですが、配布性と開発速度で不利です。citeturn16view3turn21view0turn29search0turn29search1turn36view0turn22view0

## Windows で再現する実装計画

Windows 再現性を重視するなら、**フロントエンドは Windows ネイティブ、重い CFD バックエンドは WSL2** という構成が最も無理がありません。OpenFOAM は公式に Windows での WSL 利用を案内しており、GUI 付き後処理には Windows ネイティブの ParaView を推奨しています。つまり、ユーザーは Windows 上で GUI とファイル管理と可視化を行い、ソルバだけを Ubuntu/WSL2 側で実行するのがよいです。これはフル VM より心理的障壁が低く、しかも Linux ネイティブに近い再現性が得られます。citeturn16view4turn16view5

一方、**Windows ネイティブだけで完結させたい用途**には SU2 が便利です。SU2 は公式に Windows 用の precompiled binary を提供しており、インストーラ不要で比較的すぐ走らせられます。ただし、公式インストール文書では Windows バイナリは“新規ユーザーが素早く始めるため”の serial 版で、advanced features と parallel 実行が無効であると明記されています。もし Windows ネイティブで parallel まで欲しいなら、MinGW-w64 と Microsoft MPI を用いた build 手順が公式にあります。したがって、**SU2 は「最終の body-fitted shape optimization」や「小規模検証」には非常に良いが、Topology Stage の主戦場にはしにくい**、という位置づけです。citeturn15view4turn15view6turn17view0

配布形態としては、次のように切るのがよいです。Windows の配布物は、Python 製の orchestrator、GUI 付き ParaView、ケース生成テンプレート、そして `bootstrap.ps1` と `bootstrap_wsl.sh` を含むリポジトリです。`bootstrap.ps1` は WSL2 の有無確認、ケースフォルダ作成、環境変数設定、ショートカット生成を行い、`bootstrap_wsl.sh` は solver/backend の依存パッケージを入れます。GPU 版を持つなら AMReX ブランチを別プロファイルにして、CMake 時に `-DAMReX_GPU_BACKEND=CUDA` を有効化する設計にします。AMReX は GPU backend を公式にサポートしているので、**GPU 研究版と CPU 公開版を同じコードベースから切り替えられる**のが強いです。citeturn22view0turn22view1

実装順序としては、まず **CPU 版の固定格子 topology search** を安定させ、その後に **GPU で narrow-band SDF 生成と局所更新** を速くするのがよいです。Roosing らの GPU SDF 生成は、まさにこの“前処理ボトルネックを先に潰す”考え方を裏づけています。逆に、最初からフル GPU CFD まで狙うと、数値スキーム・線形ソルバ・境界条件・開発環境の全てが一度に難しくなります。研究システムとして成功率を上げるなら、**GPU は geometry service と Octree/EB kernel から入る**のが筋です。citeturn8search2turn22view0

## 検証計画と研究テーマ

検証は、単に「最終 Cd が下がった／下がらない」では足りません。少なくとも、**前処理・幾何・メッシュ・CFD・最適化**の五層で分けて評価すべきです。前処理では SDF 生成時間、局所更新時間、メッシュ生成時間、失敗率を見る。幾何では Hausdorff 距離、法線誤差、gap 保持誤差、レギュレーション違反量を見る。メッシュではセル数、skewness、negative volume、layer coverage、第 1 層高さ誤差を見る。CFD では \(C_D\)、\(C_{\mathrm{DF}}\)、圧力分布、壁面摩擦、剥離位置、wake 欠損、格子収束を見る。最適化では、制約違反率、root 非連結率、侵食後非連結率、目的関数の単調改善、epoch ごとの改善量を見る。output-based adaptation の文献は、lift/drag のような特定出力に対して局所誤差の評価が可能であることを示していますし、NASA の immersed-boundary 研究は pressure と skin friction の比較が重要な診断になることを示しています。citeturn4search0turn4search7turn14view1turn14view0

ベンチマークは、円柱や単独翼型だけで終えると、このテーマの本質である「一般形状」「連結制約」「レギュレーション拘束」が見えません。したがって、最小でも **NACA 翼型 → 2 要素翼 → 3D 翼＋翼端板 → タイヤ＋地面 → 車体周辺部品** まで伸ばすべきです。外部流トポロジー最適化の最近の論文でも、Gurney flap のような“人間が物理直感で付けてきた形”が最適化から自然に出ることが報告されており、これはテーマとの相性が良いです。さらに、SDF-based prism＋Octree core を研究テーマにするなら、minimum-distance-field プリズム生成や HybridOctree_Hex と比較するのが筋です。citeturn26view4turn12view4turn37view0

研究テーマとして一番出版しやすいのは、私は次の順だと思います。第一は、**揚抗比制約・root-connectivity・レギュレーション拘束を同時に扱う固定格子外部流トポロジー最適化**です。理由は、既存研究が lift/drag や drag constraint は扱っていても、レギュレーション SDF と root-connectivity を統合した外部空力系はまだ手薄だからです。第二は、**SDF を使った境界層プリズム＋Octree core 自動生成**です。これは meshing そのものがボトルネックだという問題意識に直結しており、SDF-guided point cloud や minimum-distance-field プリズム法と強く接続できます。第三は、**局所 SDF 更新の GPU 化**です。これは工学的価値が非常に高く、形状最適化の反復時間を直接減らせます。連結性そのものの理論比較はレビューとスペクトル法の文献が豊富なので、単独テーマよりも、上の二テーマの“制約モジュール”として入れる方が強いです。citeturn19view0turn19view1turn19view2turn12view2turn12view4turn8search2

最後に、今回の条件に対する**一行の結論**をはっきり書くと、こうです。**探索は density/phase-field＋root-diffusion＋固定格子、精密化は SDF＋ghost-node IBM または implicit cut-cell、最終判定は SDF 由来の境界層プリズム＋Octree/Hex core の body-fitted RANS**。この三段構成が、任意形状・揚抗比制約・単一連結・設計領域拘束・Windows 再現性・将来の GPU 化、の全てをもっとも無理なく両立します。citeturn26view4turn14view0turn23view1turn12view4turn37view0turn16view4turn22view0