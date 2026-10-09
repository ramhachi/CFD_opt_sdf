# G2-DIAG5 独立レビュー（実行前）

2 本の read-only レビュー（別 agent、狭いスコープ。登録した S900 / S1000 は実行させていない）。指摘は freeze の前に反映し、tests と全 group の dry-run で確認した。反映後の第 2 ラウンドのレビューは行っていない（機械的な修正で、tests・dry-run で閉じている）。

## 1. 解析器・登録した規則・テスト・freeze builder
| 指摘 | 対応 |
|---|---|
| 実データなら E3 の primal 共有 gate が必ず落ちる（Python の `1e-06` と Julia の `1.0e-6` でキーが合わない。fixture が同じ書式なので検出できない） | 反映: キーを正規表現で parse して数値で照合。fixture に Julia 書式を使い、実際の dry-run 出力に対する検査テストを追加 |
| R2 の「flip に集中していない」判定が飽和（flip cell が box をほぼ覆い enrichment ≈ 1）。R1 の集中条件は到達不能。ε=1e-2 の非線形性で R2 になりうる | 反映: enrichment を分類から外し記述的に報告。R1 は「不一致と flip 率の Spearman 順位相関 ≥ 0.8（ε ≤ 1e-3）」に置換。R2 は 1e-5 ≤ ε ≤ 1e-3 の smooth な振幅だけで判定（無ければ判定不能） |
| AD の成長率の符号を無視（減衰も R3/R1 になる） | 反映: AD の成長率 ≥ +0.02 を要求。減衰のテスト追加 |
| E6 の ulp 指標が R1 の OR 条件を無効化 | 反映: 分類から外し報告のみ |
| R1 が baseline の不一致・surrogate の一致を要求しない | 反映: ε=1e-3 で baseline 不一致、surrogate は一致の定義を満たす、を要求 |
| 欠損 ε・空集合・NaN で fail-open（mid ε の欠損、E3 の完全性 gate なし、E6 の個数） | 反映: mid ε は 3 つ全て必須、E3・E3C の 40 行の完全性と有限性、E6 の n=16 と有限性の gate |
| source の固定が弱い（`src/*.jl`、HEAD、clean-tree） | 反映: `julia/CFDSDFWaterLily/src` の tree hash、source commit が HEAD の祖先、tracked file が clean |
| integrity 失敗でも分類を書く | 反映: 分類を書かない。`--check` を追加（何も書かず gate だけ） |
## 2. job・stage の code と lineage
| 指摘 | 対応 |
|---|---|
| 【高】有限差分側の plain Float32 simulation は Dual simulation と別の丸めの map（`@fastmath` の `quick`・`div`・`μddn`。step 100 で quick の 44%、1 step 後の u の 1.23M/1.89M 要素が違う） | 反映: 有限差分・audit・ghost closure・E6 を全て Dual 型 zero-tangent の simulation に変更。以後 dry-run で ghost closure は厳密一致、dt closure は厳密一致 |
| `quick_branch` の id が WaterLily の `median` の operand 選択と違う（同値処理。box の 8%）。id 4 は構造上到達不能 | 反映: `median_pick` を複製して id を決める。note に id 4 の不可達を明記 |
| driver が dry-run の環境変数を引き継ぐ。`ok` が `dryrun` を見ない | 反映: `DIAG5_*` を除去、`status.dryrun is False` と `k_steps == 40` を要求 |
| stored state の非有限、S900/S1000 で `CFL(u)` と保存 Δt の照合なし | 反映: 非有限は error、全 state の `dt_closure` を gate に追加（value 1e-6、tangent 1e-4） |
| 確認済み（問題なし）: `diag5_mom_step!` は `sim_step!` と statement 単位で一致し bit 同一、`conv_diff5!` は `conv_diff!` と bit 同一、`QuickTie` の値は元の `quick` と bit 一致で partials は登録どおり、状態の同定・摂動・実効方向・flip マスク・列定義 | — |
