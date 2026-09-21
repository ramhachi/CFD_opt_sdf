# PQ0.2 — 実 OpenFOAM oracle smoke record（2026-09-22）

Status: PQ0.2 executed; capability pass, improvement claim なし。Baseline `afefd50`。

## 実装

- `src/cfd_sdf/openfoam_oracle.py`: 実 solver 用 evaluator。
  - **parent**: full template 1 回（primal + adjoint 同時）。gradient は同じ artifact から
    `topOSens` を再構成し、`P.T` で canonical beta 空間へ写像。solver の再実行なし
    （`gradient_evaluations=0` が証拠）。
  - **trial / bracket**: adjoint solver を deactivate した `template_trial` で primal-only。
  - run は state hash で immutable にキャッシュし、同一 state の再評価は artifact を再利用。
  - 側副 provenance（npz + sidecar）を `src` 側へ移し、campaign runner と共有可能に。
- loop に `evaluate_parent` fast path を追加（parent 1 呼出しで values + gradients）。
- `tests/test_path_b_bracket.py` に境界セルの回帰 test を追加。

## 実測（`docs/evidence/pq0_2_openfoam_oracle_smoke_2026_09.json`）

| 項目 | 値 |
| --- | --- |
| base projected volume | 0.016250 |
| V_max（登録） | 0.021250 |
| counts | value 8 / bracket 2 / parent 1 / gradient 0 |
| accepted / rejected | 0 / 1（rollback） |
| resume | 第1反復 trace が完全一致、parent 評価が +1 |

trace の内訳: 内側反復で controller が 2 回受理（`feasible merit decrease`）したが、
bracket が `bracket_bounds_asymmetric_minus` で拒否。他の内側反復は `trust_ratio_low`。

## 判明した PQ3 前提条件

初期 canonical 設計は active セルの多くが `rho = 0`（流体）である。downforce を増やす方向は
それらを正に押すため、centered bracket の `rho - epsilon d_hat` が下限 0 を割り、**どんな
epsilon でも対称点が作れない**。plan の規則（clip 禁止）ではこの proposal は拒否が正しい。

したがって PQ3 は次のいずれかを事前登録する必要がある。

1. **strictly interior feasible seed**（active セルで 0 < rho < 1、例: 小さな solid seed を
   配置）を使い、bracket 可能な状態から開始する。
2. 境界セル専用の明示的規則（one-sided bracket または除外セル集合）を登録し、方向を
   変えないことを検証する。clip による暗黙処理は禁止のまま。

この発見は smoke の目的（長時間 campaign 前の実行契約検証）が機能したことを示す。

## 検証

- `compileall src tests scripts`、`pytest -q`（後続 commit で full suite）
- smoke は実 OpenFOAM（Docker, opencfd/openfoam-default:2512）で完走
