# 独立レビュー（T4 前、2 役）

どちらも別 agent が read-only で実施。判定は両方 **PASS-WITH-FINDINGS**（blocker なし）。指摘は freeze 前に反映し、CPU dry-run（最終版の job）とテストで再確認した（修正後の再レビューは行っていない）。

## Review A — 非干渉・隔離
- fork 復元: `pois.x === flow.p`、`u`（ghost 層込み）・`p`・Δt ベクトルの書き戻しで足りる。`u⁰`・`f`・`V`・`μ₀`・`μ₁`・粗い level の `L/D/iD/x`・`r/ϵ` は毎 step 全面上書き。V0 と straight の bit 比較（u, p, Δt の bit、毎 step）は有効。
- V0 の経路: `measure!` + `diag2_mom_step!` は `sim_step!` と等価。`solver_step!(b, nothing) == solver!(b)`。介入・solver 引数に到達しない。`@fastmath` の位置は原本と同じ。
- 介入: `variant ≠ V0`・BC 直後 stage・tangent のみ（値は保持）。領域の範囲は note と配列の extent に一致。metric は kill の前に記録。変種間の共有状態なし（fresh sim、`append!` は isbits のコピー）。
- 強制 Poisson: `tol=0.0` では `r₂ < 0` が成立せず、ちょうど `itmx` 回反復する（`MultiLevelPoisson.jl:112-124`）。
- 指摘（反映）: preflight が `:box` だけ → 全 region kind（xmin/ymin/zmax/xmax/far/ghost）を device/host で照合。note に σ の ghost 層の一行を追加。

## Review B — 網羅性・durability・判定規則・GPU 経路
- durability: 毎 step flush、`diag_index.json`（RUNNING）を開始時に書き変種ごとに更新、変種の例外は変種単位で捕捉して他を続行、INCOMPLETE は非 0 終了・DONE なし。
- GPU 経路: view の reduction、view への broadcast 代入、device 間 `copyto!` は標準の GPUArrays 経路で scalar index なし。
- 指摘と対応:
  - **MEDIUM** 全体の max は物体近傍の下駄（約 21）を履くため、遅くなっただけのモードが「suppresses」に見える → 分類を全体の傾き**と**箱の傾き（`box_project2_bc`）の両方に拡張（Julia・Python・note・テスト）。V3/V4d は箱が自明なので全体に依ること、再成長を床の下では検出できないことを note に開示。
  - preflight に device 間 copy と全 region を追加。`size(sim.flow.u)` の登録値との照合を straight run に追加。CPU の preflight が恒等写像で空だった問題は `copy(h)` で解消。
  - Julia と Python の定数の不一致を検出する regex テストを追加。kernel の `classes` と analyzer の `classes_match_kernel` を報告。
  - V0 gate に「V0 が 200 step 完走」「straight の最終の全体の max が有限」を追加。
  - `diag_index.json` の書き込みを atomic に（tmp + `mv`）、analyzer の integrity を try で包み、stub 報告は非 0 終了。変種の CSV の handle は `try` 内で開く。JSON の文字列エスケープに `\r \t \e` を追加。`current_variant` を index に記録。
