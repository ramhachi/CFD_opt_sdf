# PQ0.1 — nonlinear production path 統合修復 record（2026-09-22）

Status: PQ0.1 slice implemented and validated. Baseline `f9bb0d4`（採用 plan の commit）。

## 実装順（plan §16 の固定順）

| 順 | 作業 | 実装 | 検証 |
| --- | --- | --- | --- |
| 1 | nonlinear loop に real projected-volume value/gradient を接続 | `make_oracle_from_compiled` が `compiled.volume_constraint` を value/gradient とも projection 空間で追加。ID 衝突は fail-closed | `tests/test_nonlinear_acceptance.py`（volume 制約付き loop、衝突 test） |
| 2 | primal/adjoint callback 分離と accepted primal artifact 再利用 | `primal_evaluator(state)` / `adjoint_evaluator(state, primal_artifact)`。artifact は `rho`/transform/response hash に束縛し、不一致なら adjoint を拒否。adjoint は primal を再実行しない | artifact mismatch test（primal 呼出し 1 回のまま）、loop counts test |
| 3 | trial adjoint `not_applicable` / parent adjoint fail-closed | `TrialEvaluation.adjoint_status="not_applicable"`。受理判定から adjoint を除外。parent は `adjoint_converged is True` を必須（欠落は例外） | adjoint fail-closed test、accept_trial test 更新 |
| 4 | Path B centered FD bracket | `path_b_bracket.py`: `d_hat = d/‖d‖∞`、対称 bounds 検査（clip 禁止）、noise floor、`D_adj<0 かつ D_FD<0` の符号一致。bracket は controller 受理後に `pre_accept_gate` として実行し、不合格なら reject + move 半減 | bracket module 5 tests + loop-level 2 tests（pass / noise-floor 全拒否） |
| 5 | downforce-only + volume の reduced problem audit | 新 spec（maximize downforce のみ）＋体積 budget 宣言で production step を実行し `declared_equals_solved=true` | `docs/evidence/pq0_1_reduced_problem_audit_2026_09.json` |
| 6 | projection と solver beta の semantic name 一意化 | summary に `semantic_names` を追加（`rho_projection` = projection 出力・体積基準・再計算、`beta_solver` = artifact `rho_projected` = OpenFOAM beta、`brinkman_alpha` = beta_max×beta） | optimizer test |

## Reduced problem audit（実 artifact）

`docs/evidence/pq0_1_reduced_problem_audit_2026_09.json`:

- objective: `minimize -C_DF`（downforce 最大化のみ、drag は report-only）
- constraint: `g_V = V(rho_projection) - 0.029067262693466128 <= 0`（base で g = -0.01、feasible）
- `declared_equals_solved = true`、solved_set は objective 1 本 + volume 1 本。
- 旧 test の「downforce response を `volume_budget` と命名した偽制約」は廃止した。

## PQ0.1 exit gate の状態

| gate | 状態 |
| --- | --- |
| objective/constraints/volume が compiler の solved_set と一致 | pass（audit） |
| synthetic で volume infeasible proposal 拒否 + volume gradient centered FD | pass（loop test + compiler test） |
| trial は adjoint なし、parent は adjoint 欠落で停止 | pass |
| accepted primal artifact 再利用、重複 primal なし | pass（counts: `gradient_evaluations == 1 + accepted`、`value_evaluations == 1 + trials`） |
| bracket の sign match / mismatch / noise floor / 非対称 bounds | pass |
| checkpoint が problem/transform/oracle/bracket 変更を拒否 | pass（bracket_hash 含む 6 種 mutation） |
| projection と solver beta の lineage 区別 | pass（semantic_names） |
| downforce-only + volume fixture の declared==solved | pass（audit） |

## 次

- PQ0.2: 実 OpenFOAM oracle smoke（parent primal 1 + parent adjoint 1 + bracket ±1 + trial 1 + resume）。
  実装済み API はそのまま使える。trial 用の adjoint 無効テンプレートと、`adjoint_evaluator` の
  primal artifact 再利用（final time・hash 照合）が残作業。
- PQ2 の登録済み domain/boundary factor（V2 2 run）は独立に実行可能。
