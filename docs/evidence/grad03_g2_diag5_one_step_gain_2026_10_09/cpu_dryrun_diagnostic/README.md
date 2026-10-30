診断のみ（科学データではない）: 最終コードでの code-path の確認。`DIAG5_DRYRUN=1 DIAG5_K=3 DIAG5_ENSEMBLE=2`、登録外の step 100 の保存状態（`R1188_E0` だけは登録した状態そのもの）、CPU Float32、Dual 幅 1、`julia -t 1`。
- `R1188_E0`: E0（CPU の 1 step を保存した次 step と比較）。`ghost_closure` は ghost 0 変化（Dual 型の算術なら `BC!` は保存した ghost を厳密に再現する）。
- `S100_E1/E2/E3/E3C/E5AD/E5FD_1e-3/E6`: 各 group の出力形式。S100 の `dt_closure` は value・tangent とも厳密一致、`instrumented_step_bit_identical_to_sim_step` は true。
登録した S900 / S1000 の結果は、この dry-run からは得ていない。
