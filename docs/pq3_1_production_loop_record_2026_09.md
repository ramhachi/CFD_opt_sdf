# PQ3.1 — production-regime continuation loop（2026-09-22）

Status: 離散性 Gate は **solver field で達成**、抽出 Gate は **不成立**。複合 Gate は `ready_for_stage_s=false`。

## 実行

- v1 manifest（3 stages、2-3 iters/stage）: 7 accepted だが design mean_nd 0.033、max_rho 0.53。
- v2 manifest（5/12/12 iters、move 0.05/0.03/0.01）: 29 iterations、16 accepted。
- 生成物 `docs/evidence/pq3_1_production_loop_2026_09.json` /
  `docs/evidence/pq3_1_production_loop_v2_2026_09.json`。

## 結果（v2）

| stage | accepted/rejected | design mean_nd | design max_rho | projected volume |
| --- | --- | --- | --- | --- |
| stage1 grow (b=0) | 5/0 | 0.0336 | 0.501 | 0.01652 |
| stage2 sharpen (b=8) | 11/2 | 0.0326 | **1.000** | 0.01833 |
| stage3 binarize (b=16) | **0/12** | 0.0326 | 1.000 | 0.01840 |

- **solver field (beta)**: mean_nd **0.00874 ≤ 0.01** ✓、max_rho **0.9934 ≥ 0.9** ✓。
- projection: mean_nd 0.00834、max 0.99993 ✓。
- しかし projected volume は 0.018402 で登録上限 0.018325 を **7.7e-5 超過**し、
  stage3 では全 proposal が拒否された。

## 抽出 Gate（materialize 後、`work/pq3_1_candidate`）

| threshold | surface max | reverse max | volume rel | feature shrink | local pass |
| --- | --- | --- | --- | --- | --- |
| 0.4 | 0.260 m | 0.033 m | 55% | 1.6 voxel | False |
| 0.5 | 0.658 m | 0.017 m | 86% | 1.5 voxel | False |
| 0.6 | - | - | - | - | empty |

片方向距離だけが大きく、逆方向は小さい = **contour が疎な material を橋渡しして
大きな空隙を囲んでいる**。離散性は満たすが幾何として抽出不能。

## 診断

1. binarization は projection が担うため **design field は grey のまま**（mean_nd 0.0325）。
   solver field・projection・beta は discrete。
2. volume budget は b=0 seed 基準の固定上限制だったため、projection が mass を濃縮しても
   追加成長のインセンティブがなく、上限に張り付いて stage3 を全拒否にした。
3. filter radius 0.075 m = 1.5 cells は最小寸法として小さく、抽出可能な feature を保てない。

## 次の登録（PQ3.2）

- **volume-ramp growth schedule**（段階的に volume target を上げる）
- 宣言最小寸法を ≥0.15 m（filter radius ≥0.15 = 3 cells）へ
- volume feasibility tolerance を実行前に登録
- 再実行後に複合 Gate（`stage_s_entry_v1`）を再判定

Stage S baseline 登録、shape update、PQ5 への引き継ぎは行っていない。
