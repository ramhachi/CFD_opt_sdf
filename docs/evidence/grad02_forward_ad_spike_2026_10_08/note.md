# GRAD-02 follow-up: forward-mode AD spike の結果（CPU・未登録）

証拠区分: `cpu_forward_ad_capability_spike_unregistered`。gradient の qualification ではない。6 つの qualification flag は false のまま。
判定規則は `prerun_note.md`（実行前に固定、`prerun_freeze.json`）。toy64 は 1 ステップの smoke を固定前に見ており、盲検ではない（開示済み）。

## 事前登録した判定: **PARTIAL**
| 項目 | 規則 | 結果 |
|---|---|---|
| toy64、tol=1e-10、参照 ε=1e-5 の一致等級 | B 以内（≤1e-2） | **C**（Fx 8.6e-3、Fz 5.7e-2）→ 未達 |
| AD の primal と通常 primal の相対差 | ≤1e-10 | 7.6e-14（達成） |
| tangent が有限 | 必須 | 達成（全 run） |
| canonical（v17、D0、flow 150×72×54、2 ステップ）tol=1e-10 | 完走・有限・C 以内 | 完走・有限・**A**（Fx 7.6e-6、Fz 1.1e-5） |
→ GO-forward の条件のうち toy の等級だけが未達なので PARTIAL。規則も判定も事後に動かさない。

## 主な数値（瞬時 force の d/dt、N／solver 単位。窓平均ではない）
- toy64（3 ステップ、tol 1e-10）: AD dFx = 58.7479、dFz = −2.0102。FD(ε=1e-5) は 58.2498、−2.1323。
- canonical（2 ステップ、tol 1e-10）: AD dFx = 19352.1、dFz = −6397.6。FD(ε=1e-5) は 19351.9、−6397.7。
  tol=1e-4（WaterLily 既定）では dFx 23053.4、dFz −4567.3 で等級 B（反復打ち切りの O(tol) 差）。tol を変えると tangent の値自体が変わる。
- 0.15 m の clearance gate は phi±ε·d で 0.34990 m（通過）。
- 計算量: canonical の AD は JIT 込みで 15 秒（tol 1e-4）、166 秒（tol 1e-10）。全 run で約 14 分（2 水準 × primal+AD+FD）。

## 事後の診断（未登録・判定に使わない。`result_toy64sweep_posthoc.json`）
toy64 の AD と FD の不一致の原因を切り分けるため、ε を 1e-7〜1e-2 に振った。
- ε ≤ 1e-6 では FD が AD に 2e-9（Fx）〜1.4e-7（Fz）で一致する。ε ≥ 1e-5 で 1e-2 級の差に跳ぶ。
  登録した参照 ε=1e-5 は、この toy では FD 自体が滑らかでない域に入っていた（ε の設計の誤り）。
  AD は ε→0 の点別の微分と一致している、というのがこの診断の読み。
- 当初の仮説「非平滑さの尺度は Candidate C の遷移幅 δ=1.1444e-4 solver 単位（= 1.1e-5 m）」は**誤り**だった
  （独立レビューで棄却）。toy では Candidate C の blend はほぼ不活性（μ₀ の差は最大 1.1e-16）で、blend を外しても
  δ を 100 倍にしても AD・FD の数値は変わらない。不一致はステップ数とともに増え（ε=1e-5 で 1 ステップ 1e-6、3 ステップ 5.7e-2）、
  Poisson の tol や normal floor には依存しない。CFL の Δt（`max` を含む）を固定すると Fx の不一致が 8.6e-3 から 1e-6 に下がるため、
  時間刻みの選択（`max` の kink）が主因の候補（レビューの実験で、これ以上は切り分けていない）。
  **toy は Candidate C の blend を通らないので、blend を通した AD の検証は canonical tier だけ。**
- FD-08 と ε の比（h_SDF に対する 0.02〜0.2）を合わせた梯子（toy の h=0.1 m で 2〜20 mm、6 点、Model A の最小二乗。FD-08 自体は 0.5〜5 mm）の傾きは、
  Fx で AD の 2.8% 以内（残差 rms 0.0098、立方係数 c=−1.1e4）。Fz は信号が 2e-3 級で、傾きが AD と 106% ずれる（雑音支配という解釈は未検証）。
  この 1 例は、FD-08 流の梯子との一般的な一致の根拠にはならない。

## Float32（toy32、情報用）
AD の primal は通常 primal と 1.8e-5〜6.5e-5 で一致（Float64 の 1e-14 より粗い）。FD は Float32 の丸めで Fz が不安定。
oracle は Float32/T4 なので、点別微分を FD で検算できるのは Float64 の小さい ε に限られる。

## Enzyme reverse の再試行（情報用・**結論なし**）
`mom_step!` を concrete 型の関数経由で呼ぶ仮説（abstract 型の `Simulation` フィールドの動的 dispatch が原因）を試した
（`enzyme_concrete_step_reverse_probe.jl/.log`、WaterLily 1.6.1 = PR #285 環境）。同じ `MixedDuplicated(::Flow, ::Flow)` の MethodError で止まったが、
スタックの失敗箇所が `mom_step!` から `total_force` → `pressure_force`（`Metrics.jl:101`、probe が `Simulation` 経由の動的呼び出しのまま残した箇所）に
移っている。つまりステップ部分は通り、仮説は部分的に正しい可能性がある。**否定も肯定もできない。**
次の試行は `pressure_force` / `viscous_force` も concrete 化すること。

## 読み方
- forward-mode AD は、短時間の Candidate C `sim_step!` を v17 canonical state でも通せる（CPU）。点別の微分として整合する。
- GRAD-03 への含意: AD は点別の微分、FD-08 の ĝ は ε 0.5〜5 mm の回帰傾き（メソスケール）。両者の差（応答の非平滑さ）は
  この spike では定量していない。δ の選択肢（`46_fd08_v2_grad03_delta_options_2026_10_08.md`）はこの差を含めて決める必要がある。
- 未確認のリスク: 窓平均（約 8,700 ステップ）は CPU で非現実的で、oracle の設定には GPU（CuArray）上の Dual が要る（未確認）。
  Float32 での点別微分の精度、reverse の blocker（3b の前提）。
- 主張しない: gradient の精度・全場勾配・ε→0 の oracle との一致・物理的正しさ・格子独立性。
