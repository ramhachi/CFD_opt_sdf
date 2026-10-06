# #46 FD-08 契約 v2 段階 1 指示文（codex 向け・solver 不要の実装と設計）

日付: 2026-10-06 / 起草: Claude / 実装担当: codex
ステータス: **指示案。** 前提: `docs/issues/46_fd08_B_decision_plan_2026_10_06.md`（v2）。全 qualification flag は false。R5 は FAIL のまま。
基準 commit: integration `4eef582`（P2a 統合後）。

## 0. 範囲

やること: FD-08 契約 v2 の**評価器の実装**、**合成データでの性能測定**、**設計表と設計メモの作成**。すべて solver 不要で、結果を報告して**止まる**。

やらないこと（禁止）:

- R6 / formal の登録、criteria の作成、dataset 作成、Kaggle 操作、solver 実行。
- **R5 データへの評価器の適用（dry-run を含む）。** R5 の 0.5〜5 mm 帯は 3 点で、自由度 1・holdout なしのため証拠にならない。
- 既存の登録済みコード・criteria・証跡の変更（`src/cfd_sdf/fd08_calibration.py`、`fd08_contract.py`、`scripts/register_fd08_*.py`、`analyze_fd08_calibration.py`、`post_hoc_p1/`、`post_hoc_p2a/` など）。v2 は**新規ファイル**として追加する。登録済みコードの変更が必要な箇所は、設計表に列挙するだけで編集しない。
- パラメータ値をシミュレーション結果に合わせて調整すること。受け入れ条件を満たさない場合は、調整せず報告して止まる。
- #23 のスコープ変更、direction の追加登録、`epsilon_m` の意味の変更の実施（設計表に書くだけ）。

未決の判断（B-3〜B-7）は、評価器・設計メモのどこでも**パラメータまたは選択肢**として実装・記述し、決まったかのように固定しない。

## 1. 成果物と配置

- `src/cfd_sdf/fd08_v2_gate.py`（評価器）、`src/cfd_sdf/fd08_v2_gate_params.json`（既定パラメータ。sha256 を result に記録）。
- `scripts/simulate_fd08_v2_gate.py`（合成シミュレーション）。
- `scripts/design_fd08_v2_tables.py`（state 数・予算・登録済みコード変更箇所の設計表）。
- `tests/test_fd08_v2_gate.py`。
- `docs/evidence/fd08_v2_stage1_2026_10_06/`: シミュレーション結果 JSON、設計表、日本語 note、`SHA256SUMS`（JSON と note のみ hash 固定。図の hash は参考記録）。
- 設計メモ 2 本（日本語、同ディレクトリ）: `design_note_new_direction.md`（B-6）、`design_note_predict_then_run.md`（B-7）。
- ブランチ: integration から `exp/issue46-fd08v2-stage1`、`--no-ff` で merge（ユーザー運用。`docs/git_branching_strategy.md` の trunk 運用とは異なる旨を note に書く）。#46 に結果を comment。
- 変更前に `4eef582` で既知の failure ID（37 件）を記録し、変更後の pytest と比較する。`compileall`、`git diff --check`。

## 2. 評価器の仕様（S1）

### 入力

1 つの (direction, response) 系列に対して、ε [mm] の配列、S [N]（中心差分 (R(+ε) − R(−ε))/2）の配列、パラメータ。単位は ε を **mm**、S を **N**、g を **N/mm**ではなく **N/m**（q = S/ε を N/m にして扱う）で統一し、変換は 1 か所に集める。

### 主モデルと代替モデル

- 主モデル A: `S = g·ε + c·ε³`。代替モデル B: `S = g·ε + k·ε|ε|`。
- 推定: **重み付き最小二乗**。重み `w_i = 1 / (σ0² + (ρ·Ŝ_i)²)`。Ŝ_i は同じモデルの**重みなし最小二乗の当てはめ値**を使い、**1 回だけ**反復する（決定論的。2 回目以降は行わない）。σ0 [N] と ρ はパラメータ。
- 共分散は `(XᵀWX)⁻¹`（W はこの重み）。g の標準誤差 `SE(g)`。自由度は `n − 2`。

### 評価項目（direction・response ごと）

使用点は ε の昇順、使える帯の全点。

