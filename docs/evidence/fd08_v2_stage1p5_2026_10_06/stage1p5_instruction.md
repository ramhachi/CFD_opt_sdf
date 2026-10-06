対象リポジトリ: https://github.com/ramhachi/CFD_opt_sdf
integration: codex/kaggle-batch-migration
対象: Issue #46 FD-08
起草時点の integration HEAD: 5e67022374335aebe5eb7aba5c4c41f90f708628
直前の Stage 1:
- feature: exp/issue46-fd08v2-stage1 / implementation 9f007bc532670b8ae2bed7f4be8373a8e158a8f8
- integration merge: 5e67022374335aebe5eb7aba5c4c41f90f708628
- issue checkpoint: https://github.com/ramhachi/CFD_opt_sdf/issues/46#issuecomment-6011760254

今回の作業は **solver-free Stage 1.5** とする。

Kaggle・WaterLily・solver を実行しない。R6 を登録しない。formal を登録しない。R5 に v2 evaluator を適用しない。`docs/phase_plan.md` を変更しない（B-3〜B-7 はユーザー未承認のため。承認後に別作業で更新する）。

目的:
1. Stage 1 の 17 numeric mismatch を改竄せず、一般的な数値計算契約と比較規則を事前に固定して設計する。
2. B-3〜B-7・予算・ladder について、ユーザーが 1 回の判断で承認/却下できる decision packet を作る。
3. R6 実行前に残る科学的・実装上の曖昧さを列挙する。
成功条件は R6 を始めることではなく、**ユーザーが次の 1 回の判断で R6 契約を承認・却下できる状態**を作ること。

---

## 0. 開始時

- `git fetch`。integration HEAD、#46 最新コメント、`docs/phase_plan.md`、`docs/issues/46_fd08_B_decision_plan_2026_10_06.md`、`docs/evidence/fd08_v2_stage1_2026_10_06/`（特に stage1_note.md、design_tables.md、design_note_new_direction.md、design_note_predict_then_run.md、independent_spec.md、independent_comparison.json、independent_roundoff_diagnosis.json）、`src/cfd_sdf/fd08_v2_gate.py`、`src/cfd_sdf/fd08_v2_gate_params.json` を読む。
- integration が 5e67022 より進んでいたら、5e67022 を盲目的に checkout せず最新 integration から専用 worktree を作る。他 worktree には触れない。
- 推奨 branch: `exp/issue46-fd08v2-stage1p5-contract`
- 具体的な file:line を過去文書から信用しない。必要な箇所（solver 上限 5400 s、kernel 上限 10800 s、ladder 検証等）は**現 HEAD で再検索**して現在の行を記録する。

## 1. Stage 1 を固定事実として扱う（変更禁止）

- A1 PASS / A4 PASS / 20/20 verdict 一致 / 判定系 580 比較で不一致 0
- 数値 5,600 比較: 5,583 が純粋相対 1e-9 以内、17 が未達（最大絶対差 約 1e-16、すべて近ゼロ派生診断量）
- primary は N/mm のまま差を取り、blind 側は N/m 換算後に差を取る。純粋相対条件には形式上 FAIL。

Stage 1 evidence は immutable。PASS へ書き換えない、tolerance を適用し直して PASS にしない、17 件を削除しない、primary/blind のコードを編集して一致させない。Stage 1.5 の最終 note には「historical Stage 1 strict numeric condition: unmet 17」「root cause: explained/unexplained」「将来の canonical arithmetic 推奨」「将来の独立比較規則の推奨」を**別項目**として書く。

## 2. 数値セクション（§2〜§4 + §13）と停止条件

**このセクションで stop 条件に該当したら、§5 以降（B-3〜B-7・予算・ladder 設計）へ進まず、そこで停止して #46 に報告する。**

停止条件:
(a) 高精度参照との比較で、primary か blind のどちらかが verdict または 3 値判定に影響する本質的なアルゴリズム差を持つと判明した場合
(b) 事前凍結した比較規則が未見 seed fixture で説明不能に外れた場合（規則を調整して通さない）
(c) 数値契約の候補間で verdict が変わる場合

### 2.1 arithmetic variant（同じ数学モデルの数値実装比較）

新しい solver-free note `docs/issues/46_fd08_v2_numeric_contract_2026_10_06.md` を作る。

