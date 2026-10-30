# #45 次ステップ計画 v2（提案・未承認）

日付: 2026-10-04 / 対象: #45 XFID-01、#29 GEOM-01（export 部分）、#46 FD-08 の待ち
ステータス: **承認済み（2026-10-04 ユーザー決定 D1〜D4）。** 決定内容は phase_plan の同日付エントリに反映した。
権威: 実行順序は `docs/phase_plan.md` が唯一の権威。この文書は実行手順の詳細で、単独では順序を変えない。
全 qualification flag は false のまま。

### 決定（2026-10-04、ユーザー）

- D1: #46 FD-08 を XFID と**並行**してよい（解決済み DISAGREE が出たら #46 を止める）。
- D2: 極小 component は Stage V STL から**除去**する。
- D3: Stage V STL は **r=8** を使う。
- D4: 2026-10-03 の「baseline と全摂動が厳密 geometry gate を通ること」を、実用 gate + 幾何誤差の測定・併記に置き換える。

v1（同日）からの変更: ユーザー判断「STL の品質 gate は非本質的で後回しでよい」を採用した。
厳密な 0.5 mm 認証（CERT-02 など）を XFID の経路から外し、実用 gate と誤差の「測定・併記」に置き換える。

## 1. 位置づけ

- 構成: WaterLily-C で最適化し、OpenFOAM（Stage V）を独立した最終検証に使う。
- XFID は、その構成の信頼性を最適化の前に確かめる事前チェック（2026-10-02 four-track 計画の Track B）。
  同じ形状を両 solver で解き、`{-ε, baseline, +ε}` の応答の符号と候補順序が一致するかを見る。
  過去に Stage T の ranking が Stage V に転移しなかったことが動機。
- 分岐: 解決済み DISAGREE なら Track C（FD/AD）を降格。AGREE なら FD-08 と勾配に資源を回す。

## 2. 現在地（測定済みの事実のみ）

- XFID の solver 実行は 0 回。止まっているのは Stage V 用 STL の gate。環境再現（Kaggle CPU・OpenFOAM v2512）は PASS 済み。
- Round 3 で、r≥2 の STL は float32 STL を含めて watertight・edge/vertex-link manifold が通っている（39/40 case）。
- 絶対 geometry（0.5 mm）: r=4 は 3 PASS / 0 FAIL / 7 UNRESOLVED、r=8 は 4 / 0 / 6。0.5 mm 超と証明された case はゼロ。
  r=8 の最大 lower bound は 0.097 mm。
- orientation の FAIL は、Round 3 の記録で確認できた範囲（r=1）では 8 面の極小 component
  （体積 1.5e-10〜3.3e-10 m³、約 0.5 mm 級）が原因。主 component（0.145 m³ 級）は PASS。r=4/8 の失敗 case が同じ形状かは未確認。
- CERT-01 は FAIL のまま。taxonomy では不一致 5,796 件のうち baseline 側が 5,706 件、target 側 90 件。
  target 側は primary が判定を拒否しただけで root は同じ。

### 今回確認した新事実: OpenFOAM のメッシュは gate より桁違いに粗い

`infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template/system/` より:

- 背景メッシュ 25×13×9（約 0.2 m）、body 表面の refinement level (2 3) → **表面セル 25〜50 mm**。
- 参考: v16 再現に使った STL（`fixtures/candidate_v16.stl`）は 2,684 三角形・42,619 cell・simpleFoam 584 反復で約 62 秒。
  r=8 の STL は約 68 万三角形（baseline 681,504、r=4 は 169,098）で、三角形数が 250 倍超。
  メッシュ生成の時間・メモリへの影響は未測定で、X2 で最初に確認する（実測で重すぎる場合のみ r を再相談）。
- 厳密 gate の 0.5 mm は表面セルの約 1/50〜1/100。極小破片（~0.5 mm）はメッシュに解像されない。
- 一方、摂動 ε = 5 mm は表面セルの約 1/5〜1/10。

帰結: STL の幾何誤差の証明はメッシュ精度に対して過剰で、後回しが妥当。
**逆に、本当の懸念は「ε=5 mm の応答が OpenFOAM のメッシュノイズ（snappyHexMesh の cell 保持/除去の離散的な変化）に埋もれないか」**。
これは gate では防げず、測定が必要（X2）。

## 3. 方針

1. STL は「OpenFOAM に通せる実用品質」でよしとし、幾何誤差は**証明せず測って結果に併記**する。
2. 厳密な幾何保証（CERT-02、絶対 geometry 認証、全 component の orientation）は #29 GEOM-01 側へ移し、XFID から切り離す。
3. XFID の最大リスク（メッシュノイズ vs ε）を、最初に安く測る。

## 4. フェーズ

### X0. ユーザー判断

| # | 判断 | 推奨 |
|---|---|---|
| D1 | #46 FD-08 を XFID と並行させるか（現行順序は XFID AGREE まで #46 の solver を止める） | 並行を許可。calibration は Candidate C の同一 identity で XFID に依存しない。**解決済み DISAGREE が出たら #46 を止める** |
| D2 | 極小 component（~0.5 mm の破片）の Stage V STL での扱い | STL から除去（deterministic ルール、除去した component の面数・体積・位置を記録）。メッシュに解像されず、WaterLily の φ とは「無視できる差」として併記 |
| D3 | 使う r | r=8 の保存済み STL（最大 lower bound 0.097 mm、ε の 2% 以下）。r=4 は予備 |
| D4 | 2026-10-03 の順序（「baseline と全摂動が geometry gate を通ること」）の置換 | 厳密 gate を実用 gate に置換することを phase_plan に追記し、#45 にコメントする |

