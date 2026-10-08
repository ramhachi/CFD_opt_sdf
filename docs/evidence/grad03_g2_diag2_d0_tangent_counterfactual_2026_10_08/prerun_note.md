# G2-DIAG2: D0 遠方場 tangent モードの反事実（counterfactual）局所診断 — 実行前の登録（未登録の診断）

証拠区分: `gpu_d0_tangent_counterfactual_diagnostic_unregistered`。**診断のみ。** gradient の qualification ではない。bridge の値を出さない。δ を選ばない。GRAD-03 の verdict を出さない。
reverse には触らない。6 つの qualification flag は false のまま。Float64 は走らせない。D1/D2/P1 は走らせない。**介入は反事実の摂動であり、修正ではない。**
この note と `prerun_freeze.json` は T4 の最初の意味のある観測より前に固定する。G2 attempt 1・G2-DIAG1 の evidence namespace は immutable（DIAG1 の追補は DIAG1 側に別ファイルで追加済み）。

## 問い
G2-DIAG1: D0 の primal は定常のまま、tangent だけが遠方場の角の箱（`i<12, j<8, k≥48`、境界面から 3〜8 セル内側）で約 step 800 から 0.093 decade/step で指数成長し、step 1196 で Float32 を overflow した。
**この成長を作っているのは、どの数値設定・境界処理・演算か。** 候補: tangent の Poisson 解の未収束（H11）、Δt の tangent のフィードバック（H12）、境界・角の tangent 経路（H8）、exit 側（H7）、ghost 層（H13）。

## 開示（この note より前に見たもの）
- DIAG1 の結果と post-hoc 追補（Poisson は step 31 以降 1 反復、tangent の相対残差 2〜4 % / primal 約 1e-3、Δt の tangent は step 860 まで定常、箱への局在 99.97 %、onset の外挿 step 約 800）。
- CPU dry-run（小さい fork step と数 step）でコードパスを確認した。診断であり科学データではない。baseline の成長は dry-run では再現しない。
- 変種の閾値（0.05 / 0.01 / 0.5×）、fork step 780、各領域の範囲は、DIAG1 の観測を見たうえでの提案値であり、結果を見る前に固定する。

## 固定する科学状態（G2・DIAG1 と同一。変更は第 3 節の変種だけ）
Candidate C / canonical v17（phi SHA `e3966d87…`）/ flow_24 / D0 bytes（SHA `d0af58bd…`）/ Float32 / CuArray / Dual 幅 1 / WaterLily 既定の Poisson（`tol=1e-4`, `itmx=32`）/ CFL の時間刻み /
`remeasure=true` / ground・force semantics / 入力 hash。`build`・`load_raw`・`vp` と定数は G2 の verbatim コピー（テストで固定）。

## 設計（1 kernel、D0 のみ）
1. **S（straight）**: 通常の `sim_step!` を step 0 から `END = 980` まで再生し、毎 step の状態 checksum（u, p の xor と和、Δt の bit）を記録。step `FORK = 780`（実測 onset の外挿 800 より前）完了時の `u`, `p`, Δt ベクトルを host にコピーする。
2. **各変種**: 新しい simulation を構築し、fork 状態を書き戻し、step 781〜980 を `measure!` + `diag2_mom_step!`（DIAG1 の stage コピー + 変種用の Poisson 引数）で進める。probe は step ごとに記録し、反事実の変種のみ介入する。
   書き戻すのは `u`（ghost 層を含む）, `p`（= Poisson の x）, `Δt` ベクトルだけ。他の配列（`u⁰`, `f`, `σ`, Poisson の `r`/`ϵ`/粗い level）は毎 step 全面上書きされる（WaterLily 1.8.0 のソースで確認。`σ` の ghost 層は `conv_diff!` が scratch として毎 step 上書きし、書かれない位置は両 run とも 0）。**V0 が S と bit 一致することが gate**（一致しなければ DIAG2_INCOMPLETE）。
3. **変種**（固定。範囲は 1 始まり、配列は `u[152, 74, 56, 3]`）:

| ID | 内容 |
|---|---|
| V0_baseline | 介入なし |
| V1a/b/c | Poisson を強制的に 4 / 16 / 32 反復（`solver!(b; tol=0.0, itmx=n)`）。primal もわずかに変わる |
| V2_dt_tangent_frozen | Δt ベクトルの tangent を 0 に固定（値は保持） |
| V3_kill_corner_box | u の tangent を箱 `i∈1:12, j∈1:8, k∈49:56` で 0 にする |
| V4a/b/c | 8 セル幅のスラブ（`i∈1:8` / `j∈1:8` / `k∈49:56`）で u の tangent を 0 にする |
| V4d | V4a・V4b・V4c を同時に |
| V5_kill_ghost_layers | 外側 2 セルの層（各軸の両端）の u の tangent を 0 にする |
| V6_kill_exit_slab | x-max から 8 セル（`i∈145:152`）の u の tangent を 0 にする |

   tangent を殺す介入は、**fork 後の各 step の** `predict_bc`・`predict_exitbc`・`project1_bc`・`correct_bc`・`project2_bc` の各 stage の**直後**（metric の記録の後）に、`FD.Partials` のみを 0 にして値は保持する。NaN の置換・clipping・renormalization は行わない。
   介入コードは `variant != V0` かつ `step > FORK` のときだけ有効で、V0 の経路には介入の呼び出しがない（テストで固定）。
