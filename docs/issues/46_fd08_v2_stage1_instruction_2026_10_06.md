# #46 FD-08 契約 v2 段階 1 指示文 v2（codex 向け・solver 不要の実装と設計）

日付: 2026-10-06 / 起草: Claude / 実装担当: codex
ステータス: **指示案 v2。** v1 は対抗レビュー（1 体、評価器を実装して検証）で GO-WITH-CHANGES となり、下記を直した。
前提: `docs/issues/46_fd08_B_decision_plan_2026_10_06.md`（v2）。全 qualification flag は false。R5 は FAIL のまま。
基準: **この指示文と計画文書を integration へ merge した commit から branch を切る**（merge 前の `4eef582` からでは文書が存在しない）。

### v1 からの主な変更

- 受け入れ条件 A2「ε|ε| 型を 25% の曲率比で 80% 以上検出する」は **達成不能**と実測された（0.5〜5 mm では ε³ が ε|ε| を吸収し、g の偏りは約 5% にしかならない。検出は曲率比 100〜150% から）。**報告のみ**に変更し、検出範囲を測るためシナリオに曲率比 50/100/150/200% を追加。誤棄却の定義も、誤指定シナリオで矛盾しないものに直した。
- 数値を変える曖昧さ 14 点を仕様で固定（重みの pilot、SE、入れ子、holdout、単位、判定の優先順位、乱数など）。
- ladder の数値は `numpy.geomspace` で定義。ジッター設計を計画と整合。禁止事項と停止条件を具体化。

## 0. 範囲

やること: FD-08 契約 v2 の**評価器の実装**、**合成データでの性能測定**、**設計表と設計メモの作成**。すべて solver 不要で、結果を報告して**止まる**。

禁止:

- R6 / formal の登録、criteria・dataset の作成、Kaggle 操作、solver 実行。
- **R5 データへの評価器の適用（dry-run を含む）。** さらに、`docs/evidence/fd08_candidate_c_calibration_*` 配下のファイルを `src/`・`scripts/`・`tests/` から読み込まない（R5 の数値は、出典つきで設計表スクリプトに**手で書き写した定数**として使う）。
- 既存の登録済みコード・criteria・証跡の変更。`src/cfd_sdf/fd08_calibration.py`、`fd08_contract.py`、`scripts/register_fd08_*.py`、`analyze_fd08_calibration.py`、`post_hoc_p1/`、`post_hoc_p2a/` など。v2 は**新規ファイル**として追加する。変更が必要な箇所は設計表に列挙するだけで編集しない。
- **評価器（`src/cfd_sdf/fd08_v2_gate.py`）から `cfd_sdf.fd08_*` を import しない。**（登録済みコードへの結合を避ける。）
- パラメータ・tolerance・シナリオを、シミュレーション結果を見てから変更すること。**パラメータ JSON の sha256 を最初のシミュレーション実行の前に記録**し、以後の変更は規約違反として報告する（変更しない）。
- #23 のスコープ変更、direction の追加登録、`epsilon_m` の意味の変更の実施（設計表に書くだけ）。

未決の判断（B-3〜B-7）は、評価器・設計メモのどこでも**パラメータまたは選択肢**として記述し、決まったかのように固定しない。ladder も**設計の既定であって未決**と note に書く。

## 1. 成果物と配置

- `src/cfd_sdf/fd08_v2_gate.py`、`src/cfd_sdf/fd08_v2_gate_params.json`。
- `scripts/simulate_fd08_v2_gate.py`、`scripts/design_fd08_v2_tables.py`。
- `tests/test_fd08_v2_gate.py`（新規。既存テストとの名前衝突なし）。
- `docs/evidence/fd08_v2_stage1_2026_10_06/`: シミュレーション結果 JSON、設計表、日本語 note、設計メモ 2 本（`design_note_new_direction.md`、`design_note_predict_then_run.md`）、baseline の junit XML と failure ID 一覧、`SHA256SUMS`。
- JSON は `json.dumps(sort_keys=True, allow_nan=False)`、**浮動小数は有効数字 12 桁に丸める**。numpy の版を記録する。**JSON の hash は同一環境内の再現確認用で、機種間では参考値**と note に書く。図の hash は参考記録。
- baseline: 変更前に、**クリーンな worktree で** `4eef582` 相当（merge 前の既存テスト）の full pytest を実行し、junit XML と failure ID（既知 37 件）を上記ディレクトリに保存する。変更後と比較する。`compileall`、`git diff --check`。
- ブランチ: integration から `exp/issue46-fd08v2-stage1`、`--no-ff` で merge（ユーザー運用。`docs/git_branching_strategy.md` の trunk 運用とは異なる旨を note に書く）。意図したファイルだけを commit・push（`AGENTS.md`）。#46 に結果を comment。

