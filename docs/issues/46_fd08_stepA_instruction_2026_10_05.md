# #46 FD-08 Step A 指示文 v2（codex 向け・ソルバー不要の記述的診断 P2a）

日付: 2026-10-05 / 起草: Claude / 実装担当: codex
ステータス: **指示案 v2。ユーザー承認後に codex へ渡す。** v1 は対抗レビュー（1 体）で GO-WITH-CHANGES となり、下記の欠陥を直した。
前提文書: `docs/issues/46_fd08_post_r5_plan_2026_10_05.md`（§7 改訂 2）、`post_hoc_p1/P1_diagnostic_note.md`
全 qualification flag は false のまま。

### v1 からの主な変更（対抗レビューの指摘）

- 目的を「判定する」から「記述する」に変更。『達成不能』を結論として書かない。事前の判定規則がなく、後付けで言えてしまうため。
- LOO は ladder 点が少なく大半が評価不能（実測: 3 区間のうち 2 区間は全系列で不能、D1 は全区間で不能）。**3 値（pass / fail / undeterminable）で記録**し、補完として **登録済み selector と同じ plateau 窓表**を追加。
- A4（SDF 格子の辺の符号反転数）は構造的に無意味（4718 ノードが |phi|<1e-6 に載り、ε が約 1e-6 を超えれば全て反転するため ε に対して一定）。**連続な汎関数（体積・固体率）の奇偶分解に置換。**
- 入力 hash、力の換算（1/900 N）、配列の次元順（F/C）、符号の規約、決定性、テスト基準、ブランチ規則を明記。

## 0. 目的（記述のみ）

R5 の保存済みデータから、**事前に固定した定義**で次の数値を出して記録する。解釈と判断は書かない（P2 のユーザー判断の入力）。

1. 登録済み selector と同じ意味での、連続 5 点窓ごとの最大偏差。
2. 平坦性の区間安定性（回帰の傾き g の区間間のずれ）と粗さ（LOO、評価不能を明示）。
3. 連続汎関数（零等値面の囲む体積、固体率）の ε 依存の奇偶分解と q(ε) の比較。
4. 力の ε 別ノイズ想定に対する q の誤差の見積もり（ノイズ量は入力パラメータとして与える）。

gate・ladder・定義・direction は一切変えない。R6 は登録しない。**「達成不能」「原因は…」と結論として書くことを禁止する。**

## 1. 絶対にしないこと

- ソルバー実行、Kaggle 操作、R6 / fresh33 の登録・criteria 作成・submit。
- R5 の判定、登録済み criteria、既存 analysis JSON、P1 成果物（`post_hoc_p1/`, `post_hoc_p1_ja/`）の変更。
- 新しい受け入れ基準・閾値・ε・ladder・窓の提案を結論として書くこと。
- 機構の断定（cut 切替・ノイズ・曲率のいずれも）。観測と整合する／しない、のみ書く。
- 既存ファイルの編集（`pyproject.toml` 等が必要なら最小限で、理由を note に書く）。

## 2. 入力（読み取り専用）と検証

実行時に次の hash を検証し、**不一致なら計算せず中止**する。

- R5 criteria `928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c`、既存 analysis `dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b`、source commit `95bd9cbf8e67f0c718e346f7edca3f343ed1091f`。
- 力の CSV（`result/fd08_calibration/states/*/flow_24.forces.csv`）: runner manifest `1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e` の記載 hash と一致。
- データセット（リポジトリ外）: `/Users/sota/.codex/worktrees/issue45-root-certifier-integration/work/fd08_candidate_c_calibration_dataset_r5/`（`baseline_v17.npz`、`baseline_v17.phi_f4_fortran.raw`、`directions/*.f4-c.raw`、`states/`）。全ファイルを criteria の `dataset_files` の sha256 と照合。`baseline_v17.npz` は `CANONICAL_STATE_NPZ_SHA256`（`7a972b33…`）と一致。
- 配列の次元順: `phi_f4_fortran.raw` は `reshape(order='F')`、方向 `*.f4-c.raw` は `order='C'`、形状はともに (121,65,49)。npz の phi と F 順 raw の一致を確認してから使う。

