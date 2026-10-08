# G2-DIAG1: D0 長時間 Dual 失敗の局在化 — 実行前の登録（未登録の診断）

証拠区分: `gpu_d0_nonfinite_localization_diagnostic_unregistered`。**診断のみ。** gradient の qualification ではない。
bridge の値を出さない。δ を選ばない。GRAD-03 の verdict を出さない。reverse（CPU/CUDA/custom adjoint）には触らない。
6 つの qualification flag（`fd_oracle` / `field_gradient` / `reverse` / `optimizer` / `topology` / `shape_update_allowed`）は false のまま。
この note と `prerun_freeze.json` は、T4 の最初の意味のある観測より前に固定する。G2 attempt 1 の evidence namespace
（`docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08/`）は immutable で、一切変更しない。

## 問い
G2 attempt 1 の D0（`Dual{Float32,1}`、canonical v17、Candidate C、flow_24）は step 1200（`t = 16.409412384033203` tU/L）で
force/tangent が非有限になった。**最初に非有限になる quantity / stage / step はどれか。その直前までの tangent はどう成長していたか。**
D0 のみ。窓 [80,120] には進まない。

## 開示（この note より前に見たもの）
- G2 attempt 1 の結果: plain Float32 は 8,740 steps で完走し registered baseline_v17 と bit 一致。D0 は step 1200 で非有限。partial history は保存されていない。D1/D2/P1 は未実行。
- CPU の code-path dry-run（D0、10 steps 以内、CPU Float32 Dual）を診断コードの動作確認として実行した。科学データではない。
  そこで見えた**1 点を開示する**: 最初の数 steps は Poisson が毎回 `itmx = 32` に達していた（H4 に関係しうる）。この観測は仮説の分類規則（下）には使っていない。
- instrumentation（stage コピー）が `sim_step!` と bit 単位で一致することを CPU で確認した（reference と instrumented の checksum が一致）。
- Poisson の収束判定（`r₂ < tol`）と反復の分岐は primal の値だけで決まる（ForwardDiff は Dual の比較を value で行う）。tangent は「この有限反復の離散アルゴリズム」を微分する。

## 固定する科学状態（G2 と同一。変更しない）
Candidate C / canonical v17（phi SHA `e3966d87…`）/ flow_24 / D0 bytes（SHA `d0af58bd…`）/ Float32 / CuArray / ForwardDiff Dual 幅 1 /
Poisson `tol = 1e-4`・`itmx = 32`（WaterLily 既定）/ 時間刻み（CFL）/ `remeasure = true` / ground semantics / force semantics（`-(pressure+viscous)`、candidate のみ）/ 初期状態 /
α の seed（α = 0 で 1、単位 m）/ 入力 hash。solver algorithm は変更しない。`build`・`load_raw`・`vp`・`sample_row` と定数は G2 script の verbatim コピー（テストで固定）。

## run 構成（1 つの kernel、D0 のみ）
- **A. reference**: 通常の `sim_step!`（G2 と同じ job 構造・8 steps ごとの `sample_row`・同じ失敗の意味）。G2 attempt 1 の失敗（step 1200、`t=16.409412384033203`）を再現するか確認する。
- **B. instrumented**: `measure!` と、WaterLily 1.8.0 の `mom_step!` の stage コピー（`scripts/waterlily_grad_g2_diag1_stages.jl`）を毎 step 実行。各 stage の直後に read-only の probe を挟む。
  stage 順（source の順）: `measure` → `pre_scale` → `predict_{conv_diff, accelerate, bdim, bc, exitbc}` → `project1_{rhs, solve, gradient, bc}` →
  `correct_{conv_diff, accelerate, bdim, scale, bc}` → `project2_{rhs, solve, gradient, bc}` → `cfl` → `cfl_dt` → 力（`force_candidate_{pressure,viscous,total}`、`force_ground_*`（取得できる場合））。
- 両 run とも毎 step、`u` と `p` の host copy から bit checksum（xor と和）と Δt の bit を記録し、25 steps ごとと snapshot step で SHA-256 を取る。
  **1 つでも不一致なら DIAG_INCOMPLETE**（観測が状態を変えた、または非決定性）。順序: A（GC）→ B。

## horizon
`step ≥ 1400` **かつ** `tU/L ≥ 20.0` に最初に達する step（指示の「少なくとも」を保守的に読んで、遅いほう）、上限 2000 steps。最初の非有限を B が検出したら、その step を最後まで観測して停止（fail-fast）。
full `[80,120]` window へは進まない。非有限が出なければ **DIAG_NOT_REPRODUCED** として保存し、自動で延長しない。

