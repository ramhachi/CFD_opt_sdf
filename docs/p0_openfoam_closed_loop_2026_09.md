# P0 OpenFOAM closed loop — 2026-09-12

## 判定

このスライスの判定は **gradient chain GO / Stage T optimization NO-GO** とする。

canonical stateをOpenFOAM solverへ渡し、`topOSens`をcanonical gridへ戻す閉ループが、
実機OpenFOAM v2512上で初めて成立した。勾配は有限差分で検証済みである。

同時に、Stage Tがこれまで一度も実設計を生成していなかったことが判明した。過去の
Stage T成果物とStage Sへのhandoff入力は、いずれも設計を表していない。

## 成立した閉ループ

```text
canonical rho (46080 cells)
    -> P @ rho                      -> openfoam_source_state.npz (8192 cells)
    -> active cellのみ注入            -> injected T1 contract
    -> adjointOptimisationFoam       -> topOSens
    -> P.T @ topOSens                -> canonical gradient (46080 cells)
```

| 格子 | shape | origin | spacing | cells |
| --- | --- | --- | --- | --- |
| canonical target | 60 x 32 x 24 | (-1.0, -0.8, -0.6) | 0.05 | 46080 |
| OpenFOAM source | 32 x 16 x 16 | (-1.0, -0.8, -0.6) | (0.09375, 0.1, 0.075) | 8192 |

両格子は同一領域を完全に覆う。これは`ExactCartesianOverlapTransfer.build`の前提である。

主問題は161反復、drag随伴は713反復、downforce随伴は1143反復で収束した。
`drag_coefficient = 3.65646530652`、`downforce_coefficient = 0.775975568032`。

### cell orderの実測

`source_global_cell_labels_by_xfastest`にはこれまで生成器がなく、利用者が与える入力だった。
`derive-openfoam-cell-order`は`postProcess -func writeCellCentres`を実行し、実測したcell
centreを逆写像してこのpermutationを導出する。完全なpermutationでない場合、cell centreが
格子中心に一致しない場合は拒否する。

このメッシュでは結果はidentityだった。blockMeshの単一blockがx-fastest順であるという
従来の仮定は正しかったが、**実測で裏付けられたのは今回が初めて**である。

## 有限差分による検証

canonical格子上で中心差分を取り、`P`、注入、solver、`topOSens`、`P.T`の合成を一括で検証した。
摂動は`0.1 < rho < 0.9`かつ勾配非ゼロの624 cellに限定し、`[0,1]`のclippingを避けた。

| 方向 | eps | ratio（符号補正後） | 相対誤差 |
| --- | --- | --- | --- |
| sensitivity | 3e-5 | 0.990 | 1.03% |
| sensitivity | 1e-4 | 0.993 | 0.74% |
| sensitivity | 3e-4 | 0.994 | 0.57% |
| sensitivity | 1e-3 | 0.994 | 0.56% |

suite全体は8行16実行（各行plus/minus）で、上表はそのうちsensitivity方向の4行8実行である。
16実行はすべて収束した。epsを縮めるとratioが1へ近づく、教科書どおりの挙動である。
**最適化器が実際に辿る勾配方向について、連鎖は約1%で正しい。**
残る4行はfiltered-random方向であり、後述の未解明バイアスを持つ。

### 符号規約

`top_o_sensitivity_gradient`は`+downforce_coefficient`の微分であり、本プロジェクトの
`J = -downforce_coefficient`に対する`dJ/drho`とは**逆符号**である。補正前のratioは8行すべてで
約-1（平均-0.9931）に集中した。

この配列を`dJ/drho`として消費する実装は、設計を逆方向へ動かす。artifactの規約文字列を
「`adjoint_solver_id`が指すOpenFOAM目的関数の微分であり、下流の目的関数との符号関係は
消費側が与える」と明示するよう修正した。

### 未解明の系統誤差

filtered-random方向（局在したランダム方向）では、ratioが約0.90で安定し、epsを1桁変えても
1に近づかない。

| 条件 | ratio | 相対誤差 |
| --- | --- | --- |
| 既定許容値 | 0.896（eps 1e-3） | 10.4% |
| 主問題残差を約2桁厳格化（5e-7 → 約5e-9） | 0.905 | 9.5% |
| 正則化を無効化 | 0.861 | — |

許容値の厳格化はratioのばらつきを消したが（分散0.075 → 0.008）、バイアスは消さなかった。
したがってノイズではない。