## 2. 評価器の仕様（S1。曖昧さを残さない）

### 単位

ε は **mm**、S は **N**。当てはめは mm 単位で行い（正規方程式の条件数を悪化させないため）、出力する g だけを N/m に換算する（`g_n_per_m = g_n_per_mm × 1e3`）。換算は 1 つのヘルパー関数に集め、テストで確認する。q = S/ε [N/mm → N/m]。

### 入力

1 つの (direction, response) 系列の、ε の配列（昇順）、S の配列、パラメータ。**使う点は入力の全点**（評価器の中で点の選別はしない）。

### モデル

- A: `S = g·ε + c·ε³`。B: `S = g·ε + k·ε|ε|`。
- 推定: **重み付き最小二乗**、重み `w_i = 1 / (σ0² + (ρ·Ŝ_i)²)`。
  - Ŝ_i は **同じモデルを同じ点集合に対して重みなしで当てはめた値**（pilot）。**部分集合（入れ子・holdout）ごとに pilot も再計算する**。重みを使い回さない。
  - 反復は pilot → 重み → 重み付き当てはめの **1 回のみ**（固定点まで反復しない。1 回目と 2 回目で g が約 1e-4 異なることを note に注記）。
  - Ŝ が 0 付近でも `w ≤ 1/σ0²` で有限。pilot の符号は無関係。
- 共分散: `(XᵀWX)⁻¹`（**公称重みのまま、χ²/dof でスケールしない**）。`SE(g)` はその (1,1) 成分の平方根。**スケール版はフラグで切り替えて併記してよい**が、判定は非スケール版。
- 自由度は `n − 2`。判定にだけ使う（UNRESOLVED の条件）。SE の計算には入れない。

### 評価項目（direction・response ごと）

1. **符号**: 全点でのモデル A・B の g、および入れ子部分集合（下記）でのモデル A・B の g が、すべて同符号。
2. **相対 SE**: `SE(g_A)/|g_A| ≤ tol_se`。
3. **入れ子安定**: モデル A のみ。**最大 ε を 1 点ずつ落とす k = 1, …, nested_drop**（既定 2）。ただし **残りの点が 3 点以上**になる k だけ使う。各 k で `|g_A(k) − g_A(0)| / |g_A(0)|` の最大 ≤ `tol_nested`。項目 1 の入れ子も同じ部分集合（k = 1, …, 3、残り 3 点以上）を使う（A・B 両モデル）。
4. **モデル差**: `|g_A − g_B| / |g_A| ≤ tol_model`（全点）。
5. **内部 holdout**: 端点（最小・最大 ε）を除く各点を 1 点ずつ外し、**モデル A を重み付きで、pilot も再計算して**当てはめる。外した点の予測 `S_pred` に対して `|S_obs − S_pred| ≤ max(3·σ_pred, tol_hold·|S_pred|)`。`σ_pred = sqrt(σ0² + (ρ·S_pred)² + xᵀ(XᵀWX)⁻¹x)`（x は外した点の設計行）。全ての内部点で満たす。
6. **絶対量**: `|S| ≥ k_mag·σ0` を満たす点が 4 点以上。

判定: **計算可能な項目のどれかが不合格なら FAIL**（項目 6 が 4 点未満でも他が不合格なら FAIL）。全項目を満たせば PASS。**UNRESOLVED は、n < 4、自由度 < 1、または計算できる項目がない場合のみ**、ならびに項目 6 だけが不合格で他が全て合格のとき。出力は 3 値と全項目の数値（g_A, g_B, SE, 入れ子の各 g、相対ずれ、holdout の各誤差、点数、各項目の合否）。

### 既定パラメータ（暫定案・未承認。`fd08_v2_gate_params.json`）

`sigma0_n = 3.0e-6`、`rho = 0.05`、`tol_se = 0.10`、`tol_nested = 0.15`、`nested_drop = 2`、`tol_model = 0.15`、`tol_hold = 0.15`、`k_mag = 5`。
GitHub に根拠のない私の暫定値。σ0 は R6 のジッター測定で置き換える予定の仮定値。**感度表**: `tol_se`・`tol_nested`・`tol_model`・`tol_hold` の 4 つを同時に 5/10/15/20% に振る（`nested_drop`、`k_mag`、`σ0`、`ρ` は既定値のまま。note に書く）。

### ladder（設計の既定。**未決**。評価器は ladder に依存しない）