モデル S = g·ε + c·ε³（N/mm, mm）。mm→m で design matrix の列は **ε 列が 1e-3、ε³ 列が 1e-9 と別々にスケールする**。数学的に等価でも lstsq の条件数と丸め挙動は変わる。以下を比較する:

- N1: mm でフィットし、dimensionless 量（相対 SE、入れ子相対ずれ、モデル差）は単位換算を挟まず形成、g/SE の表示時のみ N/m。
- N2: SI（ε は m、g は N/m、高次係数もそれに対応）でフィット・派生量を計算。
- N3: ε_ref による明示的 column scaling（x=ε/ε_ref 等）。ε_ref は contract から一意に決まるもののみ。ladder が未決のため、**N3 は条件数・誤差の比較に留め、production 候補の確定は ladder 確定後に後送り**する。

選択は「結果に合わせる」のではなく原理ベースで書く（例: 「dimensionless 量は presentation-unit 換算の前に形成する」）。

### 2.2 高精度参照
`mpmath`（またはそれに準ずる任意精度）で、同じ入力・同じ WLS 手順（OLS pilot→WLS 一回、公称共分散）の参照実装を新規に書く。primary / blind / N1 / N2 / N3 それぞれの forward error（g、SE、共分散、nested shift、モデル差、holdout）を参照からの誤差として報告する。条件数（design matrix、weighted design）も記録する。これは**第三の独立実装ではなく参照**であり、primary のコードを読んだ人間/Codex が書いたものと明記する。もし独立性を主張するなら、primary を見ていない別担当に independent_spec.md のみで書かせ、その旨を記録する（必須ではない）。

### 2.3 比較規則（事前凍結が先）
比較規則 C1〜C4 を、**どの fixture の結果も見る前に**文書化して SHA-256 を固定する:
- C1 純粋相対（rtol=1e-9, atol=0）
- C2 混合許容。ただし atol を 17 件から逆算しない。
- C3 ULP（最終値の ULP は 17 件の原因に合わない。比較して不適合な理由を示すこと）
- C4 semantic（符号、有限/非有限、閾値側、verdict、tolerance への margin の一致）
- **C5（推奨候補）被演算子基準の cancellation-aware forward error**: 派生量 r=|g_sub−g_full|/|g_full| に対し、数値誤差を最終 r の ULP ではなく被演算子 g から導く。例えば概念的に |δr| ≲ C·u·(|g_sub|+|g_full|)/|g_full|（u=単位丸め誤差）。係数 C は演算経路・フィットの数値誤差（条件数）を含む形で**事前に式として定義**し、17 件を見て合わせない。

主量（g、SE、β、共分散）と近ゼロ派生量（入れ子ずれ、モデル差）で規則を分けるかを設計し、理由を書く。実データでは nested shift は 1e-3 を大きく超えるため、近ゼロ問題はノイズなし合成 fixture 特有の現象である旨も評価する。

### 2.4 未見 seed fixture による検証
規則の hash 固定の**後に**、Stage 1 の seed と重ならない新 seed（実行前に値を note に記録・固定）で fixture を生成し、primary/参照/blind 相当（新規 fixture には既存 blind を再実行しないなら、その旨）で検証する。さらに既存 20 入力にも同じ規則を適用し、17 件が規則下でどう分類されるかを**帰結として**報告する（規則の選択に使わない）。R5 の force/result/analysis は使わない。

### 2.5 canonical state について
canonical state NPZ の SHA-256 は `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`、canonical Float32 phi（Fortran 順 raw）の SHA-256 は `e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`（`src/cfd_sdf/fd08_contract.py` の定数と照合）。表記を混同しない。

## 3. B-3〜B-7 の decision-ready 化（§2 の停止条件に当たらなかった場合のみ）

### 3.1 B-3 estimator / model
- 重みの定義を式で固定: w_i = 1/(σ0² + (ρ·S_pilot,i)²)（1/分散）。NumPy 実装では行に √w_i を掛ける。B 計画の「1/√(σ0²+…)」表記との対応を式で示し、曖昧さを除く。
- nominal 共分散 (XᵀWX)⁻¹ で χ² スケーリングをしない案の仮定、σ0/ρ が誤っていた場合の影響、sandwich 共分散との違いを説明（変更はしない）。
- モデル A/B の g 差の検出力について、Stage 1 の合成結果から「検出できたもの/できなかったもの」を明確化（曲率比 25% で 100% PASS の意味＝5 mm 上端では ε³ が ε|ε| を吸収して検出できない）。「A4 が良かったからモデル仕様が十分」とは書かない。

