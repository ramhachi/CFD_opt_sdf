# LOWDIM-02A（#49 Stage A）事前登録メモ — flow_32 での受理 step の符号確認

実行前に固定する。結果を見た後に state・閾値・判定を追加・変更しない。Stage B は別の事前登録（Stage A の結果を見た後）で行い、本メモは Stage B を許可しない。

## 目的と位置づけ
LOWDIM-01（#48）は 4 方向 basis の FD 提案方向に沿った +1.25 mm を flow_24 で受理した（downforce +4.05e-4 N、+0.12%）。Stage A は、その同一の phi を flow_32（200×96×72）で評価し、downforce の符号が保たれるかを調べる。
1 方向・1 step の cross-grid 符号確認であり、#26 GRID-01 の完了、格子収束、絶対 downforce、gradient の適格性、OPT-01（#30）のいずれでもない。flag 6 個 false、δ 未決、GRAD-03 verdict なし、FD-08 verdict は動かさない。reinitialization は使わない（#28 未適格）。

## state（1 kernel、T4、5 run）
1. `lowdim02a__baseline`: canonical baseline（phi SHA e3966d87…）。
2. `lowdim02a__baseline_repeat`: 同じ phi の再実行（決定性と flow_32 の noise floor の実測）。
3. `lowdim02a__prop__s1.25mm`: LOWDIM-01 の受理 state（提案方向 +1.25 mm）。
4. `lowdim02a__ctrl_reverse__s1.25mm`: reverse control（−1.25 mm）。
5. `lowdim02a__prop__s2.5mm`: +2.5 mm。**記述的のみ**で判定に使わない（flow_24 では −5.0e-5 N とほぼゼロで符号に情報がない）。
phi は `lowdim01` の inventory と同一（SHA を `inventory.json` に hash 束縛）。runner が numpy（`construct_state` と同じ演算順）で再生成し SHA を照合する。

## 実行と gate（fail closed）
- job は XFID job の複製で、case を flow_32 に絞る点とメッセージだけが違う（`scripts/waterlily_lowdim02_flow32_job.jl`、テストで行単位の差分を固定）。評価器・測定契約は W4 v17 と同一。
- 窓は [80,120] tU/L の endpoint-clipped time-weighted force。N への換算は host で flow_32 の格子間隔（0.025 m、ρU²dx² = 6.25e-4）。W4 v17 round-2 の flow_32 baseline CSV を同じ換算で再計算し、W4 の記録値（0.3612783598966907 N、drag 0.35002673442739357 N）と一致することをテストで確認済み。
- baseline の `flow_32.forces.csv` は W4 v17 round-2 retained の `flow_32.forces.csv`（SHA 032ef1cf…）と byte 同一でなければならない。不一致なら runner は以降の state を走らせず停止し、analyzer も INCOMPLETE。baseline repeat の byte 同一は記録のみ（gate にしない。差があれば noise floor として分解能に入る）。
- 各 state の phi・state・NPZ の SHA、margin、有限性、t_end ≥ 120、threads=1、host 再計算と Julia summary の相対 1e-9 一致、manifest・pin・GPU（Tesla T4）。

## 判定（actual primal のみ。予測は使わない）
分解能 res = max(3e-5 N, 10 × |baseline repeat − baseline|)（downforce と drag に別々に適用。3e-5 N は FD-08 の名目 σ0 の 10 倍で、flow_24 の値。flow_32 の実測 noise は repeat から入る）。
gain = D(+1.25) − D(baseline)、control = D(−1.25) − D(baseline)。
- `STAGE_A_PASS`: gain > res_df、drag(+1.25) − drag(baseline) ≤ res_dr、control < gain − res_df（reverse が分解能以上に悪い）、+1.25 mm の geometry gate（LOWDIM-01 で評価済み・全通過）。
- `STAGE_A_SIGN_FLIP`: gain < −res_df。flow_24 への過適合として停止（Stage B に進まない）。
- `STAGE_A_UNRESOLVED`: |gain| ≤ res_df。次はユーザー判断。
- `STAGE_A_CONSTRAINT_FAIL`: gain > res_df だが drag・control・gate のいずれかが満たされない。次はユーザー判断。
- `STAGE_A_INCOMPLETE`: integrity gate の失敗。何も結論しない。
記述的に併記: flow_32 と flow_24 の gain の比と符号一致、odd/even 部分、baseline の差、+2.5 mm、baseline repeat の byte 一致。

## 事前の既知事項（開示）
- flow_24 → flow_32 で baseline downforce は +8.9%（0.3316 → 0.3613 N）。格子感度が大きい。受理 gain は +0.12% しかないので、flow_32 の符号は予測できない（SIGN_FLIP も UNRESOLVED も十分ありうる）。
- flow_32 の W4 stationarity（半窓差）は downforce で相対 3.0e-5（約 1e-5 N）。分解能 3e-5 N との余裕は小さく、baseline repeat で実測する。
- 単一 run の flow_32 baseline が W4 の byte と一致しない場合（別 driver など）は停止し、amendment とユーザー承認なしに先へ進まない。
- 結果は 1 方向・1 step・1 窓の記述であり、PASS でも「flow_32 で最適化できる」は主張しない。

## 禁止
gradient・FD-08 verdict・flag・δ の変更、GRID-01 完了の主張、OPT-01 の主張、reinitialization、事後の state・閾値の追加、AD/tangent の使用、Stage A の結果前の Stage B 登録。

## kernel
`ramhachi888/cfd-opt-sdf-lowdim02a-a`（title=slug、private、T4、dataset なし、timeout 10800 s）。新 slug は identity-free check 済み（`identity_free_check.json`）。
