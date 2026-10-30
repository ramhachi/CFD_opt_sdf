# DF 実行計画の批判的レビュー — 2026-09-21

Status: review record, subordinate to
[`df_execution_plan_2026_09.md`](df_execution_plan_2026_09.md) と
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
Scope: DF0–DF7 実行計画の自査的レビュー。外部一次文献の再調査
（2026-09-21 実施）に基づき、計画の技術的前提のうち弱いものを列挙し、
各項目について計画書への修正を適用済み/amend 必要を明示する。

---

## 1. Findings（重要度順）

### F1（高）受理制御の数理が未定義のまま。DF3 と DF6 で二重に受理を走らせる設計になっている

**指摘**。実行計画の DF3 は「ad hoc の accept/reject + move radius 半減」を、
DF6 は「GCMMA backend」を導入するが、両者とも trial 受理の数理（merit 関数、
方向の descent/conservatism 判定、内側反復の回数上限）を定義していない。
結果として (a) linearized acceptance の失敗を繰り返す、または (b) DF6 で
controller と backend が二重に受理を判断して role が曖昧になる。

**文献根拠**。
Svanberg の GCMMA（globally convergent MMA、括弧内は FORTRAN manual "MMA and
GCMMA – Fortran versions", 2013）は、outer iteration で勾配を 1 回だけ評価し、
inner iteration ごとに trial で **真の目的・制約値を再評価** して近似が
conservative（`f̃(x̂) ≥ f(x̂)`）でなければ asymptote を保守化して再解く、という
新しい保守性チェックループとして定義される。これは DF3 が求める
「実 response で accept/reject」そのものであり、backend と acceptance control を
同一の数理構造に統合できる。比較研究（Rochefort-Beaudoin et al., DETC2022-88722）
では MMA / GCMMA / hybrid の収束差実測もある。よって "DF3 の controller を建てて
後で GCMMA に '置換'" は誤った構造であり、**DF3 の時点から GCMMA 型の保守性
loop として実装するのが正しい**（SLSQP adapter は診断 reference として残す）。

**修正（計画書に適用済み）**: DF3 の controller 仕様に merit/conservatism 定義
と GCMMA 型構造を明記。DF6 は backend 実装の入れ替えであって受理規則の変更ではない
ことを明示。

### F2（高）robust three-field の性質を過大に書いている。コストと前提の明記が必要

**指摘**。実行計画は「robust 三場だけが solid/void 両側の length scale を保証する
既知の定式化」と書いたが、これは次の点で不正確。

1. robust 三場の length scale 制御は、三場が **同一 topology を共有する場合に限り**
   blueprint design の length scale を保証する。一貫性は a posteriori にしか確認
   できない（Wang/Lazarov/Sigmund 2011 の前提、Zhou et al. 2015 CMAME 293:266 の
   反例と条件、Hägg & Wadbro 2018 SMO 76:103 の形態論的定式化）。
2. solid/void 両側の同時制御には dilated design 側への体積制約適用が
   構造上必要（Trillet, Duysinx, Fernández, arXiv:2101.08605 / SMO 2021–2022:
   "intermediate/dilated designs は objective から除外できるが volume restriction
   は dilated design に適用しなければ 3 field が問題に参加しない"）。
   実行計画は nominal vs worst-case volume を ProblemSpec で選べとだけ書いており、
   この定理を使っていない。
3. filter/projection パラメータと length scale の対応は解析的に先行計算できる
   （Qian & Sigmund 2013、Trillet et al. 2021）。試行錯誤を preregistration に
   混ぜないための根拠として計画に入れるべき。
4. 計算コスト: robust 三場は outer iteration あたり primal+adjoint を
   **3 回** 走らせる。budget manifest は 3 倍 primal cost を前提にしなければならない。
