# PQ0 — production integration closure record (2026-09-21)

Status: PQ0 slice implemented and validated. Baseline `4bbd8e3`; this record
covers the I1–I12 dispositions of the adopted plan
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md).

## Dispositions

| ID | 処置 | 証拠 |
| --- | --- | --- |
| I1 | volume budget を compile-time の明示宣言にした（`VolumeBudget`）。宣言がなければ volume 制約は解かず、legacy switch が要求したら fail closed。ProblemSpec v2 への contract amendment は計画の停止条件どおり独立判断へ保留 | `compile_problem(volume_budget=...)`、`solved_set()`、`docs/evidence/pq0_declared_solved_audit_2026_09.json` |
| I2 | production solved set は compiler 出力のみ。legacy control は制約を追加できず、宣言済み制約を消せない（`enforce_volume=True` + 未宣言 → error、connectivity も同様）。artifact に全 solved term と ignored legacy controls を列挙 | `_spec_constraints`、`ignored_legacy_controls`、integration tests |
| I3 | volume は projection 出力空間で定義。`pullback_from_projected`（RAMP 微分なし）を追加し、value と gradient が同一関数に。`q=30` の中心差分一致と、RAMP 空間 pullback が一致しない mutation test | `tests/test_problem_spec_compiler.py::test_volume_gradient_matches_fd_in_projection_space_with_ramp` |
| I4 | oracle adapter が `rho_design -> state -> solver field (beta)` を明示し、solver-field 勾配を `pullback_from_beta` で design 空間へ戻す。`gradient_space` と `transform_hash` を結果に記録 | `make_oracle_from_compiled`、`tests/test_nonlinear_acceptance.py::test_oracle_maps_solver_field_gradients_through_the_transform` |
| I5 | production runner は明示的な `design_transform_declaration` を必須とし、derived arrays を `transform.forward` から生成。block filter は拒否、stored `rho_filtered` が宣言 transform と不一致なら fail closed。legacy path は `--allow-legacy-objective` で diagnostic と明示 | `design_transform_declaration.py`、optimizer spec-mode、CLI |
| I6 | `evaluate_values`（trial, primal のみ）と `evaluate_gradients`（parent, 受理ごとに1回）を分離。受理 trial の value payload を再利用し、受理後の重複 primal は 0 | loop の counts test（`gradient_evaluations == 1 + accepted`、`value_evaluations == 1 + trials`） |
| I7 | 「GCMMA-shaped」表現を merit/trust controller に訂正。MMA/GCMMA の名称は moving asymptotes backend 導入後（PQ6）に限定 | `nonlinear_acceptance.py` docstring |
| I8 | checkpoint が ProblemSpec sha、compiled problem hash、transform hash、backend id、oracle profile を束縛。5種の mutation で resume 拒否 | `tests/test_nonlinear_acceptance.py::test_checkpoint_resume_rejects_binding_mismatch` |
| I9 | extraction selection で数値 `0.0` を missing 扱いしない（`is None` 判定）。回帰 test 追加 | `tests/test_extraction_sweep.py` |
| I10 | candidate-specific uncertainty は登録 band を下回れない（`max(default, candidate)`、clamp 記録） | `tests/test_cross_fidelity_ranking.py::test_candidate_uncertainty_cannot_shrink_the_registered_band` |
| I11 | independent verification が 3 格子以上、response 別 numerical uncertainty、明示 `extraction_status` を必須化 | `tests/test_independent_verification.py` |
| I12 | robust three-field は `production_status() = {production_ready: False, PQ6 pending}` で production registry から除外 | `tests/test_robust_fields.py` |

## Real-artifact audit

`docs/evidence/pq0_declared_solved_audit_2026_09.json` — 実 P0 artifact
（injected contract、primal_base sensitivity、project.yaml）と identity transform
宣言で production step を実行し、`declared_equals_solved = true`。compiled された
objective は宣言どおり 2 本（minimize drag / maximize downforce）で、
`base_objective = 0.55495 = drag − downforce` を記録。legacy hard-coded
`-downforce` とは異なることを machine-readable に示した。

## 検証

- `.venv/bin/python -m compileall src tests scripts` → ok
- `.venv/bin/pytest -q` → **735 passed, 2 skipped**
- `git diff --check` → clean

## PQ0 の残ギャップ（PQ3 前に必要）

1. OpenFOAM 実装の oracle adapter（`evaluate_values` = primal-only、
   `evaluate_gradients` = adjoint のみ）は未接続。純 Python protocol と
   counts 契約は確定済み。
2. volume budget の ProblemSpec field 化（contract amendment）は保留。
3. legacy `run_fixed_grid_constrained_density_step`（spec なし）は diagnostic
   のまま。production CLI は spec + transform declaration を要求。

## 2026-09-22 post-implementation audit

上の `Status: PQ0 slice implemented` は component slice の記録であり、実 OpenFOAM
nonlinear path の閉鎖を意味しない。追加監査で次を確認した。

1. `stage_t_loop.make_oracle_from_compiled` は `compiled.volume_constraint` の
   value/gradient を `OracleResult` へ追加しない。
2. `evaluate_values` と `evaluate_gradients` は同じ `primitive_evaluator` を呼び、
   gradient call へ渡した primal values/artifact を再利用しない。
3. primal-only trial も `adjoint_converged` を要求し、payload 欠落時は `True` になる。
4. Path B に必要な proposal ごとの centered primal FD bracket は loop 未接続である。
5. real-artifact audit fixture は unconstrained `drag - downforce` であり、次の
   downforce-only + projected-volume 問題を監査していない。

従って PQ0 の表現は「component implementation complete」とし、PQ3 entry gate は
詳細計画の PQ0.1/PQ0.2 を通過した時点で初めて閉じる。
