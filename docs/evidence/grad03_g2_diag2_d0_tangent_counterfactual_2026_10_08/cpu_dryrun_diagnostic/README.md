診断のみ（科学データではない）: `DIAG2_BACKEND=cpu` の code-path 確認。CPU Float32 の `Dual{Float32,1}`、D0、`DIAG2_FORK_STEP=6 DIAG2_STEPS=8`。
- `all_variants/`: 12 変種すべてが走り、V0 が straight 再生と bit 一致（gate）。成長は再現しない（onset の step 800 より前）ため verdict は NOT_REPRODUCED が正しい。
- `raise_variant/`: `DIAG2_ONLY=V0_baseline,V3_kill_corner_box DIAG2_RAISE_VARIANT=V3_kill_corner_box`。V3 で意図的に例外 → 例外を記録し、V0 は完走、verdict DIAG2_INCOMPLETE、終了コード 2、DONE なし。
- dry-run の `classes` は意味を持たない（fork が onset より前で成長がなく、傾きは雑音）。確認したのはコードパスと V0 の bit 一致、preflight（device/host 一致）、例外の記録だけ。
