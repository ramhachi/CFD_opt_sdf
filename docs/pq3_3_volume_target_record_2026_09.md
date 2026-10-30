# PQ3.3 — volume-target continuation（2026-09-22）

Status: solver field の離散性 Gate は pass、抽出の複合 Gate は **false**。Stage S には進まない。

## 実行（登録 manifest `pq3_3_volume_target_manifest_2026_09.json`）

| chunk | b | q | target | acc/rej | objective | beta mean_nd | beta max | projected vol |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0.03 | 3/0 | -2.108 | 0.0627 | 0.504 | 0.02080 |
| 1 | 0 | 0 | 0.06 | 3/0 | -2.476 | 0.0703 | 0.612 | 0.02446 |
| 2 | 0 | 0 | 0.10 | 3/0 | **-2.727** | 0.0749 | 0.707 | 0.02745 |
| 3 | 8 | 30 | 0.10 | 2/1 | -0.362 | 0.0055 | 0.574 | 0.01469 |
| 4 | 16 | 100 | 0.10 | 0/3 | -0.190 | 0.0039 | 0.944 | 0.01302 |

Hard gates: beta mean_nd **0.0039 ≤ 0.01** ✓、max_rho **0.944 ≥ 0.9** ✓、volume feasible ✓
→ `discrete_candidate = true`。

## 複合 Gate（materialize 後 `work/pq3_3_candidate`）

| threshold | local pass | global ready | surface max | volume rel | feature shrink |
| --- | --- | --- | --- | --- | --- |
| 0.4 | False | False | 0.212 m | 66% | 2.2 voxel |
| 0.5 | False | False | (empty revoxelization) | 100% | - |
| 0.6 | - | False | - | - | - |

`selected_threshold = None` → **Stage S baseline 登録なし**。

## 診断

1. volume-target OC step は b=0 で budget を充填し、objective -2.73（downforce 2.73）に到達。
2. b=8/16 の sharpening で projected volume が 0.0275 → 0.0130 へ崩壊し、objective も -0.19 へ後退。
   原因: (a) sharpened projection の下での再最適化反復が不足、(b) volume target が design field に
   対して課され、抽出対象の projected field を制御していない。
3. 終端は離散（mean_nd 0.0039, max 0.944）だが material が疎で、contour が橋渡しし抽出不能。

## 次の登録（PQ3.3b）

- 各 projection level（b=8, b=16）で十分な反復（目安 10+）を回し、projected volume と objective が
  安定してから次の b へ進む。
- volume target を **projected field** に対して課す。
- 同じ hard gates / 複合 Gate で再判定。b=0 growth stage は有効なので維持。