5. 補完・代替経路として Zhou et al. 2015 の geometric constraints
   （追加 PDE 解なし、微分可能、安価）とその解析的 hyperparameter 版
   （Arrieta, Romano, Johnson, arXiv:2507.16108, 2025）がある。robust 三場の
   topology 不一致や cost が manifest budget に収まらない場合の fallback
   path として計画に登録する価値がある。

**修正（計画書に適用済み）**: DF6 に上記 5 点を明記。

### F3（中）P6（hash 比 ~1.9 の約 10% bias）の立て付けが弱い。原因仮説と修復経路を文献で支える

**指摘**。DF2 は non-integer overlap transfer の検証を入れているが、bias の
診断経路と修復経路が generic。文献上の既知構造を明記する必要がある。

- 精度問題は classic な **consistency（P による勾配の一致写像）と
  conservativity（積分の保存）の区別** に集約される（Farhat et al., CMAME
  2004, common refinement; de Boer et al. 2008; Najian Asl et al. 2020, partitioned
  adjoint FSI on non-matching meshes — nearest-element 一定写像の adjoint 側転置は
  spurious oscillation が残り、mortar/common-refinement は primal・sensitivity 両方で
  noise-free）。P6 の ~0.90 ratio は「P による solver field への force 投影と
  `P.T` による sensitivity の逆写像が同一の重み構造でなく非整合」仮説と整合的で、
  これは FD で (a) primal 側転写誤差、(b) adjacency 側転写誤差、(c) 両者合成の
  3 段で分離できる。P6 triage の FD suite にこの 3 段分解を必須にする。
- 修復経路は (i) integer-ratio 制限（contract 制限）、(ii) common-refinement 型
  conservative transfer の実装、(iii) 誤差を明示した residual correction の 3 段階。
  修復に進む前に (i) で止める判断の根拠になる。

**修正（計画書に適用済み）**: DF2 step 3 に 3 段分解診断と文献根拠 を追記。

### F4（中）Ghasemi & Elham 2022 の実測値が Stage T 格子 doctrine の定量的錨として未使用

**指摘**。DF2 の Stage T 三格子（固定形状）は基準が緩い。Ghasemi & Elham 2022
（SMO 65, doi:10.1007/s00158-022-03208-x）は multi-stage Cartesian density TO で
(a) interface 力の誤差は十分に解像された格子（feature あたり ≥7 cells）で <4% に
なることを確認、(b) coarse stage → projection → refined local design space という
multi-stage 正式手順で 3D 15–45% の cost 削減を報告。したがって
- Stage T grid family は事前 registered な halving voxel family として定義する
  （この意味は "Stage T の格子の数値不確かさ" の評価対象であり、Stage V body-fitted
  三格子と混同しない）。
- feature 解像 cell 数と推定 force 誤差を Stage T manifest に preregister する。

**修正（計画書に適用済み）**: DF2 step 4 に錨数値と格子 family 定義を義務化。
ただし本数値は target physics の threshold ではなく、「Stage T 系の格子を変えた
場合の interface 力誤差の解析錨」として使う（target-physics 主張には転用しない）。

---

## 2. 適用済み修正のサマリ

| Finding | 適用先 | 状態 |
| --- | --- | --- |
| F1（受理制御未定義）| DF3 ステップ 2 | applied |
| F2（robust 三場の前提）| DF6 robust three-field | applied |
| F3（P6 transfer 診断）| DF2 transfer FD suite | applied |
| F4（格子 doctrine 錨）| DF2 ステップ 4 | applied |

## 3. 採用しなかった提案と理由

- **SSP (subpixel-smooth projection, Hammond et al. 2025)** 利用の提案: 現在の
  tanh projection + ConeFilter chain が一台で binarization gate を満たし、robust
  formulation に余計な置換を混在させないため。DF6 で feature-size 適合が不十分な
  場合の再調査対象メモとして記録する。
- **MOLE/perimeter/skeleton 族への置換**: metric 面では安価で微分可能だが
  構造に固有の registration が必要で、aerodynamic objective との binding は実装
  経歴にないため。DF6 の fallback 候補に留める。