6 点: `numpy.geomspace(0.5, 5, 6)` mm。8 点: `numpy.geomspace(0.3, 5, 8)` mm。

## 3. 合成シミュレーション（S2）

`scripts/simulate_fd08_v2_gate.py`。乱数は `numpy.random.Generator(numpy.random.PCG64(seed_ij))`、`seed_ij = base_seed + 1000·(シナリオ番号) + (ladder の点数)`、`base_seed` は固定して結果に記録。**各点でノイズを先に、相対偏差を後に**引く（順序固定）。試行数は既定 2000。各シナリオで 6 点と 8 点の ladder の両方。

| シナリオ | 真値と観測 |
| --- | --- |
| a 範囲内・ノイズなし | q 形式 `q = g + c_q·ε²`（ε mm、c_q は N/m/mm²）、S = q·ε（ε を m に換算して N）。a1: g=−0.17、c_q=0。a2: g=−0.104、c_q=−0.00104。ノイズなし |
| b 範囲内・絶対ノイズ | a1・a2 に iid 正規 σ ∈ {1.5, 3, 4} µN |
| c D1 型の波打ち | a1・a2 に、S·(1 + w·z)（z ~ N(0,1) を ε ごとに独立、w ∈ {0.04, 0.07}）を作り、その後に σ=3 µN の絶対ノイズを足す |
| d 範囲外（ε\|ε\| 型） | `S = g·ε + k·ε|ε|`、g ∈ {−0.104, −0.17}（N/m）、**k の符号は g と同じ**、曲率比 `|k|·5 mm / |g|` ∈ {10, 15, 25, 50, 100, 150, 200}%、σ=1.5 µN。真の g は与えた g |
| e 弱い応答 | `|g| = 0.02 N/m`（0.5 mm で S≈10 µN）、σ=3 µN。c_q=0 |

### 出力（シナリオ × ladder × tolerance 水準 {5, 10, 15, 20}% 同時）

- PASS / FAIL / UNRESOLVED の割合。
- ĝ_A の偏り（中央値）と相対誤差の分位（p50、p90）。
- **誤通過**: PASS かつ `|ĝ_A − g_true|/|g_true| > 0.20` の割合。
- **誤棄却**: **a・b（σ ≤ 3 µN、モデルが正しい）のシナリオに限り**、FAIL かつ `|ĝ_A − g_true|/|g_true| ≤ 0.05` の割合。c・d・e では FAIL 率を報告するだけで、誤棄却のラベルは付けない。

### 受け入れ条件（**実行前に note 冒頭へ転記**。調整せず、満たさなければ §8 の停止）

- **A1**: シナリオ a・b（σ ≤ 3 µN）で、既定 tolerance の PASS 率 ≥ 95%。
- **A4**: **全シナリオ**で、既定 tolerance での誤通過率 < 5%。ただし曲率比 100% 以上の d は**報告のみ**（検出の限界を測るための範囲外）。
- **A2（報告のみ、合否なし）**: d の曲率比ごとの PASS 率と、PASS 率が 20% を下回る曲率比を報告する。0.5〜5 mm では ε³ が ε|ε| を吸収し、g の偏りは曲率比 25% で約 5% にすぎない。この範囲で検出を要求することは仕様に含めない。
- **A3（報告のみ）**: c・e の結果。

## 4. 設計表（S3）

`scripts/design_fd08_v2_tables.py`。R5 の実測値は出典つきの手書き定数（§0）。

- state 数と solver・経過時間: 入力は 108.7 秒/state（R5 の solver 実測 5,109.38 秒 / 47）、オーバーヘッド約 74 秒/state（経過 8,596.5 秒 / 47 − 108.7）、solver 合計上限 5,400 秒（`xfidc_criteria.json` の `measurement.aggregate_solver_wall_time_limit_s`）、kernel 上限 10,800 秒（`docs/phase_plan.md`）。設計: 方向 ∈ {3, 4, 5} × ε 点 ∈ {6, 7, 8} × 2 符号 + baseline ∈ {1, 5} + ジッター（§5、各方向 2 state）の全組合せ。上限超過を明示。
- 登録済みコードの変更が要る箇所。**実在する `file:line` を実行して確認してから書く**。対象: `fd08_calibration.py` の `FORMAL_EPSILON_COUNT`・`FORMAL_DIRECTION_IDS`（24-25 付近）、`MINIMUM_CALIBRATION_EPSILON_COUNT`・`MINIMUM_CALIBRATION_SPAN_RATIO`（28-29 付近）、`validate_calibration_ladder`・`_plateau_metrics`・`select_formal_epsilon_ladder`・`evaluate_formal_direction_response`・`aggregate_formal_verdict`、`fd08_contract.py` の `FRESH_QUALIFICATION_RUNS`・`PLATEAU_RELATIVE_LIMIT`・`MINIMUM_PLATEAU_POINTS`・`validate_fd08_design`、`register_fd08_formal.py`・`verify_fd08_formal.py`・`register_fd08_calibration.py`・`analyze_fd08_calibration.py`。
- `epsilon_m` の意味（名目か有効か）が影響する関数の一覧。

