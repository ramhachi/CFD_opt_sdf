# #47 STEP-01 事前登録: 有限 step の secant oracle（実行前に固定）

目的: 実際の optimizer の step（2.5〜12.5 mm = 0.1〜0.5 h、h = 25 mm）で、Candidate C の力の応答が (1) どの step 幅まで符号を保つか、(2) どこから secant が曲がるか、(3) 合成方向でも破綻しないか、を測り、#48 LOWDIM-01 の step 幅 contract の材料にする。
**これは gradient の qualification ではない**。FD-08 の verdict は変えない。6 flag false、δ 未決、GRAD-03 verdict なし、reverse 未着手、AD・tangent は使わない。DIAG5（R4）の判断は尊重する（診断条件の読み替え・DIAG6 なし）。

## 1. 状態（47 run、3 kernel、各 kernel に baseline を 1 本）
- baseline: `cal_baseline_01`（phi SHA `e3966d87…`）。方向 D0 / D1 / D2 / P1（FD-08 の方向、max-norm 1、SHA は `inputs_manifest.json` と `inventory.json`）。
- step: {2.5, 5, 7.5, 10, 12.5} mm（{0.1, 0.2, 0.3, 0.4, 0.5} h）× 符号 ±。`phi_child = float32(float64(phi) + (sign·ε_m)·float64(d))`、`ε_m = mm/1000`（`cfd_sdf.fd08_v2_campaign.construct_state` と同じ演算で、runner の numpy 実装が byte 一致することを host で検査済み）。
- kernel A = baseline + D0 + D1（21 state）、kernel B = baseline + D2 + P1（21 state）、kernel C = baseline + 合成 4 state（5 state）。計 47 run。
- **合成方向**: `d_combo = (d_a + d_b) / max|d_a + d_b|`（float64 の和と正規化 → `<f4`、max-norm 1）。組は `D0+P1`、`D1+D2`、±0.3h（7.5 mm）で 4 state。再正規化の因子 m は D0+P1 で 0.99999997（ほぼ 1: 台地が重ならない）、D1+D2 で 1.6047。
  したがって合成 state の成分は d_a、d_b それぞれ `7.5 mm / m`（D0+P1 で 7.5 mm、D1+D2 で 4.674 mm）。
  方向の raw（`inputs/combo_*.dir_f4_fortran.raw`）は git に固定。geometry gate（clearance ≥ 0.15 m、変化 node 数、float32 の実効変化）を 4 state にも適用済み（最小 margin 0.3375 m、変化 node 4717–4718、実現した最大変位 / 要求 = 1 ± 5e-8）。
- 実行: FD-08 の per-state Julia job（`scripts/waterlily_xfid_candidate_c_job.jl`）を**そのまま**使い（同じ bit）、runner が numpy で phi を生成して inventory の SHA を検証してから job を呼ぶ。dataset は使わない。FD-08 の記録は再利用せず、run ID は disjoint（`step01__…`）。

## 2. 応答と主量
- 応答 R: [80,120] tU/L の endpoint-clipped trapezoid の力の平均（drag = +Fx、downforce = −Fz、N、1/900 N/solver-force）。host の再計算は `scripts/fd08_v2_campaign_io.py::recompute_force_n`。R(0) は同じ kernel の baseline。
- **主量**は centered secant: `g_sec(s) = [R(+s) − R(−s)] / (2s)`（N/m）。非対称性・非線形性の指標: `η_even(s) = |R(+s) + R(−s) − 2R(0)| / |R(+s) − R(−s)|`。一方向の `(R(s) − R0)/s` は保存するが主判定に使わない（odd と even が混ざる）。
- 「分解された」: `|ΔR| > 10σ0`（σ0 = 3e-6 N、FD-08 の nominal T2。測定した noise ではない）。分解されない step は符号判定から外し、明示する。

## 3. 報告する量（各 direction × response。判定ではなく記述）
1. **符号の安定**: 分解された step で `g_sec` が同符号か、FD-08 の ĝ と同符号か、最初に符号が反転する step、符号が保たれる最大の step（`sign_stable_through_mm` = 最初の符号反転の手前の、分解された最後の step。分解された step が無ければ null）。
2. **secant の曲がり（secant drift）**: `g_sec(s) / g_sec(2.5 mm) − 1` が ±30% / ±50% を超える最小の step と、その手前の最後の step。η_even の step 依存。
3. **FD-08 との記述的な比較**: `g_sec / ĝ`、`(g_sec − ĝ) / SE`（キー名 `diff_over_nominal_se`。SE は nominal で統計的な信頼区間ではなく、z 値ではない）、**30% agreement radius / 50% agreement radius**（`|g_sec/ĝ − 1| ≤ 0.3 / 0.5` が最小 step から連続して保たれる最大の step）。
   ĝ・SE は `formal_criteria.json` の `calibration_binding.fits["<dir>|<resp>"]`（`g_n_per_m`、`se_g_n_per_m`）。**agreement radius は「その step が正しい」という意味ではない**: ĝ は ε→0 の真の微分ではなく Model A の局所傾きで、校正範囲（0.5–5 mm）の外（5 mm 超）は外挿。