1. 符号: モデル A・B の g、入れ子（最大 ε を 1 点ずつ落とした部分集合、n ≥ 4 のとき n−3 点が残るまで）の g が、全て同符号。
2. 相対 SE: `SE(g_A)/|g_A| ≤ tol_se`。
3. 入れ子安定: 最大 ε を最大 `nested_drop`（既定 2）点まで落とした g_A の、フル g_A に対する相対ずれの最大 ≤ `tol_nested`。
4. モデル差: `|g_A − g_B| / |g_A| ≤ tol_model`。
5. 内部 holdout: 端点を除く各点を 1 点ずつ外して当てはめ、外した点の S を予測する。誤差 `|S_obs − S_pred| ≤ max(3·σ_pred, tol_hold·|S_pred|)`。`σ_pred = sqrt(σ0² + (ρ·S_pred)² + Var(S_pred))`（`Var` は当てはめの予測分散）。全ての内部点で満たす。
6. 絶対量: `|S| ≥ k_mag·σ0` を満たす点が 4 点以上。

判定: 全て満たせば **PASS**。いずれかを満たさなければ **FAIL**。計算不能（n < 4 または自由度 < 1、または 6 で 4 点未満）は **UNRESOLVED**（FAIL とは区別）。出力は 3 値と、全項目の数値（g_A, g_B, SE, 入れ子 g, 相対ずれ, holdout 誤差, 点数）。

### 既定パラメータ（暫定案、`fd08_v2_gate_params.json` に置き、hash を記録。B-5 で変更される）

`sigma0_n = 3.0e-6`、`rho = 0.05`、`tol_se = 0.10`、`tol_nested = 0.15`、`nested_drop = 2`、`tol_model = 0.15`、`tol_hold = 0.15`、`k_mag = 5`。
これらは GitHub に根拠のない私の暫定値。**感度表（`tol_*` を 5/10/15/20% に同時に振る）**を必ず出す。σ0 は R6 で測定するジッターから置き換える予定で、ここでは仮定値。

### ladder（設計の既定。実装は ladder に依存しない）

0.5〜5 mm、6 点の等比（0.5, 0.793, 1.260, 2.000, 3.175, 5.0 mm 目安）。

## 3. 合成シミュレーション（S2）

`scripts/simulate_fd08_v2_gate.py`。乱数は `numpy.random.Generator(PCG64(seed))`、seed と各シナリオの試行数（既定 2000）を結果に記録。各シナリオで、**ladder 6 点（0.5〜5 mm 等比）と 8 点（0.3〜5 mm 等比）**の両方を測る。真値を次のとおり生成する（`g` は q の主値 [N/m]、単位 §2）。

| シナリオ | 真値の S(ε) | 観測 |
| --- | --- | --- |
| a 範囲内・ノイズなし | q 形式 `q = g + c_q·ε²`（ε は mm、c_q は N/m/mm²）。a1: g=−0.17、c_q=0（D2 drag 型）。a2: g=−0.104、c_q=−0.00104（D0 drag 型。R5 の q が 0.5 mm で −0.105、5 mm で −0.130 になる値）。S = q·ε | ノイズなし |
| b 範囲内・絶対ノイズ | a に iid 正規 σ ∈ {1.5, 3, 4} µN | |
| c D1 型の波打ち | a に ε ごとの独立な相対偏差 N(0, w²)（w ∈ {0.04, 0.07}）× S | と b の σ=3 µN |
| d 範囲外（ε\|ε\| 型） | `gε + kε|ε|`、5 mm での q の曲率比（k·5 mm / g）が **10%・15%・25%**、σ=1.5 µN | 真の g との偏りを併記 |
| e 弱い応答 | `|g| = 0.02 N/m`（0.5 mm で S≈10 µN）、σ=3 µN | |

出力（シナリオ × ladder × tolerance 水準 {5, 10, 15, 20}%）:

- PASS / FAIL / UNRESOLVED の割合。
- 「誤通過」= PASS かつ `|ĝ_A − g_true|/|g_true| > 0.20` の割合、「誤棄却」= FAIL かつ `|ĝ_A − g_true|/|g_true| ≤ 0.05` の割合。
- ĝ_A の偏りと誤差の分位（中央値、p90）。

### 受け入れ条件（**実行前に note 冒頭へ転記**。これは私の提案値で、満たさなければ調整せず報告して止まる）

- A1: シナリオ a・b（σ ≤ 3 µN）で、既定 tolerance の PASS 率 ≥ 95%。
- A2: シナリオ d の曲率比 ≥ 25% で、**FAIL（または UNRESOLVED）の割合 ≥ 80%**（ε\|ε\| 型の誤指定を検出できること）。
- A3: シナリオ c・e は**報告のみ**（受け入れ条件なし）。
- A4: 誤通過率が、全シナリオで既定 tolerance のとき 5% 未満。