正則化フィルタの連鎖律欠落を疑ったが、**因果実験で棄却された**。フィルタを無効化すると
ratioは1へ近づくどころか0.861へ遠ざかった。先行して記録した「canonical chainが正則化の
連鎖律項を欠いている」という主張は撤回した。

残る候補は`P`の部分重なり再配分である。refinement比が整数でない（0.09375/0.05 = 1.875、
0.075/0.05 = 1.5）ため、source cellの感度が非整数個のcanonical cellへ分配される。
**この候補は未検証であり、確定した機構として扱わない。**

運用上の含意は限定的である。勾配方向の精度は約1%であり、move制限付き降下法が使うのは
その方向である。バイアスは一般方向の方向微分検査に現れる。

## Stage Tが実設計を生成していなかったこと

### 観測

`t1_contract`の2909 active design cellのうち、2797が`rho = 0`、112がちょうど`rho = 0.5`で、
0.5を超えるcellは存在しない。

native optimizerを40サイクル、および目的関数を組み替えて20サイクル実行したが、いずれも
同一の退化解へ収束した。

| 実行 | サイクル | beta histogram | mean | 実現体積率 | 目標 |
| --- | --- | --- | --- | --- | --- |
| run40（元の定式化） | 40 | [8080, 2, 110, 0, 0, 0] | 0.0070 | 約0.007 | 0.462 |
| run_maxdf20（downforce最大化） | 20 | [8080, 0, 112, 0, 0, 0] | 0.0070 | 約0.007 | 0.462 |

histogramのbinは`[0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]`。0.5を超えるcellは両者ともゼロである。
40サイクル実行は固定点への収束を示しており、サイクル数の不足ではない。

### 第一の欠陥：目的関数ではなく等式制約

`examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base/system/optimisationDict`は
`downforce`を`isConstraint true; target 0;`として宣言し、`drag`を唯一の重み付き目的関数と
していた。実際に解かれていた問題は次である。

```text
minimize   drag
subject to downforce == 0
           volume fraction == 0.462
```

材料を置けば必ず鉛直力が生じて`downforce == 0`に反するため、最適化器は体積ゼロ近傍に留まる。
これはこのリポジトリ自身のテンプレートであり、work成果物だけの問題ではない。

### 第二の欠陥：体積制約が機能しない

`downforce`を`weight -1`の最大化目的へ組み替えても、設計場はほぼ動かなかった
（mean alpha 0.0070 → 0.0071）。`vol`目的値は両実行で1.1493付近に凍結し、
Lagrange乗数はISQPのペナルティ係数`c = 2`と一致する約1.99999999に固着していた。

つまり主犯はdownforceの定式化ではなく、体積制約の機構である。

### 第三の欠陥：iso-surfaceが設計面ではない

全実行・全サイクルの`optimisation/topOIsoSurfaces/topOIsoSurface*.stl`は同一だった。

| 項目 | 値 |
| --- | --- |
| faces | 5120 |
| vertices | 2822 |
| watertight | false |
| connected components | 6（[1024, 1024, 1024, 1024, 512, 512]） |
| bounds | 計算領域そのもの |

これは32x16x16領域の6枚の平坦な境界パッチである。`rho`が0.5を超えないため、0.5等値面
抽出器が辿るべき面を持たない。

**これまでStage Sのdensity→SDF handoffが`component count = 0`で失格していた原因はここにある。**
handoffの欠陥ではない。

## 既知のギャップ

1. 使用したProblemSpecは`drag`応答と`minimize_drag`目的のみを宣言しており、検証した勾配は
   OpenFOAMの`downforce`目的のものである。**勾配は宣言された目的関数へ意味論的に束縛されて
   いない。** 対策として`transfer-openfoam-gradient-to-canonical`に`--response-id`を必須化し、
   ProblemSpecで宣言された応答であることを検証するようにした。記録済みartifactはこの
   ガード導入前のものである。
2. 注入は`rho`のみを上書きし、`rho_filtered`、`rho_projected`、`alpha`は前状態のまま残る。
   solver caseは`rho`から生成される（`src/cfd_sdf/fixed_grid_primal.py:590`）ため今回の結果は
   正しいが、他の配列を読む将来の消費者は古い状態を黙って読む。
3. 一般方向の約10%バイアスは未解明である。

## 証拠の範囲