4. **観測（変種ごと、毎 step flush）**: 全体の max|tangent u|（`project2_bc` 後、介入前）と max|primal u|、primal / tangent の非有限数、
   各 u stage 後の角の箱の max|tangent u|（11 stage）、Poisson の反復数と RHS・残差の max（primal と tangent、`project1`・`project2`）、Δt の値と tangent、時刻、状態 checksum。
5. **成長率**: 区間 `[FORK+100, END] = [880, 980]`（101 点）で、(a) `log10(全体の max|tangent u|)`（`project2_bc` 後、その stage の介入の前）と (b) `log10(角の箱の max|tangent u|)`（`box_project2_bc`）の、それぞれの最小二乗の傾き（decade/step）。DIAG1 の baseline は 0.0975、post-hoc の箱の傾きは 0.093。
   **両方**を使うのは、全体の max が物体近傍の定常値（約 21）の下駄を履いており、遅くなっただけのモードが箱の外の指標では 0 に見えうるため（レビュー指摘）。

## 判定規則（固定）
- **DIAG2_LOCALIZED**: V0 が S と bit 一致、baseline の傾き `s0 ≥ 0.05`、全 12 変種が記録され例外なし、解析が 1 回実行される。
- **DIAG2_NOT_REPRODUCED**: V0 は bit 一致だが `s0 < 0.05`（成長が再現しない）。重要な結果として保存し、自動で延長しない。
- **DIAG2_INCOMPLETE**: V0 の不一致、変種の例外、欠落、実行時の想定外。DONE を書かず非 0 で終了する。
- **変種の分類**（全体の傾き `s`・箱の傾き `sb`、baseline の `s0`・`sb0`）: `suppresses` = 非有限なしで `s ≤ 0.01` **かつ** `sb ≤ 0.01`、`reduces` = `s ≤ 0.5·s0` かつ `sb ≤ 0.5·sb0`（suppresses を除く）、`no_effect` = それ以外、`diverged` = 区間内で非有限、`undetermined` = 点が足りない。
  V0 の gate は「S と bit 一致」に加え「V0 が 200 step 完走（非有限で止まらない）」と「S の最終 step の全体の max|tangent| が有限」。
- **仮説**（`supports / weakly_supports / refutes / unresolved`。解釈は結果の後に post-hoc と明記）:
  - H11 tangent の Poisson 解が primal 停止判定のため未収束 ← V1a/b/c
  - H12 Δt の tangent のフィードバック ← V2
  - H8 境界・角の tangent 経路 ← V3 と V4d（どの面かは V4a/b/c の suppresses で記録）
  - H7 exit 側 ← V6
  - H13 ghost 層の tangent の BC ← V5
  各仮説の status: 対応する変種のどれかが `suppresses` なら supports、なければどれかが `reduces` なら weakly_supports、全て `no_effect` なら refutes、それ以外は unresolved。
- 機械的な次の提案: H11 が supports / weakly_supports なら「primal と tangent の両方が収束するまで反復する停止規則」の事前登録。H12 なら Δt の tangent の扱いの調査。H8/H7/H13 なら境界の tangent 経路の局所診断（第 2 弾: `conv_diff!`・BDIM の内部分解）。
  どれも効かなければ第 2 弾の内部分解。**提案であり、実行は次のユーザー判断。**
- 限界（開示）: V3 と V4d は箱全体を殺すので箱の傾きは自明に小さく、判定は全体の傾きに依る。全体の max は物体近傍の下駄（約 21）より下の再成長を検出できない。再成長の有無は最終の全体の max（`final_glob_max_tangent_u`）を併記して読む。
- 注意: kill 系の変種は「その領域の tangent を毎 step 殺しても成長が他所で再発しないか」を測る。領域内の tangent が 0 になること自体は自明で、全体の max を指標にするのはそのためである。

## 解析（実行前に凍結、1 回だけ実行）
host の terminal 検証（manifest の SHA、DONE/ERROR の排他、source・pin・入力 hash・runtime source hash・flag false・dryrun false・登録した fork/end/slope 区間）が PASS した出力に対して `scripts/analyze_grad_g2_diag2.py` を **1 回**だけ実行する。
結果を見て規則・閾値を変えて再実行しない。bridge analyzer は呼ばない。

## 禁止（今回やらないこと）
Float64 Dual / D1・D2・P1 / full-window retry / bridge 値の推定 / δ の選択 / GRAD-03 verdict / reverse の修復 / Candidate C の変更 / production の修正 / flag の変更 / 結果を見た後の閾値 / production backend の選択。
`conv_diff!` の内部分解は今回の範囲に入れない（上の変種で絞れなかった場合の第 2 弾）。

## retry 規則
provider の一時障害で、意味のある観測が 1 件も出ておらず、source・登録・kernel の同一性が不変なら retry 可。
**instrumentation / source の不具合**（診断コードの bug、例: GPU でのコンパイル失敗、preflight の失敗）は attempt を保存し、source を変えるなら同じ freeze を上書きせず**新しい identity で最大 1 回**直す。
科学的な結果（NOT_REPRODUCED を含む）は retry しない。

## 結果の意味（限定）
反事実の変種は「成長が消えるか」を見る診断で、原因の証明でも修正でもない。ある変種で成長が消えても、forward 勾配が正しいことは主張しない。次の実験はユーザーの判断で決める。
