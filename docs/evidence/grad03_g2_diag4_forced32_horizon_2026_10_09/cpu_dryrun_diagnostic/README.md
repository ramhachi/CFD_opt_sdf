診断のみ（科学データではない）: `DIAG4_BACKEND=cpu` の code-path 確認。CPU Float32 の `Dual{Float32,1}`、D0、`DIAG4_FORK_STEP=6 DIAG4_END_STEP=14`（成長は再現しない）。
- `gates_pass/`: 参照 CSV（別の dry-run の B0 と B32fork の checksum）を `DIAG4_REF_STRAIGHT` / `DIAG4_REF_F32` に与え、B0 の 14 step と B32fork の 8 step が参照と全 bit 一致 → DIAG4_RECORDED。clone の bit 一致、3 つの simulation の独立性（`Base.mightalias`）も確認。fork と fresh は、元の solver も最初の数 step は 32 反復するため fork が早い step では一致する。
- `gate_failure/`: 参照の F32 の step 9 の checksum を 1 だけ書き換えた → step 9 で「B32fork differs from the DIAG3 F32 arm」と止まり、DIAG4_INCOMPLETE（終了コード 2、DONE なし）。それまでの履歴は残る。
- `exception/`: `DIAG4_NO_REF=1 DIAG4_RAISE_STEP=9`。step 9 で意図的な例外 → DIAG4_INCOMPLETE、履歴は step 8 まで残る。

注: 3 ケースとも、独立レビュー（lineage）の指摘（clone を u・p・Δt の bit 比較でも検証、B0 の first_nonfinite を上書きしない、flow 配列の extent の assertion）を job に反映した後の版で実行し直した結果。
