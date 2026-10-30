診断のみ（科学データではない）: `DIAG3_BACKEND=cpu` の code-path 確認。CPU Float32 の `Dual{Float32,1}`、D0、`DIAG3_FORK_STEP=6 DIAG3_STEPS=8`（fork が onset より前なので成長は再現せず、verdict は DIAG3_NOT_REPRODUCED が正しい）。classes は意味を持たない。
- `all_arms/`: 24 arm すべてが走る。tangent-only の arm（A0, A1）は primal の値が plain 再生と全 step で bit 一致。Dual 停止・強制 32 反復の arm は primal が変わる（一致しない）。smoke（production の経路）と drift（基準 step の u・p・力）も記録。
- `stage_b/`: `DIAG3_ONLY=A0_baseline,A1_tau_1e-5 DIAG3_FORCE_SELECT=A1_tau_1e-5 DIAG3_STAGE_B_STEPS=12`。Stage B（新しい D0 を step 0 から）が 12 step 走る経路の確認。
- `raise_arm/`: `DIAG3_RAISE_ARM=A1_n02`。arm の例外 → 例外を記録し他は続行、verdict DIAG3_INCONCLUSIVE、終了コード 2、DONE なし。
