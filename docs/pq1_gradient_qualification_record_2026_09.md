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
