# PQ4 — T-to-S extraction gate on the PQ3 candidate（2026-09-22）

Status: extraction executed; **candidate is not Stage S-ready**; Stage S not started。

## 実行

- candidate: PQ3 v5 最終（checkpoint `work/pq0_2_smoke/checkpoint.json`、rho sha `ad96e1dc...`、
  downforce 0.9951、volume 制約 feasible）。
- 登録済み manifest `docs/evidence/pq4_extraction_sweep_manifest_2026_09.json`
  （thresholds [0.2, 0.3, 0.4, 0.5]、rule `registered_range_first_that_passes`）。
- 結果 `docs/evidence/pq4_extraction_sweep_2026_09.json`。

| threshold | status | watertight | components | volume rel | ready_for_stage_s |
| --- | --- | --- | --- | --- | --- |
| 0.2 | ok | True | 1 | 0.112 | **False** |
| 0.3 | ok | True | 2 | 0.297 | False |
| 0.4 | ok | True | 2 | 0.590 | False |
| 0.5 | error | False | - | - | False |

## Gate 不成立の理由（machine-readable）

`qualification_reasons`:

- `density_field_not_sufficiently_discrete`（PQ3 v5 は identity transform b=0/q=0 の
  capability loop であり、grey/porous な field が残る）
- `quantitative_fidelity_limits_not_configured`
- `surface_distance_not_evaluated`
- `minimum_feature_survival_not_evaluated`
- `self_intersection_not_evaluated`
- `source_root_connectivity_not_available` / `revoxelized_root_connectivity_not_available`

## 判定と次の一手

- Stage S は開始しない（plan §9 の entry gate）。
- 実装側の次: handoff layer に quantitative fidelity limits（surface distance、feature survival、
  self-intersection、root connectivity）を実装し、`ready_for_stage_s` を数値で判定可能にする。
- 候補側の次: filter/projection/RAMP continuation（b>0, q>0）を使う production-regime の
  PQ3 run で discrete な終端を作る。identity-transform の capability loop はそのままでは
  Stage S 候補にならない。

## 定量 Gate の実装と再判定（同日）

`src/cfd_sdf/extraction_qualification.py` を追加し、
`handoff` artifact から **surface distance**（mesh 頂点と revoxelized material 境界の
EDT 距離、max/RMS）、**feature survival**（super-sampled DT の最小 feature 比較）、
**manifoldness**（watertight / winding / positive volume / duplicate faces）、
**root connectivity**（root が空なら not_applicable、未接続成分は fail）を数値判定する。
`sweep-density-extraction --qualify-extraction` で登録プロファイル v1
（max 0.05 m / RMS 0.025 m / shrink 1 voxel）を適用する。

実 candidate の再判定（`work/pq4_sweep_qualified`）:

| threshold | ready | 理由 | surface max / RMS | feature shrink |
| --- | --- | --- | --- | --- |
| 0.2 | False | surface distance 超過 | 0.0707 / 0.0480 | 0.0 |
| 0.3 | False | surface distance 超過 | 0.0707 / 0.0324 | 0.0 |
| 0.4 | False | surface distance + feature shrink | 0.0866 / 0.0523 | 2.0 |
| 0.5 | False | handoff error（not watertight） | - | - |

- **Stage S は開始しない**。定量的な理由（mesh が material から最大 1.4 voxel 外側へずれる）
  まで特定できた。
- 測定 metric は cell-centered EDT の頂点サンプルなので ~0.5 voxel（0.025 m）の量子化床を
  持つ。プロファイル v1 の閾値校正は、**解析形状（ground truth）での登録済み測定**を行って
  から変更する（結果を見た閾値変更は禁止）。
- 候補側: identity-transform capability loop の grey field ではなく、filter/projection/RAMP
  continuation を使う production-regime PQ3 で discrete な終端を作る必要がある。