## 5. 設計メモ

- **ジッター反復（σ̂ の測定元）**: **各方向 2 state**（ladder の中央 ε_m に対し、`ε_m·(1 + δ)`、δ = 1e-3 の ± 1 ペア）。ジッター量は、ladder の当てはめ（モデル A）から外した予測 `Ŝ_A(ε_m(1+δ))` との差 `J = S_obs − Ŝ_A`（ジッター点は当てはめに含めない）。**線形でも S は ε に比例して変わり、立方項があると J は厳密には 0 にならない**（`≈ 2δ·c·ε³`。D0 drag で 5 mm のとき約 0.26 µN）。このため、単純な `S(ε(1+δ)) − S(ε)(1+δ)` ではなくモデル予測との差を使う。σ̂ は 4 方向 × 2 応答の J を**プールして推定**し、自由度と信頼区間（`χ²` 分布）を書く。方向ごとの自由度は 1。
- **B-6 `design_note_new_direction.md`**: 滑らかな低次の法線変位ローブの生成アルゴリズム案。入力は正準 state の変更ノード集合（4718 ノード）と法線。出力は max=1 規約の direction（float32、C 順）、実現変位（max、RMS、変更ノード数、全格子 RMS）、direction hash、float32 ゲートの確認。プロトタイプ生成器を scripts に置いてよいが、**読み取り専用で、dataset・evidence には登録しない**（evidence に置くのは設計メモだけ）。D0/D1/D2 の direction と hash は保護履歴で変更しない。力への応答の大きさは solver なしでは分からない、と明記。加えるか否かの判断材料（実装量、期待される利点）を書く。
- **B-7 `design_note_predict_then_run.md`**: calibration の (ĝ, ĉ) を固定し、どの当てはめにも使っていない内部の ε を新しく解いて、固定した予測と比較する設計。新しい ε の選び方（案: ladder の隣接 2 点の幾何平均）、予測と tolerance の式、state 数（4 方向 × 3 ε × 2 = 24）、**限界**（同じ solver・同じ direction なので「protocol の一般化」ではなく「当てはめの内挿予測」の検証）。取り置き direction との比較表（2 試行の 95% 下限 約 0.22 など）を付ける。
- **ladder の上端の判断材料（ユーザー判断 B-5 に関わる）**: 0.5〜5 mm では ε³ が ε|ε| を吸収するため、モデル差の項目はほぼ効かない。上端を 15 mm まで伸ばすと検出できるが、D0 の非線形域に入る。この**トレードオフを数値で並べる**（シナリオ d を上端 5 mm と 15 mm の両方で測る。上端 15 mm の ladder は `geomspace(0.5, 15, 7)`）。決めない。

## 6. 独立検算（必須）

別担当に、**§2 の仕様と §3 のシナリオ定義、固定の 20 個の合成データ（スクリプトが seed から生成して JSON に保存）だけ**を渡し、primary の**出力もコードも見せずに**評価器を再実装させる。比較は後で行う。20 個は、シナリオ a1・a2・b・c・d・e と ladder 6/8 点にまたがるように割り当て、対応表を JSON に残す。許容は数値の相対差 ≤ 1e-9（§2 の曖昧さを固定したので、重みの再計算の違いによる 5e-5 級のずれは出ない想定）。3 値判定が 1 つでも違えば、仕様の曖昧さとして note に記録し、原因を特定する。

## 7. note に必ず書くこと

証拠区分 `solver_free_design_and_simulation_unregistered`、§0 の禁止事項、受け入れ条件（**実行前の転記**）、パラメータ JSON の hash と「暫定案・未承認」、R5 に適用していないこと、未決の判断（B-3〜B-7、ladder）と、本成果物がそれを決めていないこと、全 flag false。

## 8. 停止条件

- 受け入れ条件 A1 または A4 を満たさない場合: **パラメータを調整せず**、他の成果物（設計表、設計メモ、`SHA256SUMS`）は作成し、note に「Stage 1 FAILED」と書き、満たさなかった条件と数値を示して #46 に報告し、止まる。
- 満たした場合も、成果物を #46 に報告して止まる。次の判断（B-3〜B-7 の確定、R6 の登録）はユーザー。