## 4. 設計表（S3）

`scripts/design_fd08_v2_tables.py` が次を出す（数値は R5 の実測を定数として使い、出典を note に書く）。

- state 数と solver 時間・経過時間の表。入力: 108.7 秒/state（R5 の solver 実測）、オーバーヘッド約 75 秒/state、上限 5,400 秒、kernel 上限 10,800 秒。設計: 方向 ∈ {3, 4, 5} × ε 点 ∈ {6, 7, 8} × 2 符号 + baseline {1, 5} + ジッター反復（各方向で 2 state、§5）の全組合せ。上限超過を明示する。
- 登録済みコードの変更が要る箇所（`file:line`）。`fd08_calibration.py` の `FORMAL_EPSILON_COUNT`・`FORMAL_DIRECTION_IDS`・`validate_calibration_ladder`（7 点以上・100 倍スパン）・`_plateau_metrics`・`select_formal_epsilon_ladder`・`evaluate_formal_direction_response`・`aggregate_formal_verdict`、`fd08_contract.py` の `FRESH_QUALIFICATION_RUNS`・`PLATEAU_RELATIVE_LIMIT`・`MINIMUM_PLATEAU_POINTS`・`validate_fd08_design`、`register_fd08_formal.py`・`verify_fd08_formal.py`・`register_fd08_calibration.py`・`analyze_fd08_calibration.py`。**実在する行番号を確認して書く**（私の記憶の行番号は信用しない）。
- `epsilon_m` の意味（名目か有効か）が影響する関数の一覧。

## 5. 設計メモ

- **ジッター反復（σ̂ の測定元）**: 各方向で、中央の ε_m に対し `ε_m` と `ε_m·(1 + 1e-3)` の ± 計 2 ペア（4 state）を解く案。ジッター量は `J = S(ε_m(1+δ)) − S(ε_m)·(1+δ)`（δ=1e-3、S が ε に線形のとき 0 になる量）。state 数への影響は設計表に入れる。**解析式と、少ない自由度での σ̂ の不確かさ**を書く。
- **B-6 `design_note_new_direction.md`**: 滑らかな低次の法線変位ローブの生成アルゴリズム案。入力は正準 state の変更ノード集合（4718 ノード）と法線。出力は max=1 規約の direction（float32、C 順）、実現変位（max、RMS、変更ノード数、全格子 RMS）、direction hash、`audit_float32_perturbation` と同じ float32 ゲートの確認。**プロトタイプ生成器を scripts に置いてよいが、dataset 登録・evidence 登録はしない。**D0/D1/D2 の direction と hash は保護履歴で変更しない。力への応答の大きさは solver なしでは分からない、と明記する。加えるか否かの判断材料（実装量、期待される利点）を書く。
- **B-7 `design_note_predict_then_run.md`**: calibration の (ĝ, ĉ) を固定し、どの当てはめにも使っていない内部の ε を新しく解いて、固定した予測と比較する設計。新しい ε の選び方（案: ladder の隣接 2 点の幾何平均、事前に規則で固定）、予測と tolerance の式、必要 state 数（4 方向 × 3 ε × 2 = 24）、**限界**（同じ solver・同じ direction なので、「protocol の一般化」ではなく「当てはめの内挿予測」の検証である点）を書く。取り置き direction との比較表（2 試行の 95% 下限 約 0.22 など）を付ける。

## 6. 独立検算（必須）

別担当に、**§2 の仕様と §3 のシナリオ定義だけ**（コードは見せない）を渡して、評価器を再実装させる。固定の 20 個の合成データ（スクリプトが `seed` から生成して JSON に保存）の出力を、primary と照合する。数値の相対差 ≤ 1e-9。3 値判定が 1 つでも違えば、仕様の曖昧さとして note に記録し、原因を特定する。

## 7. note に必ず書くこと

証拠区分 `solver_free_design_and_simulation_unregistered`、§0 の禁止事項、受け入れ条件（実行前の転記）、既定パラメータの hash と「暫定案・未承認」、R5 に適用していないこと、未決の判断（B-3〜B-7）と、本成果物がそれを決めていないこと、全 flag false。

## 8. 停止点

成果物を #46 に報告して**止まる**。次の判断（B-3〜B-7 の確定、R6 の登録）はユーザー。評価器のパラメータや tolerance を、シミュレーション結果に合わせて変更しない。