## 観測（B）
- **per-step ledger**（`stage_ledger.csv`）: 各 stage・各 field について primal / tangent を**別々に**: 要素数、非有限数（primal・tangent）、max|·|（非有限は除く）、RMS、argmax の index。
  対象 field は inventory（`inventory.json`、Flow と Poisson 全 level の Dual 配列）から決め、stage ごとの対象は `stage_order.json` と `stage_ledger.csv` に残る:
  `u⁰, u, f, σ(=Poisson z), p(=Poisson x), V, μ₀(=Poisson L), μ₁, D, iD, residual r, ε, 粗い level の L・x・r`、Δt（Dual のスカラー）。
- **Poisson**（`poisson_ledger.csv`）: 各 projection の反復数 `ml.n[end]`、`r₂ = L₂(p)` の値と tangent、Δt。RHS(`z`) / 解(`x`) / 残差(`r`) の primal・tangent norm は stage ledger。
- **力の分解**（`force_ledger.csv`、毎 step）: candidate の pressure / viscous / total（G2 と同じ符号・同じ式）、ground の pressure / viscous / total（取得できなければ unavailable と記録）。値と tangent。Fx と −Fz が drag / downforce。
- **幾何の静的監査**（`geometry_static_audit.json`）: step 1 の `measure!` 直後の σ(=sdf)・μ₀・μ₁・V の primal・tangent の範囲、非有限数、tangent の絶対値上位 10、帯域セル数、|∇sdf| の分位（記述のみ。判定に使う閾値は置かない）。毎 step の `measure` stage 行が「幾何は時間不変」の確認。
- **空間局在**（`localization.json`）: 最初の非有限の index → 物理座標（`x = origin + spacing·(I − 1.5)`）、sdf 値、|∇sdf|、帯域所属（|sdf|<3）、μ₀。保持した直近 12 steps それぞれの u の max|tangent| の位置とその局所情報（繰り返し同一セルか）。
- **snapshot**（raw、SHA は `snapshot_index.json`）: step 0, 2, 100, 500, 900, 1000, 1050, 1100, 1150, 1175, 1190, 1195, 1198, 1199 と、step ≥ 1000 の 25 steps ごと、直近 12 steps の ring（失敗時にまとめて書き出す）、
  最初の非有限の瞬間の状態（u, u⁰, f, p, σ, r, ε）。形式: `Dual{Float32,1}` 配列を column-major で、要素ごとに `value`・`tangent`（float32 LE）。
  **raw は git に入れない**（kernel の出力に保存し、SHA と manifest だけを evidence に置く）。
- 最初の非有限は `first_bad.json` に**検出した瞬間**に書く（値は `NaN` / `Inf` / `-Inf` の文字列表現も記録する）。`snapshot_index.json` は snapshot のたびに書き直し、`diag_index.json`（status RUNNING）は開始時に書く。
  kernel が時間制限で kill されても ledger と上記ファイルから部分解析できる。例外時は直近 12 steps の ring も書き出す。
- GPU 上の統計処理（Float64 の診断用累積を含む。T4 では遅いが動く）は、起動時の preflight（小さい配列で host 結果と照合）と各呼び出しで失敗を検出し、失敗した場合は同じ統計を host コピーで計算する（結果は index に記録）。
- 診断コードは clipping・renormalization・NaN 置換・tangent の rescale / reset・gradient clipping を一切しない。非有限は直さず、観測して止める。

## 判定規則（固定）
- **DIAG_LOCALIZED**: A が G2 の失敗を再現（step 1200、時刻の文字列が `16.409412384033203`）、B が最初の非有限を取得（`first_bad_step ≤ 1200`）、self-check（checksum 全 step と SHA）が一致、
  B が最初の bad の step / time / stage / field / component / index / 直前値 / 非有限値を保存し、失敗前の tangent の成長が（ある範囲で）保存されている。
- **DIAG_NOT_REPRODUCED**: A も B も horizon まで有限で、self-check が一致。重要な結果として保存し、自動で延長しない。
- **DIAG_INCOMPLETE**: 上のどちらでもない（例外、self-check の不一致、A が G2 の失敗を再現しない、A と B で有限性が食い違う）。DONE を書かず非 0 で終了する。
- exit code 0（kernel の `DONE`）は LOCALIZED / NOT_REPRODUCED のときだけ。

## 解析（実行前に凍結、1 回だけ実行）
host の terminal 検証（manifest の SHA、DONE/ERROR の排他、source・pin・入力 hash・runtime source hash・flag false・dryrun false）が PASS した出力に対して
`scripts/analyze_grad_g2_diag1.py` を**1 回**だけ実行する。bridge analyzer は呼ばない。結果を見て規則・閾値を変えて再実行しない。
- 失敗の identity（`first_bad_step / time / stage / field / component / index`、直前の有限 stage、最初の非有限 stage）は ledger から独立に再導出し kernel の `first_bad.json` と照合する。
- 成長（u の max|tangent|、`project2_bc` 後）: 失敗直前 100 steps の曲線（max、RMS、前 step 比、log10）。パターン（記述規則、閾値は固定）:
  `sudden_jump`（1 step で log10 が 1.0 decade を超えて上昇）、`roughly_exponential`（傾き > 0.01 decade/step かつ線形近似 R² ≥ 0.95）、
  `slow_monotonic`（非減少の割合 ≥ 0.9 かつ傾き > 0）、それ以外は `other`。