8192 cellの層流fixture一つ、収束状態一つ、目的関数一つ、機械一台での結果である。
target aerodynamicsの証拠ではない。拘束付き最適化の証拠でもない。他の格子、他のReynolds数、
実行時間・メモリの証拠でもない。いかなるsolver backendの昇格根拠にもならない。

機械可読な記録は`docs/evidence/p0_openfoam_closed_loop_2026_09.json`に置く。

## サロゲートのランキングが転写しなかった — 2026-09-12

この構成はStage T（固定格子Brinkman多孔質サロゲート）で最適化し、Stage V
（body-fitted RANS）で検証する。成立条件はサロゲートが候補の**順位**を検証と
同じ向きに並べることであり、絶対値の一致は要求しない。この前提を候補2つ
（`candidate_a_seed_reshape`、`candidate_b_zero_floor`）で検査したところ、結果は
**負**だった。

両候補をbody-fitted meshで3段階の解像度（1 m/s、Stage Tケース自身の粘性、
`Aref` 0.64、層流）で解いた。B/A比は次のとおり。

| B/A比 | Stage T | coarse (5.5k) | medium (30k) | fine (180k) |
| --- | --- | --- | --- | --- |
| drag | 2.582 | 0.849 | 0.901 | 0.905 |
| downforce | 3.882 | 3.167 | 0.896 | 0.918 |
| L/D | 1.503 | 3.728 | 0.995 | 1.015 |

dragの順位は全格子で逆転している。downforceの順位は最も粗い格子でのみ一致し、
より細かい2格子では逆転する。dragは両候補とも単調に収束する
（A: 0.857→0.934→0.958、B: 0.728→0.841→0.867）が、downforceは単調ではない
（A: 0.0132→0.0358→0.0449、B: 0.0417→0.0321→0.0413）。coarse格子でのみ
Stage Tと一致するdownforceの順位は、この中で最も収束していない数値の上に
成り立っている。

### 乱流モデルの交絡は棄却された

candidate Aについて層流と`kOmegaSST`のdrag系数を比較すると、coarseで0.016%、
mediumで0.006%しか差がない。Re~300ではeddy viscosityの寄与が無視できるほど
小さく、以前の`kOmegaSST`比較は無効な検定ではなかった。これが今回の負の結果
を信頼できるものにしている。

### 「サロゲートは使い物にならない」とは結論しない

このデータはその主張を支持しない。順位が転写しなかった原因として、区別され
ていない2つの欠陥がある。

1. **設計が二値化されていない。** candidate Aの`rho`最大値は0.62、Bは0.55で、
   0.9を超えるcellは両者ともゼロ。Stage Tは半透過なblobを最適化し、Stage Sは
   その0.5等値面から立体を抽出し、Stage Vはその立体を解いた——別の物理的対象
   である。原因は`docs/stage_t_optimizer_diagnosis_2026_09.md`に記録した
   `function linear`射影の欠陥である。
2. **Stage Tの格子が最適化対象を解像していない可能性がある。** Stage Tの8192
   cellはbody-fitted coarse格子（5534 cell）と同程度であり、両フィデリティが
   一致するのはまさにその解像度である。より細かい格子では一致が消える。

この2つは別々の主張であり、今回のデータはそれらを分離しない。

### 確立された正の結果

Stage S -> Stage Vのパイプライン自体は実在する非退化形状で機能する。
`build-density-sdf-handoff`の再実行はbyte-identicalなSTLハッシュを再現し、
candidate Bの2つの連結成分は3解像度すべてでsnappyHexMeshに欠落なくmeshされ、
`Cd`は単調収束し、6実行すべてで力の後処理が成功した。

この検定のため、`src/cfd_sdf/openfoam.py`にbody-fitted層流経路を追加した。
`kOmegaSST`以外の未対応乱流モデルはfail-closedのまま拒否する。

### 証拠の範囲

fixture一つ、候補2つ、Re~300、機械一台。cross-fidelityとpipeline-capability
の証拠であり、target physicsでもbenchmarkでもなく、いかなるsolver backendの
昇格根拠にもならない。**二値化され十分に解像された設計に対してサロゲートが
正しく順位付けるかは未検証であり**、`docs/phase_plan.md`第11節の実行順序1番
としてroadmapに残す。

機械可読な記録は`docs/evidence/cross_fidelity_ranking_2026_09.json`に置く。