### 3.2 B-5 tolerance（δ を Codex が作らない）
- T1: **ユーザーが GRAD-03/#23 の誤差基準 δ を指定した場合の error-budget 接続図**として記述する。#23 に数値 δ は存在しないため、Codex は δ を発明しない。例示する場合は必ず `arbitrary illustration` と明記する。#23 の既存 criteria と衝突し得る箇所を正確に列挙する。
- T2: 現 Stage 1 の provisional params（tol_se、tol_nested、tol_model、tol_hold、k_mag、sigma0_n、rho、nested_drop）を 1 表にし、各値を measured / derived / engineering choice / synthetic-calibrated / arbitrary-provisional に分類して意味・出所を示す。「Stage 1 で良かったから」は根拠にならない。

### 3.3 B-4 coverage（#23 の scope は変更しない）
- COV-A: 登録した全 direction で drag/downforce 両方 PASS。
- COV-B: direction ごとに独立 qualify、事前固定の一般 coverage 条件（例: 4 方向中 3）。#23 の「every registered direction」の意味変更、optimizer が使う gradient space、LOWDIM-01、full-field gradient との関係を整理。
- D1 だけを恣意的に除外する案は禁止（一般 coverage contract のみ）。

### 3.4 B-6 新 direction（生成・登録はしない）
- 既存 design_note_new_direction.md を再利用して具体化。smooth low-frequency normal displacement lobe を最低 1 案（可能なら 2〜3 案）: 解析定義、局所化、符号規約、support、正規化、最大/RMS 変位、canonical v17 への適用法、Float32 changed-node audit、hash 生成契約。
- **許可**: canonical state NPZ（`generate_directions(state)` で正準 state から D0/D1/D2 を再生成）と保護済み `src/cfd_sdf/gradients/directional_fd.py` を使った、D0/D1/D2 との L2 内積・cosine・RMS・max norm・support overlap の算出。
- **禁止**: R5 の force/result/analysis/dataset 内の direction raw を読むこと、force 応答を計算すること。
- canonical state NPZ がローカルに存在しない場合は**相関計算を「未実施」と記録して止め**、値を作らない。

### 3.5 B-7 formal independence
- predict-then-run を第一候補として詳細化。calibration で固定した ĝ・ĉ・共分散・モデル同一性から S_pred(ε) を作り、**どの当てはめにも使っていない interior ε**（calibration ladder の隣接 ε の幾何平均など、ladder 確定後に contract から自動生成される規則）の ± pair と比較する。評価量: 絶対予測誤差、標準化誤差、相対誤差、符号。
- **明記**: solver が決定論的なので、これは独立 noise validation ではない。検証されるのは主として「calibration 点から固定した応答モデルが、未使用の phi byte 列（未使用の interior ε）へ補間できるか」である。外挿は検証しない。
- formal の判定基準は calibration 結果を見てから作れない構造にする（B-5 と同時に事前固定）。

### 3.6 jitter（既存分析を再利用し、3 択を表にする）
design_note_new_direction.md は既に次を整理済み。再調査せず引用すること: 1 magnitude の ± pair は 2 state/方向、2 magnitude なら 4 state/方向。1 magnitude では direction×response あたり J が 1 個。exact repeat は bit 同一（床 1e-8 N）。jitter residual には model bias・fit uncertainty・deterministic ε variation が混ざり、「noise の単独測定」とは呼べない。
decision table には **「2 state/方向」「4 state/方向」「jitter なし」** の 3 択を、得られる情報・自由度・状態数・予算・科学的依存関係とともに載せる。jitter を exact repeat / ε micro-jitter / grid-phase jitter / time-window / model residual と混同して同じ σ0 に混ぜない。

### 3.7 予算（現 HEAD で上限を再検索）
- 現行: solver 合計上限 5400 s、kernel 上限 10800 s（現 HEAD で該当コード/文書を再検索して場所を記録）。R5 実績 約 108.7 s/state。
- 57 state: solver 6195.9 s、elapsed 約 10413.9 s（design_tables.md）。20% margin なら solver 約 7435 s、elapsed 約 12497 s が必要で、**両上限とも不足**する旨を表に書く。
- Budget A（両上限を引き上げ、少なくとも 20% margin）/ B（kernel 分割。同一 criteria/source/dataset identity を維持できるか）/ C（state 削減。6 点回帰・holdout 能力を壊さない）/ D（jitter を別 round へ分離。科学的依存関係を明示）を比較。5400 秒に収めるために意味のある state を削らない。

