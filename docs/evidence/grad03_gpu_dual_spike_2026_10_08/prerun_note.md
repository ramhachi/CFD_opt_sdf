# G1: T4 上の Dual（forward AD）capability gate — 実行前の判定規則（未登録・診断）

証拠区分: `gpu_forward_ad_capability_spike_unregistered`。gradient の qualification ではない。6 つの qualification flag は false のまま。
reverse には触らない。この note は最初の T4 実行より前に作り、script・runner 以外の入力の SHA を `prerun_freeze.json` に固定する。

## 開示（この note より前に見たもの）
- CPU の forward AD spike（`docs/evidence/grad02_forward_ad_spike_2026_10_08/`）の結果。本 G1 の閾値は、その CPU 結果
  （primal 差 1e-5〜6e-5、FD との差 1e-3 級）を見たうえで置いている。
- 同じ G1 script を `G1_BACKEND=cpu`、Float32 Dual、1 ステップで CPU 上に走らせた dry-run（保存しない・判定に使わない）。完走し、
  primal 差 4e-7、FD との差 2e-3〜3e-3 だった。GPU 上の挙動はまだ何も見ていない。

## 問い
`WaterLily.Simulation(...; T=Dual{Tag,Float32,1}, mem=CuArray)` の `sim_step!` が、Candidate C 複合 body（`DeviceGridSDF` の `kernel_grid` 経由）を
T4 上で通り、phi の摂動方向（D0）への微分を返すか。

## 測るもの
- canonical v17 baseline phi と D0（Fortran 順 `<f4`、SHA は freeze に固定）、flow_24（150×72×54）、2 ステップ、`remeasure=false`、Poisson は WaterLily 既定（tol 1e-4、itmx 32）。
- 力は 2 種: `combined_*` = `total_force(sim)`（ground 込み、CPU spike と同じ定義、solver 単位）、`cand_*` = candidate のみの
  `-(pressure+viscous)`（登録 job と同じ定義。drag = 第 1 成分、downforce = −第 3 成分）。
- AD の primal と plain の primal の相対差、tangent（Dual の partial）、partial を含む場の有限性、VRAM、時間。
- 情報のみ（判定に使わない）: Float32 GPU での中心差分（ε = 1e-3、2e-3 m）との差、Float64 Dual の 1 ステップ tier。

## 判定規則（登録・事後に動かさない）
- **G1-FAIL**（blocker）: 完走しない（例外・コンパイル失敗・scalar 例外）、または tangent が NaN/Inf/零、または partial を含む場が非有限。
- **G1-PASS**: FAIL でなく、かつ (1) `primal_rel_diff_max ≤ 1e-3`、(2) Float32 GPU の `combined_fx`・`combined_fz` の tangent が
  CPU Float64 の AD tangent（`result_canonical.json`、tol 1e-4、2 ステップ: 23053.4、−4567.25）と相対差 ≤ 1e-1。
- **PARTIAL**: 上のいずれでもない。結果をそのままユーザーに提示する。
- 閾値は判断であり、根拠は「CPU の Float32/Float64 の primal 差 1e-5〜6e-5、CPU の FD 差 1e-3 級、GPU の reduction の丸めの違い」だけ。
- 規則は `scripts/evaluate_grad_dual_gpu_g1.py` に実装し、`tests/test_grad_dual_gpu_g1_rule.py` で検査する。

## 失敗時の扱い
コードの bug（`Float64(Dual)` 等の型の誤り）は修正して再実行してよい（規則は動かさない。試行は全て記録する）。コンパイル失敗が
Candidate C の body 内の Dual 演算（`copysign`・`muladd`・`sign`・`min`）に出た場合は、値ベースの薄い helper で回避する案を 1 回だけ試し、
それでも駄目なら blocker として報告して止まる。