## 3. 事前に固定する定義（実装前に note 冒頭へ転記し、定数としてスクリプトに埋める）

- 力: `clipped_time_mean_from_rows`（P1 と同じ）で窓 `[80,120] tU/L` を平均し、**換算 1/900 N / solver force unit**（`force_scale_n_per_solver_force=0.0011111…`）を掛けて N にする。
- 系列: 3 方向 × {drag, downforce}。ε は **mm** で保持する（c の単位は N/m/mm² ではなく、q [N/m] に対する mm⁻²）。
- R0 = baseline 5 反復の `math.fsum` 平均（E の計算にだけ使う）。
- S = (R(+ε) − R(−ε))/2、q = S/ε、E = (R(+ε) + R(−ε))/2 − R0。S の閾値は **中心差分の |S|** に適用する。
- 区間の端点は含む。当てはめは重みなしの最小二乗（q に対し q = g + c·ε²）。
- **大信号点**: |S| ≥ X µN。**X の一次値は 50 µN**（記述用の事前固定カットで、導出されたノイズ床ではない。P1 の「3.4e-6 / 2.2e-6 N は固定参照からの差でありノイズ床として登録した値ではない」を踏襲する）。
  - ただし 50 µN は D1 downforce 0.5 mm（48.08 µN）・D2 downforce 0.5 mm（47.51 µN）のすぐ上にあるため、**10 / 30 / 50 µN の 3 水準で並べた感度表を併記**する（50 µN を primary と明記）。
  - 「結果を見る前に固定した」とは書かない。P1 と計画の表で S・q を既に見た後の記述用の固定である、と note に正直に書く。
- **LOO**: 区間内の大信号点が **4 点以上**あるときだけ定義する。点 ε_k を除き、残りで当てはめ、ε_k の q を予測。相対 LOO 誤差 = |q_obs − q_pred| / |q_obs|（|q_obs| が 1e-9 N/m 未満なら undeterminable）。**3 値（pass / fail / undeterminable）で記録**し、pass・fail の境は書かず、**数値のみ**（% と µN/m）を出す。undeterminable を「良好」と読める表現を使わない。
  - 既知の想定: ladder 点は [0.5, 5] と [1.5, 15] mm で 3 点だけなので、この 2 区間は全系列で undeterminable。そのまま記録する。
  - [0.5, 15] mm の 15 mm 点は、P1 が非線形域と呼んだ領域への外挿であることを併記する。
- 当てはめ区間（固定）: [0.5, 5]、[0.5, 15]、[1.5, 15] mm（R5 ladder 点）。g・c・残差 RMS（絶対と g に対する %）を出す。g の区間間のずれ = (max g − min g)/|median g|（3 区間での最大・最小）。大信号点のフィルタは g 当てはめには適用せず、区間内の全点を使う（フィルタ適用版は別列で併記）。
- 連続汎関数（A4）の規約: **phi < 0 を物体内部**とする。符号の規約が変わる場合は note に別表を出す。

## 4. 作業項目

