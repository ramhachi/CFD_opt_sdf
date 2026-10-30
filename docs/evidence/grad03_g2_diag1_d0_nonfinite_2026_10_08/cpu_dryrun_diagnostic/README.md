診断のみ（科学データではない）: `DIAG1_BACKEND=cpu` の code-path 確認。CPU Float32 の `Dual{Float32,1}`、D0、数 steps。
- `normal/`: reference と instrumented を各 12 steps（`DIAG1_HORIZON_STEPS=12`）。両 run の checksum・SHA が全て一致（非干渉）。
- `inject_tangent_inf/`: `DIAG1_SKIP_REFERENCE=1 DIAG1_INJECT=4:project1_solve:x:tangent_inf`。step 4 の `project1_solve` の `x` に Inf の tangent を注入 → first_bad が class B（primal 有限、tangent 非有限）として記録される。注入は CPU 専用で、cuda では起動時に error。
- `raise_exception/`: `DIAG1_SKIP_REFERENCE=1 DIAG1_RAISE_STEP=4`。step 4 で意図的に例外 → step 1–3 の ledger・force・checksum が残り、verdict DIAG_INCOMPLETE、終了コード 2。
大きな raw snapshot（`snapshots/`）は含めない（`snapshot_index.json` に SHA）。
