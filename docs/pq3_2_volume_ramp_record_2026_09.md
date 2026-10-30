# PQ3.2 — volume-ramp growth（2026-09-22）

Status: 失敗（projection が field を消した）。診断は PQ3.3 へ引き継いだ。

## 実行（登録 manifest `pq3_2_volume_ramp_manifest_2026_09.json`）

- 宣言最小寸法 0.30 m（filter radius 0.15 = 3 cells）、volume limit を chunk ごとに
  +0.004 → +0.030 へ ramp、b/q は 0/0 → 8/30 → 16/100。
- 結果 `docs/evidence/pq3_2_volume_ramp_2026_09.json`。

| chunk | b | q | acc/rej | objective | beta mean_nd | beta max | projected vol |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0-2 | 0 | 0 | 9/0 | -1.44 | 0.052 | 0.417 | 0.0168 |
| 3 | 8 | 30 | 3/0 | -0.083 | 0.0008 | 0.036 | 0.0045 |
| 4 | 16 | 100 | 3/0 | -0.017 | 0.0002 | 0.032 | 0.0028 |

## 診断

- 上限制のみの projected-gradient backend では design が budget を充填しない
  （beta_max 0.417 = design が 0.5 を超えない）。
- 3-cell filter では filtered field が eta=0.5 を超えず、b=8/16 の projection が
  ほぼ全 field を 0 にする（beta_max 0.036、projected volume 0.0028）。
- 対策は PQ3.3 の volume-target OC step（design の体積 target を bisection で充足）。