### X1. 実用 STL 入力の確定（solver 不要・約半日）— **完了 2026-10-04**: 7/7 PASS、独立 check と STL の sha256 が一致。`45_stage_v_input_2026_10_04.md`

- 入力: Round 3 の保存済み r=8 の STL/表面（baseline と D0/D1/D2 の ±ε の 7 形状）。
- 処理（決定的スクリプト 1 本）: D2 に従い極小 component を除去し、主 component が内向きなら component 単位で反転。頂点は動かさない。
  出力は派生 STL とし、元の Round 3 証跡は不変のまま、入力ハッシュと派生ハッシュを記録して lineage を結ぶ。
- **実用 gate（pass/fail）**: watertight、edge/vertex-link manifold、重複・縮退面なし、符号付き体積が正、Stage V の clearance。
- **測定して併記（gate にしない）**: 頂点の `|φ|/|∇φ|` 統計（median / p99 / max）、baseline と ±ε の STL 変位が ε に対して妥当か、除去した破片の体積比。
- 独立 check: 派生 STL を別の小スクリプトで再計算（sonnet サブエージェント、primary を見せない）。
- 事前登録: 実用 gate と併記項目を、実行前に commit・push。厳密認証が未実施であることを結果に明記。

### X2. OpenFOAM グリッド位相感度（grid-phase）の測定（Kaggle CPU・最重要）— **完了 2026-10-04（round 2）**: 33/33 完了、0.73 h、中心 secant ノイズ ~3e-4 N（downforce）。`45_xfid_gridphase_x2_result_2026_10_04.md`

目的: 固定した背景メッシュに対して形状を剛体並進させたときの力の変化（grid-phase 感度）と、
メッシュ生成コストを、XFID 本番の前に実測する。XFID の response floor の経験的根拠にする。

設計上の注意（レビュー反映）: x 方向の並進は入口・出口・wake 長との相対位置が変わるため、
**物理応答ゼロの null 摂動とは扱わない**。y は左右対称 domain/BC ならほぼ null に近いが断定しない。
z は ground clearance が変わるので物理応答が乗る。したがって「ゆらぎ = メッシュノイズ」と仮定せず、
各軸の応答を滑らかな成分（直線/2 次）と残差に分けて報告し、**経験的 floor の測定**として登録する。

- 内容: baseline STL を軸ごとに 0.5, 1, 2, 4, 8 mm 並進（±両方向で奇/偶成分も分離）。毎回 snappyHexMesh を新規生成。
- 記録するもの: drag/downforce の差とジャンプ [N]、総 cell 数・表面 refinement cell 数の変化、
  checkMesh、snappyHexMesh の時間とピークメモリ、simpleFoam の反復数・時間。
- 判断: 実現変位が D1/D2 相当（中央値約 0.9 mm、p95 約 3.2 mm）の並進でも力が D1/D2 相当以上に動くなら、
  formal XFID で D1/D2 を使う設計は厳しい。→ ε を大きくする、D0 を主にする、表面 level を上げる、のいずれかをユーザーに諮る。
- XFID の 7 形状は使わない（formal 証拠を消費しない）。submit 前にユーザー確認を取る。

### X3. XFID 比較契約の登録（solver 不要・約 1 日）

`45_xfid_comparison_contract_draft.md` の未決部分を埋めて immutable に登録する:
方向（D0/D1/D2）、ε、solver ごとの response floor（X2 の結果と WaterLily 側の calibration）、
same-geometry lineage（X1 の派生 STL と同じ摂動 GridSDF）、判定規則（AGREE / DISAGREE / UNRESOLVED）。
応答は N で比較し、係数は主応答にしない。

### X4. 実行と判定（Kaggle）

WaterLily-C（確定済みの Candidate C identity、flow_24、v17、`[80,120]` の物理時間窓）と OpenFOAM（Kaggle CPU、環境再現済みと同一構成）で
7 形状を解き、判定を #45 に記録。解決済み DISAGREE のときだけ Track C を降格。AGREE でも
「STL の幾何誤差が X の条件下で、全 FSAE 形状の保証ではない」と限定して記録。

### 後回し（#29 GEOM-01 側に移管。XFID を止めない）

- CERT-02（root 集合の一致契約：半開区間の所有、厳密有理数での endpoint 符号評価、区間の重なり判定）。
  taxonomy で得た材料は保存済み: `45_cert01_mismatch_taxonomy_2026_10_04.md`。
- 絶対 geometry 0.5 mm の PASS/FAIL/UNRESOLVED 再判定。
- 小 component の orientation の厳密処理と、最小 feature 限界の判断（#29/#31）。
- 着手の条件: XFID の結果が出た後、または「Stage V の幾何保証」を主張する必要が出たとき。

## 5. 実行体制と記録

契約文・事前登録・レビュー・証跡の記録は私。独立 check は sonnet サブエージェント（primary のソースを渡さない）。
ブランチは統合ブランチから issue ごとに `exp/issue45-*`、`--no-ff` で merge。各ステップで focused テスト、
compileall、full pytest（failure-ID を基準 36 件と比較）、`git diff --check`。結果は #45 と phase_plan に残す。

## 6. 主なリスク

- ε=5 mm がメッシュノイズ級で UNRESOLVED になる → X2 を最初に実施し、結果で ε/メッシュを判断する。
- STL の幾何誤差が応答に効いて DISAGREE に見える → 誤差を測って併記し、「証明済み」とは書かない。
- 極小破片の除去が WaterLily との形状差になる → 体積比と位置を記録（比は 1e-9 級、メッシュ解像度未満）。
- 厳密 gate を後回しにした分、XFID の結論は「uncertified geometry 条件下」と限定される。
- AGREE でも、grid 独立な downforce、全車両・高 Re の FSAE 資格、Stage T/V ランキングの資格は主張しない。