- **Case**（優先順 E > D > F > A > C > B。「tangent のみ」= 最初に非有限になった**要素**の primal が有限、tangent が非有限）:
  E = 最初の bad が force stage で、同じ step の state stage は全て有限。
  D = 幾何の静的監査に非有限がある、または最初の bad が measure stage の幾何 field（μ₀, μ₁, V, D, iD, 粗い L）。
  F = 最初に非有限になった要素の primal が非有限（primal が先に壊れた）。
  A = tangent のみが非有限で、パターンが `roughly_exponential` または `slow_monotonic`、かつ直前の log10(max|tangent u|) ≥ 30（Float32 の上限は約 38.5）。
  C = tangent のみが非有限で、最初の bad が Poisson solve stage（`project1_solve` / `project2_solve`）（A に該当しないとき）。
  B = tangent のみが非有限で、パターンが `sudden_jump`（A・C に該当しないとき）。それ以外は `unclassified`。
- **次の実験の機械的な提案**: A → Float64 Dual の precision discriminator が強く正当化される。B → 問題の stage / 演算の局所 diagnostic を先に。
  C → 許容誤差 / 反復数感度の新しい事前登録 diagnostic が候補。D → Candidate C の derivative semantics を先に調査。E → force の derivative path を局所的に diagnose。F → primal が先に壊れている（G2 の plain は有限だった）ので、該当 stage の primal 演算を局所的に調査。unclassified → 提案なし、ユーザーに報告。
  **提案は提案であり、実行は次のユーザー判断。**
- **仮説の分類（H1–H6、`supports / weakly_supports / refutes / unresolved` のみ）**。結果の後に追加する仮説は post-hoc と明記する:
  - H1 Float32 tangent の dynamic range overflow: Case A なら supports。tangent のみ非有限かつ直前 log10 ≥ 30 なら weakly_supports。直前 log10 < 20 なら refutes。他は unresolved。
  - H2 startup transient 中の有限だが不安定な tangent 動力学: パターンが roughly_exponential で step 100 から失敗前までに ≥ 3 decade 増えていれば supports。roughly_exponential / slow_monotonic で ≥ 1 decade なら weakly_supports。増加が 1 decade 未満なら refutes。他は unresolved。
  - H3 Candidate C / 近縮退 immersed-boundary 係数の derivative 増幅: Case D なら supports。最初の bad のセルが帯域内かつ tangent のみ非有限で幾何は有限なら weakly_supports。帯域外で幾何が有限なら refutes。他は unresolved。
  - H4 有限反復 Poisson の derivative 増幅: Case C なら supports。直前 20 steps の反復が 50% 以上 itmx に達し最初の bad が projection stage なら weakly_supports。直前 20 steps で一度も itmx に達しないなら refutes。他は unresolved。
  - H5 force の後処理だけが非有限（state の tangent は有限）: Case E なら supports。同じ step に state の非有限があれば refutes。他は unresolved。
  - H6 instrumentation 非依存の再現失敗 / 非決定性: self-check 不一致、A が 1200 を再現しない、A と B の有限性が食い違うなら supports。A が 1200 を再現し self-check が一致すれば refutes。他は unresolved。

## 禁止（今回やらないこと）
Float64 Dual / D1・D2・P1 / full-window retry / bridge 値の推定 / δ の選択 / GRAD-03 verdict / reverse の修復 / Poisson tolerance の変更 / Candidate C の変更 / precision の変更 / tangent clipping / 結果を見た後の閾値 / production backend の選択。

## retry 規則
転送・download の provider transient で、意味のある観測が 1 件も出ておらず、source・登録・kernel の同一性が不変なら retry 可。
**instrumentation / source の不具合**（診断コードの bug、例: GPU でのコンパイル失敗）は attempt を保存し、source を変えるなら同じ freeze を上書きせず**新しい identity で最大 1 回**直す。
科学的な結果（失敗の位置・DIAG_NOT_REPRODUCED を含む）は retry しない。

## 結果の意味（限定）
これは「G2 の D0 長時間 run がどこで非有限になったか」の観測であり、AD の誤りの証明でも、forward 勾配の可否の判定でもない。
結果が A–E のどれであっても、次の実験はユーザーの判断で決める（Float64 precision discriminator / offending stage の局所修復・diagnostic / Poisson derivative diagnostic / long-window forward bridge の断念）。推測で次に進まない。