- **A1 分解表**: 6 系列 × 7 ε の R(+), R(−), R0, S, q, E（N と µN）。
- **A2 回帰と区間安定性**: §3 の 3 区間の g, c, 残差、g のずれ。
- **A3 plateau 窓表（登録済み selector と同じ意味）**: 連続 5 点窓は 3 つ（0.05 / 0.15 / 0.5 mm 起点）。各系列・各窓の、窓内中央値に対する最大相対偏差（%）。正規化は登録済み `_plateau_metrics`（`src/cfd_sdf/fd08_calibration.py`）と同じ `max(|q_ref|, floor/ε_min)`。結果に対する閾値は書かない。
- **A3' LOO 表**: §3 の 3 値で、系列 × 区間 × 閾値水準（10/30/50 µN）。
- **A3'' q の誤差見積もり表**: 力のノイズ想定 σ ∈ {2, 3, 4} µN を**入力パラメータ**として、各 ε の σ/ε [N/m] と、各系列の |q_ref| に対する比（%）。σ は観測の仮定であり測定値ではない、と明記する。
- **A4 連続汎関数の奇偶分解（ソルバー不要）**: 正準 state と方向（§2 の次元順）から、`phi ± ε d` を float32 化して作る（式 `np.asarray(base.astype(np.float64) + sign*eps*d, np.float32)`。保存済みの state raw と**一致することを確認**してから使う）。ε は R5 の 7 点に、0.05〜50 mm の対数等間隔 40 点を加える。次を ± で計算する。
  - (a) 固体率の総和 `Σ clip(0.5 − phi/h, 0, 1) h³`（h = 25 mm の SDF 格子幅）。
  - (b) 同じ式で h = 33.33 mm（流体セル幅）。
  - (c) 三線形補間した零等値面が囲む体積（実装が重い場合は (a)(b) のみでよい。理由を書く）。
  - 各汎関数の奇数部 O(ε) = (F(+ε) − F(−ε))/2 を ε で割った値と、偶数部 (F(+ε) + F(−ε))/2 − F(0) を、方向ごとに出す。q(ε) との並置図を作る。
  - 事前の記載: 「SDF 格子の辺の符号反転数は、4718 ノードが |phi| < 1e-6 に載っているため ε にほぼ依存せず、情報量がない」。これは確認済みの事実として書き、数え直す必要はない。
  - 限界を明記: これは SDF 格子の代理で、WaterLily 流体セルの cut/mask（normal_floor を含む）そのものではない。『連続汎関数に折れが見えない』を『cut 切替がない』と読める表現は使わない。
- **A5 要約**: 数値と 3 値のみで答える。判断・原因・gate の適否は書かない。
  1. 3 つの連続 5 点窓について、系列ごとの最大偏差が最小の窓はどれか（数値のみ）。
  2. 3 区間の g のずれが大きい系列の順位（数値）。
  3. LOO が定義できる系列・区間と、できないもの（undeterminable の一覧）。
  4. D1 の奇数部 O(ε)/ε は D0 に比べて桁でどれだけ小さいか（数値）。

## 5. 成果物・決定性・検証

- 単体スクリプト `scripts/diagnose_fd08_r5_posthoc_p2a.py`（入力 hash 検証、定数は §3、決定的）。
- `docs/evidence/fd08_candidate_c_calibration_2026_10_04_r5/post_hoc_p2a/`: 結果 JSON（`sort_keys=True`, `allow_nan=False`）、`SHA256SUMS`（**JSON と note だけを hash 固定**。PNG は matplotlib の版で変わるため、hash は参考記録に留める）、日本語 note `P2a_diagnostic_note.md`、図。P1 のファイルは変更しない。
- note 冒頭: 証拠区分 `solver_free_post_hoc_calibration_diagnostic_unregistered`、§1 の禁止事項、§3 の定義、R5 の確定 FAIL、全 flag false、「P1・計画の表を見た後の記述用定義である」旨。
- 合計の和は `math.fsum`。
- テスト: 分解・LOO（3 値）・窓表・汎関数の小さな合成例、`compileall`、full pytest。**変更前に `bf44af0` で既知の失敗 ID を記録し、変更後と比較**（基準が一致しなければ報告）。`git diff --check`。
- ブランチ: integration `codex/kaggle-batch-migration` から `exp/issue46-p2a-diagnostic`、`--no-ff` で merge（ユーザー決定の運用。`docs/git_branching_strategy.md` の trunk 運用とは異なるため、note に「ユーザーの指示による」と書く）。#46 に結果を comment。

## 6. 独立検算（必須）

primary のスクリプトを見せない別担当に、**§2・§3・§4 の定義と入力パスだけ**を渡して A1〜A4 を再計算させる。共通のつまずき（1/900 換算、F/C 順、符号規約、undeterminable の扱い、窓表の正規化）は §3 に固定済みなので、checker にもそのまま渡す。不一致は note に記録して原因を特定する。

## 7. 停止点

成果物を #46 に報告して**止まる**。gate・定義・direction・ladder・R6 の判断は P2 のユーザー判断。R6 の criteria・registrar・runner には着手しない。