4. **合成の加法性**: `ΔR(d_combo, ±7.5 mm)` と `ΔR(d_a, ±7.5/m mm) + ΔR(d_b, ±7.5/m mm)` の差。単一方向の ΔR(s) は 10 点（±5 step）と原点から PCHIP と線形の 2 通りで補間し、差を予測の不確かさとして併記。崩れ = `(ΔR_combo − 予測) / |ΔR_combo|`。予測の不確かさ = 2 成分の |PCHIP − 線形| の和。崩れが「その不確かさと測定の分解能（10σ0）の両方を超える」ときだけ `defect_exceeds_interpolation_spread_and_resolution` を立てる。
5. #48 へ渡す要約（`contract_inputs_for_lowdim`）: 各 series の `sign_stable_through_mm`、drift radius、agreement radius、合成の最悪の加法性の崩れ、全 series が 12.5 mm まで符号一定か。

## 4. gate（全て必要。fail-closed）
- 各 kernel: DONE か ERROR の一方だけ、manifest の SHA、source commit と全 pin と方向ファイルが kernel 上で検証されている、T4、plan と完了 state の一致、各 state の summary（phi/state/NPZ の SHA、margin、有限、`t_end_reached ≥ 120`、`julia_threads = 1`）、host の力の再計算と Julia の summary が相対 1e-9 で一致。
- **baseline**: 各 kernel の baseline の `flow_24.forces.csv` が FD-08 の `baseline_v17`（SHA `39370386…`、R6 と formal で byte 同一）と byte 同一。runner は不一致なら以降の perturbed state を走らせずに停止し、analyzer も INCOMPLETE（baseline の drag 0.3239039699743226 N、downforce 0.3316344583180616 N と相対 1e-12 でも照合）。
- 凍結したものの照合: analyzer、`step01_contract.py`、`step01_states.py`、`fd08_v2_campaign_io.py`、`formal_criteria.json`、inventory（正規 JSON）の SHA、凍結した 8 本の FD-08 の ĝ・SE。manifest は index・identity・nvidia-smi と全 state の 3 ファイルを列挙していること、pins と方向ファイルが空でないこと。
- agreement radius と drift radius は分解されない step も使って計算する（`unresolved_indices` を併記）。verdict は `STEP01_RECORDED` か `STEP01_INCOMPLETE`（INCOMPLETE のときは series を書かない）。

## 5. 実行環境と手順
FD-08 の runner との意図的な差: `CUDA_DEVICE_ORDER=PCI_BUS_ID` を設定する（nvidia-smi の index 0 の UUID と job が使う device を一致させるため。DIAG4 と同じ）。runtime smoke（`w0b_t4_smoke.jl`）と GPU 2 枚の確認は省く（版は各 state の summary に残り、baseline の byte 一致がより強い検査になる）。runner の SHA、python / numpy の版、platform を `run_identity.json` に記録する。
T4（Julia 1.12.6、WaterLily 1.8.0、Float32、`JULIA_NUM_THREADS=1`、FD-08 formal と同じ runtime）。A と B を並列に、baseline が byte 同一であることを確認してから C。1 state ≈ 110 s の solver + 起動。A/B は各 ≈ 1.2 h、C は ≈ 0.4 h。
独立レビュー 2 本（入力・runner の lineage／analyzer・定義・文言）を実行前に行い、freeze 後に実行、host で terminal verification → analyzer を、まず `--check`（gate だけ、何も書かない）で確認してから 1 回だけ（`open("x")`。INCOMPLETE でも one-shot を消費する）→ 記録。

## 6. 言い方の規則
agreement radius・drift radius・加法性の崩れは**記述的な量**で、「頑健な step」「正しい step」「qualified」とは呼ばない。ĝ との比較は FD-08 の校正範囲外の外挿を含む。合成方向の加法性は単一方向の補間に依存し、その不確かさを併記する。
gradient・FD-08 verdict・flag・δ・GRAD-03 は触らない。結果を見た後の step・閾値・方向の追加はしない。

## 7. 事前の確認の開示
- solver なしの geometry の確認（44 perturbed state）: clearance margin ≥ 0.3375 m（gate は 0.15 m）、変化 node 数 4717–4718、実現した最大変位 / 要求 = 1 ± 5e-8。
- FD-08 の baseline の force CSV は R6 と formal で byte 同一（SHA `39370386…`）。これを決定性の根拠とし、baseline gate の参照にした（記録の再利用ではなく byte 照合のみ）。
- DIAG5 の観測（有限差分の応答が ε によらず一定）が、この oracle の動機の一つ。STEP-01 の結果は DIAG5 の分類を変えない。
