# PQ1 — Stage T gradient oracle 判定記録（2026-09-21）

Status: PQ1 判定 = **Path B（bounded research exception）**。PQ0 合格済み（`345118d`）。

## 判定

`docs/evidence/pq1_fd_verdict_2026_09.json`（v2 manifest を先に登録:
`docs/evidence/pq1_fd_manifest_v2_2026_09.json`）:

| 方向 | 比（平均） | ε plateau 幅 | 5% gate |
| --- | --- | --- | --- |
| gradient_aligned | 1.2179 | 1.1e-4 | 不合格 |
| random_seed_11 | 1.3764 | 7.9e-4 | 不合格 |
| random_seed_2026 | 1.5678 | 2.6e-3 | 不合格 |

- 符号は全方向・全 ε で安定、plateau は 5% 以内（No-Go 条件ではない）。
- `mesh` gate は本 campaign で未測定のため `not_measured_gates` に記録（False のまま）。
- したがって production gradient とは呼ばず、PQ3 は **bounded research loop**（各提案方向を
  primal FD で bracket し、実 primal 再評価のみで受理、magnitude 補正なし）に限定する。

## 原因分離の実施結果

1. **objective/sign/binding audit**（`docs/evidence/pq1_objective_binding_audit_2026_09.json`）:
   - downforce objective は `porousDirectionalForce`, direction `(0 0 -1)`, Aref 0.64, UInf 1。
   - sensitivity field `topOSensdownforce`、response binding `downforce`、sign
     `dJ/drho = -d(downforce)/drho`、identity profile、final time は provenance に固定。
2. **`isConstraint true; target 0` 仮説の A/B**（`docs/evidence/pq1_constraint_flag_ab_2026_09.json`）:
   - 同一 base state・同一テンプレートで downforce 随伴のみ `isConstraint false`（target 削除）に
     変更して base を再実行。primal は同一（downforce 0.300720062967）。
   - analytic は **bit-identical**（全方向で差 0.0）→ 制約フラグ仮説は棄却。
3. 既に棄却済みの仮説（transfer、設計移動、regularisation、primal 残差）は再試行しない。

## 次の一因子（登録済み・未実行）

`docs/evidence/pq1_grid_stability_manifest_2026_09.json`:

1. **source grid refinement**（blockMesh 細分化、base run 1本）— 転送が analytic 比較から
   消えるため、比の移動は solver 離散化の効果として解釈できる。
2. **canonical grid refinement**（voxel 0.05→0.025、fixture 再生成）— 設計パラメータ化の効果。
   第一因子の判定後に登録。

## 現時点で言えること / 言えないこと

- 言える: この configuration の勾配は符号と誤差区間が安定で、bounded research loop の
  入力として使える。magnitude は 5% 以内で正しくない。
- 言えない: production gradient としての合格、grid 依存性、他 state/response、target physics。

## 追記 — source grid refinement の実行結果（同日）

登録済み第一因子を実行した（`docs/evidence/fd_campaign_p6_source_grid_refined_manifest_2026_09.json`,
結果 `docs/evidence/pq1_source_grid_refined_2026_09.json`）。source grid を
32x16x16 → 64x32x32（各軸 2 倍）に細分化し、canonical state・domain・template・方向・
epsilon を固定した。

| 方向 | 粗格子比 | 細格子比 | 細格子 plateau |
| --- | --- | --- | --- |
| gradient_aligned | 1.2179 | **1.1499** | 2.8e-3 |
| random_seed_11 | 1.3764 | **1.0749** | 1.18e-1（3e-5 のみ 0.999） |
| random_seed_2026 | 1.5678 | **1.1596** | 5.3e-2 |

- 全方向で比が 1 へ移動し、符号反転なし。aligned の plateau は締まった。
- seed_11 は最小 ε の FD 差が細格子の solver 残差床に近く、外れ値になっている。
- したがって判定は「partial grid movement」: 細格子を leading configuration とし、
  **Path A / No-Go のいずれでもない**。次は perturbation 残差を締めた plateau 再確立
  （または ε 範囲の拡大）を登録して実行する。

## 追記2 — 細格子＋タイト残差で plateau 再確立（同日）

登録済み manifest `fd_campaign_p6_source_grid_refined_tight_manifest_2026_09.json`
（ε ∈ {1e-4, 3e-4, 1e-3, 3e-3}、残差 5e-9）を実行。結果は
`docs/evidence/pq1_source_grid_refined_tight_2026_09.json`。

| 方向 | 比（平均） | plateau 幅（30×ε 範囲） |
| --- | --- | --- |
| gradient_aligned | 1.1504 | 4e-4 |
| random_seed_11 | 1.1134 | <1e-4 |
| random_seed_2026 | 1.1441 | 4.5e-3 |

- 前回の seed_11 最小 ε 外れ値は **残差床の効果**であり、比の不安定ではないと確定。
- 比はまだ 5% gate を超えるが、**細格子で grid-consistent・ε-stable・方向別区間
  （1.11–1.15）** となった。粗格子（1.22–1.57）からの移動は source grid 離散化の効果。
- 判定: **Path B bounded exception（細格子構成）**。magnitude 補正は行わず、PQ3 は
  提案方向ごとの primal FD bracket を必須とする。

## 実装メモ

runner が manifest の ε・方向を無視していたバグを修正（`_manifest_plan`）。
登録 manifest と実行条件の一致が fail-closed で保証されるようになった。
