# GRAD-02 follow-up: forward-mode AD spike — 実行前の判定規則（CPU・未登録）

証拠区分: `cpu_forward_ad_capability_spike_unregistered`。gradient の qualification ではない。6 つの qualification flag は false のまま。
Kaggle・T4 は使わない。この note は最初の本実験の前に作り、script・note・入力の SHA を `prerun_freeze.json` に固定する。

## 開示（この note より前に見たもの）
harness のデバッグのため、toy64 を 1 ステップだけ scratch に実行した（保存しない・判定に使わない）。AD は完走し、tangent は有限で、
FD との差は 1e-6〜1e-2 の範囲だった。この結果を見たうえで以下の閾値を置いているので、**toy64 の判定は盲検ではない**。
canonical tier と 3 ステップの本実験は未実行。

## 問い
`WaterLily.Simulation(...; T=Dual)` の `sim_step!` を、Candidate C 複合 body（`NormalFloorWaterLilyBody` + `V16MovingGroundBody`、
`CandidateCWaterLilyBody`）を通して Dual 数で微分できるか。phi を `phi + t·d` と置き、`d/dt` の瞬時 force（Fx、Fz）の
Dual の partials が、同一の離散モデルの中心差分と一致するか。

## 比較の定義
- 損失: 数ステップ後の瞬時 `total_force(sim)` の [1]（Fx）と [3]（Fz）。FD-08 の窓平均ではない。oracle の ĝ とは比べない。
- FD: 同じ実数型で `(F(phi+εd) − F(phi−εd)) / 2ε`。摂動は保存型に丸める（oracle と同じ流儀）。
- 参照 ε（結果を見て選ばない）: toy64 と canonical は 1e-5 m、toy32 は 1e-2 m。他の ε は報告のみ。
- 一致の等級 = max(Fx の相対差, Fz の相対差)（参照 ε）: A ≤ 1e-4、B ≤ 1e-2、C ≤ 1e-1、D > 1e-1。
- Poisson 許容: 1e-4（itmx 32、WaterLily 既定）と 1e-10（itmx 1000）の 2 水準。1e-4 は反復打ち切りの O(tol) 差を見る情報用。
- AD の primal と通常 primal の相対差も報告する。

## 判定規則（登録）
- **GO-forward**: toy64 の tol=1e-10 が等級 B 以内、かつ AD の primal 相対差 ≤ 1e-10、かつ tangent が有限。
  さらに canonical tier が完走して tangent が有限で、tol=1e-10 が等級 C 以内。
- **NO-GO-forward**: AD が例外で止まる、または toy64 の tol=1e-10 が等級 D。
- **PARTIAL**: 上のいずれでもない。結果をそのままユーザーに提示する。
toy32（Float32）、tol=1e-4 の行、Enzyme forward（Tier 3）は情報用で、判定には使わない。判定規則は結果を見て変えない。

## 設定
- toy: 解析球（半径 0.3 m、21³ 格子 h=0.1 m）、非球対称な表面帯の方向 d（max|d|=1）、flow 32×24×24、L=20、ν=0.1、3 ステップ（`SPIKE_STEPS`）。
- canonical: 登録 baseline phi（Fortran 順 raw、SHA `e3966d87…`）と D0（canonical state から再生成した `<f4` Fortran raw）、
  flow 150×72×54、L=24、ν=0.3、2 ステップ。0.15 m の clearance gate は primal の phi±ε·d に対して別途検査する
  （Dual 値は GridSDF の位置引数 constructor で gate を迂回するため）。
- 環境: `julia --project=julia/CFDSDFWaterLily`（WaterLily 1.8.0、`JULIA_PKG_OFFLINE=true`、Manifest は変更しない）。
- 追跡する限界: kink（`floor`、`copysign`、`max(·,0.25)`）の一側微分、Poisson は反復を通した微分、Dual の JIT・メモリ増、
  GPU（CuArray）上の Dual は未確認（本番 oracle は T4）。
