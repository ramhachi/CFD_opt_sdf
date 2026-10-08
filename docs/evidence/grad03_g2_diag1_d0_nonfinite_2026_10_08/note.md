# G2-DIAG1 結果: **DIAG_LOCALIZED**（診断。gradient の qualification ではない）

事前登録（`prerun_note.md`、`prerun_freeze.json` SHA `215ed319…`）どおりに T4 で 1 回実行し、host の terminal 検証（manifest の SHA・DONE/ERROR の排他・source/pin/入力 hash/runtime source hash・flag false・dryrun false・snapshot 57 個の SHA）が PASS した出力に対して、
`scripts/analyze_grad_g2_diag1.py` を 1 回だけ実行した（`diag1_analysis.json`、SHA `d3e2deee…`）。bridge analyzer は呼んでいない。bridge の値・δ・GRAD-03 verdict は存在しない。reverse は未着手。6 flag は false。

- kernel: `ramhachi888/cfd-opt-sdf-grad-g2-d0-nonfinite-diag1` version 1、source `2cd713a588da…`、runner SHA `47276166…`、Tesla T4、Julia 1.12.6、CUDA.jl 6.3.1、WaterLily 1.8.0。所要約 11 分（reference 87 s、instrumented 256 s）。
- preflight（GPU 上の統計処理）は成功し、host への fallback は使われなかった。

## 登録した規則での結果
- **G2 の失敗を再現**: reference run が step 1200・`t=16.409412384033203` で G2 attempt 1 と同一の失敗（bit 同一の時刻表現）。
- **非干渉**: reference と instrumented の状態 checksum が 1197 steps すべてで一致、SHA-256 51 点も一致（観測は状態を変えていない。非決定性の兆候なし）。
- **最初の非有限**（B の ledger から独立に再導出して kernel の `first_bad.json` と一致）:
  - step **1196**（step 開始時刻 `t = 16.3407` tU/L。G2 が検出した step 1200 より 4 steps 早い）、stage **`correct_conv_diff`**（corrector の対流・拡散の直後）、field **`f`**、component **tangent のみ**（要素 class **B: primal 有限・tangent 非有限**）。
  - index `(24, 61, 40, 1)`（物理座標 `(−1.75, 0.783, 0.383)` m、sdf = 38.5 セル、帯域外・上流側の遠方場）。非有限値: primal `−6.607e−06`（有限）、tangent `Inf`。
  - 直前の有限値: 同 field の max|tangent| = `6.0e+37`、max|primal| = `1.23`。最後に全て有限だった stage は同 step の `project1_bc`。
- **primal は終始健全**: 全 field で primal の非有限は一度も出ない。`max|u|` は step 500 以降 1.231 で一定（primal は準定常）。
- **tangent の成長**（u の max|tangent|、失敗前 100 steps）: 1 step あたり約 ×1.26（0.0975 decade/step、線形近似 R² = 0.992、最大の 1 step 上昇 0.32 decade）。パターン = `roughly_exponential`。失敗直前の log10 = 37.4（Float32 の上限は約 38.5）。
- **Poisson**: 直前 20 steps の反復は 1 回（itmx = 32 に達した steps は 0 %）。収束はしている。`r₂` の tangent は 1e28 級で、最終 step で NaN。
- **力**: 力の非有限（`candidate_pressure_x_tan`）は step 1196 で、state の非有限と同じ step。直前の力の tangent は 1e33〜1e34 級（candidate）、ground の z 成分も 8e33（ground 側にも同じ成長）。
- **幾何**: 静的監査に非有限なし。tangent の範囲は有限（μ₀ 最大 30、μ₁ 最大 23.8）。幾何は成長の原因ではない。

## 事前登録した分類（機械的）
- **Case A**（tangent のみが非有限、パターンが roughly_exponential、直前の log10 ≥ 30）→ 機械的な次の実験の提案: *Float64 Dual の precision discriminator が強く正当化される*。
- **H1 supports**（Float32 の tangent の dynamic range overflow）、**H2 supports**（有限だが不安定な tangent 動力学。step 100 から失敗前まで ≥ 3 decade 増加）、
  **H3 refutes**（最初の bad は帯域外で、幾何は有限）、**H4 refutes**（Poisson は毎回 1 反復で収束、itmx 到達 0 %）、**H5 refutes**（同 step に state の非有限がある）、**H6 refutes**（再現し、非干渉が一致）。

## post-hoc の観測（事前登録の規則の外。解釈は未検証）
- tangent の成長は**全期間ではなく、step 約 849（t ≈ 11.6 tU/L）に始まった**。step 400〜849 は max|tangent| の log10 が 1.32 で完全に一定で、その位置は物体近傍のセル `(59, 48, 21)`（tangent も準定常）。
  step 850 で最大点が `(6, 4, 51)` 付近へ移り、以後は同じ領域（x ≈ −2.35 m、y ≈ −1.12 m、z ≈ 0.75 m の**遠方場の角**、sdf ≈ 50 セル）で指数的に成長を続けた（step 1196 の最大点は `(7, 4, 53)` を含む同領域。step 1192〜1195 は上流側の別の遠方場セルが最大になる）。
  つまり不安定な tangent モードは**物体ではなく遠方場の境界付近**から立ち上がっている（primal は定常のまま）。原因（境界条件・exit BC・時刻 Dual の伝播・線形化系の不安定モード等）はこの診断では特定していない。
- 成長率が一定（0.0975 decade/step）と外挿すると、Float32 の上限（log10 ≈ 38.5）を超えるのは step 約 1200。**Float64（log10 ≈ 308）でも step 約 4000 で超える**。登録済み窓 [80,120] tU/L は約 8,740 steps なので、成長が飽和しない限り、Float64 でも long-window の bridge は完成しない可能性が高い。
  したがって Case A の機械的な提案（Float64 の precision discriminator）は、「成長が飽和するか／原因が遠方場境界の人工的なモードか」を先に診断しない限り、解決策にならない可能性がある（推測であり、次の実験はユーザーの判断）。

## 保存した証拠
`kernel_output/`（ledger・index・first_bad・localization・Poisson・force・幾何・selfcheck・snapshot の SHA index・manifest・log。`stage_ledger.csv` は gzip、約 8 MB）。
大きな raw snapshot（57 ファイル、543 MB）は git に入れていない。kernel の出力（`/Users/sota/kg_diag1/out1/`）に保存済みで、manifest に SHA がある。
`cpu_dryrun_diagnostic/`（code-path の確認、科学データではない）、`independent_reviews.md`、`identity_free_check.json`。G2 attempt 1 の namespace は変更していない。

## 次のユーザー判断（推測で進めない）
1. Float64 Dual の precision discriminator（上の外挿からは単独では不十分な可能性）
2. 遠方場の角から立ち上がる tangent モードの局所診断（offending stage `correct_conv_diff` と境界条件・exit BC の寄与の切り分け）
3. Poisson derivative の診断（H4 は refuted なので優先度は低い）
4. long-window forward bridge の断念