### 3.8 R6 ladder 候補
複数案（6 点以上、0.5〜5 mm 周辺、15 mm 上端比較、回帰条件数、曲率同定、holdout/predict-then-run との分離、Float32 perturbation 分解能）。旧 contract（7 点以上・100× スパン）を変えるなら、旧 contract が v2 回帰 gate に不適切な理由を「R5 が FAIL したから」以外で説明する。確定しない。

## 4. 依存順（decision table に DAG として記載）
numeric contract → B-3 estimator/model → B-5 tolerance → ladder/jitter → B-6 direction inventory → B-4 coverage → B-7 formal。各決定が前段の何に依存するかを明記する。

## 5. 独立レビュー（役割分離。primary の結論を渡して追認させない）
- Review 1 numerical: arithmetic variant、条件数、forward error 式、C5 の係数 C の事前定義、未見 seed 検証。
- Review 2 scientific contract: B-3〜B-7、coverage、formal の interpolation 性、jitter の位置づけ。
レビューには prompt/spec のみを渡す。意見が割れたら decision table にユーザー判断として残す。

## 6. 成果物
- `docs/issues/46_fd08_v2_stage1p5_decision_packet_2026_10_06.md`
- `docs/issues/46_fd08_v2_numeric_contract_2026_10_06.md`
- `docs/evidence/fd08_v2_stage1p5_2026_10_06/`: numeric_contract.md、arithmetic_comparison.json、ulp_comparison.json、comparison_rule_freeze.json（規則 hash と fixture seed を実行前に固定）、unseen_seed_validation.json、coverage_options.md、tolerance_options.md、direction_design.md、formal_predict_then_run_design.md、jitter_options.md、budget_table.md、ladder_candidates.md、independent_numerical_review.md、independent_scientific_review.md、validation（JUnit 圧縮、failure IDs）、SHA256SUMS
- 新規ファイルのみ。既存ファイル変更 0（`docs/phase_plan.md` を含む）。

## 7. 最終決定表（ユーザー提示用）
| ID | 決定事項 | Option A | Option B | Codex 推奨 | 根拠 | 依存 |
N-1 arithmetic / N-2 independent tolerance（C1〜C5）/ B-3 / B-4 / B-5 / B-6 / B-7 / J-1 jitter（2・4・なし）/ P-1 solver 予算 / L-1 ladder。

さらに、**「この推奨セットを承認した場合にだけ R6 を登録する」という 1 本の recommended configuration** を出す。

## 8. やってはいけないこと
R5 へ v2 gate を適用しない / R5 verdict を変更しない / R6 criteria・dataset v6・direction・formal を登録・生成しない / Kaggle submit・WaterLily・solver 実行をしない / fresh33 を実行しない / #23 scope・qualification flag を変更しない / Stage 1 の 17 件を削除しない / Stage 1 の comparator tolerance を後から変えて PASS 扱いにしない / `docs/phase_plan.md` を変更しない / R5 の force・result・analysis を読まない / δ を発明しない（例示は arbitrary illustration と明記）。

## 9. 検証と Git
- focused tests、`.venv/bin/python -m compileall src tests`、`git diff --check`、full `pytest`、baseline failure ID 集合の比較（baseline は 37 failed。新規 failure 0 が条件）、evidence hash 検証。コマンド・結果・artifact path・hash・evidence class を結論と分けて記録する。
- 意図したファイルのみ commit。レビュー後 `--no-ff` で `codex/kaggle-batch-migration` へ merge。main は触らない。#46 に結果をコメント。force-push・reset・他作業の上書きはしない。

## 10. 停止点と最終報告
成果物と決定表が完成したら停止。**R6 登録前で必ず止まる。** ユーザー判断なしで Stage 2 へ進まない。
最終報告に必ず含める: integration commit / Stage 1 historical strict mismatch 17 件がそのままであること / 数値契約の推奨と停止条件に当たったか / B-3〜B-7 の推奨 / R6 候補 state 数 / solver・kernel 予算（20% margin 込み）/ 未決事項 / R6 未登録 / solver 未実行 / 6 つの qualification flag が false / `docs/phase_plan.md` 未変更。