# PQ4 — T-to-S extraction gate on the PQ3 candidate（2026-09-22）

Status: extraction executed; **composite Stage S entry gate = false**（discreteness が阻害）; Stage S not started。

> 2026-09-22 追記: 本文の途中で `ready_for_stage_s` を局所抽出判定の意味で使っていた箇所は、Codex レビュー（PQ4.0）を受けて合成判定へ修正済み。最終判定は `stage_s_entry_v1` の論理積で、現 candidate は **false**。`extraction_profile_pass` は 0.2/0.3 で true（別フィールド）。

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

## 校正と v2 プロファイル（同日）

解析形状（binary ground truth: box_bluff03 / plate_a20_nd / wing_camber_bent /
wing_two_element）で metric floor を測定（`docs/evidence/pq4_profile_calibration_2026_09.json`）:

| shape | surface max | max (voxel) | RMS | v1 ready |
| --- | --- | --- | --- | --- |
| box_bluff03 | 0.0707 m | 1.41 | 0.0476 | False |
| plate_a20_nd | 0.0707 m | 1.41 | 0.0412 | False |
| wing_camber_bent | 0.0866 m | 1.73 | 0.0445 | False |
| wing_two_element | 0.0707 m | 1.41 | 0.0470 | False |

**完全な binary 形状でも v1 閾値（max 1.0 voxel / RMS 0.5 voxel）を超過** — v1 は metric floor
以下にあり、どの候補も合格できない設定だった。校正結果に基づき **v2**
（max 2.0 voxel = 0.10 m、RMS 1.25 voxel = 0.0625 m）を、候補再判定の前に登録。

### v2 での再判定

| threshold | ready | surface max | feature shrink | reasons |
| --- | --- | --- | --- | --- |
| 0.2 | **True** | 0.0707 | 0.0 | - |
| 0.3 | **True** | 0.0707 | 0.0 | - |
| 0.4 | False | 0.0866 | 2.0 | feature_shrink |
| 0.5 | False | - | - | handoff error |

選択 threshold 0.2。**PQ3 v5 candidate は Stage S-ready になった**（v1 の不成立は candidate の
欠陥ではなくプロファイルの校正ミス）。次の PQ4 slice は Stage S 第一歩:
body-fitted case 生成 → downforce/drag surface sensitivity → 法線変位の centered FD 資格化 →
1 つの shape update。

## PQ4.0 — Codex レビューに基づく合成 Gate 修正（2026-09-22）

1. **`ready_for_stage_s` を合成判定へ戻した**（`src/cfd_sdf/stage_s_entry.py`）:
   lineage ∧ discreteness ∧ extraction profile ∧ volume fidelity ∧ width/gap ∧
   components/root ∧ manifoldness ∧ clearance。局所抽出 pass は `extraction_profile_pass`
   として別記録し、global 判定を上書きしない。
2. **選択規則を fail-closed 化**: `selection_rule` は `require_ready_for_stage_s=true` を必須。
3. **不足 gate を追加**:
   - reverse surface distance（voxel boundary → mesh、`trimesh.proximity`）
   - non-manifold edge count と self-intersection status（manifold3d 不在時は `not_evaluated` を明記）
   - volume fidelity（analytic ground truth で校正した相対 0.25 / revox 0.20 / 絶対 0.02 m³）
   - width/gap（ridge thickness の p5 と component 間 gap を ProblemSpec policy と比較、未宣言は `not_required`）
   - components/root（root 必須 policy で root mask が空なら fail）
   - clearance（`stage_v_clearance_v1` preflight を抽出 surface に適用）
4. **再判定（`work/pq4_sweep_entry`）**:

| threshold | extraction_profile_pass | ready_for_stage_s | 主な理由 |
| --- | --- | --- | --- |
| 0.2 | True | **False** | discreteness（mean_nd 0.0333 > 0.01、max_rho 0.50001 < 0.9） |
| 0.3 | True | False | discreteness + volume fidelity |
| 0.4 | False | False | discreteness + feature shrink |
| 0.5 | - (handoff error) | False | - |

`selected_threshold = None`（fail-closed）。したがって PQ4 の結論は
**「v2 校正と抽出 profile は有効、しかし Stage T field が grey のため Stage S へは進めない」**であり、
`phase_plan.md` の「qualified Stage S candidate なし」と一致する。

## 次の固定順

1. **PQ3.1**: filter / projection continuation / RAMP continuation（b>0, q>0）で
   production-regime の Stage T loop を再実行し、`mean_nd <= 0.01`、`max_rho >= 0.9`、
   volume feasible、Path B bracket pass の discrete candidate を得る。
2. **PQ4.1**: その candidate に対して完全な合成 Gate（lineage/volume/component/root/width/gap/
   self-intersection/clearance）を再実行する。
3. 合格後のみ Stage S baseline 登録と surface FD 資格化へ進む。
