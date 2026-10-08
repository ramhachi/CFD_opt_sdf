# G1: T4 上の Dual（forward AD）capability gate — 結果（未登録・診断）

証拠区分: `gpu_forward_ad_capability_spike_unregistered`。gradient の qualification ではない。6 つの qualification flag は false のまま。
判定規則は `prerun_note.md`（実行前に固定、`prerun_freeze.json`）。判定は `scripts/evaluate_grad_dual_gpu_g1.py` の出力（`g1_evaluation.json`）。

## 判定: **G1-PASS**
Kaggle kernel `ramhachi888/cfd-opt-sdf-grad-dual-gpu-spike` version 1（Tesla T4、CUDA.jl 6.3.1、WaterLily 1.8.0、ForwardDiff 1.4.5、Julia 1.12.6）、
実行 source commit `0319a34d07c2e1de78d275395c822574ed64e699`、script SHA-256 `a2798b7b…`（`run_identity.json` で pin 検証済み）。

| 項目 | 規則 | 結果 |
|---|---|---|
| 完走（compile 失敗・scalar 例外なし） | 必須 | 達成（`spike_exit_code` 0、status COMPLETE） |
| tangent が有限・非零、partial を含む場が有限 | 必須 | 達成（場の tangent 最大 59.55） |
| AD の primal と plain の primal の相対差 | ≤ 1e-3 | 最大 2.2e-6 |
| GPU Float32 の tangent と CPU Float64 の AD tangent の相対差 | ≤ 1e-1 | Fx 0.60%、Fz 7.99% |

## 数値（Float32 Dual、2 ステップ、flow_24、D0、`remeasure=false`、Poisson 既定 tol 1e-4/itmx 32。solver 単位）
| 力 | plain | AD tangent |
|---|---:|---:|
| combined Fx（ground 込み） | −2073.56 | 22914.4 |
| combined Fz | 1804.92 | −4932.23 |
| candidate drag | 2072.82 | −22906.8 |
| candidate downforce | 2134.05 | −8890.3 |

- Fz の 7.99% は規則の範囲内だが閾値（10%）に近い。2 ステップの瞬時値で、Float32 と Float64 の差がそのまま出ている。
- 情報のみ（判定に使わない）: Float32 の中心差分との差は ε=1e-3 m で Fx 0.27%・Fz 1.2%、2e-3 m で 1.7%・6.8%
  （Float32 の丸めの影響を含む）。Float64 Dual の 1 ステップ tier も完走（primal 差 2.9e-16、tangent 有限）。
  Dual の JIT 込みの時間は約 45 秒、VRAM のピークは約 165 MB。

## 保存した出力
`kernel_output/`（`output_manifest.json` に Kaggle 側の SHA を記録。`instantiate.log` だけは行末の空白を除いた複製で、原本とは SHA が異なる）。

## 限界・次
- この結果は「T4 上で Dual が動く」ことだけを示す。窓平均（約 8,700 ステップ）、4 方向同時の partial、oracle の観測量との比較は未検証。
- 閾値は CPU の結果を見た後に置いた判断（開示済み）。GPU の結果は規則を動かしていない。
- G2（full-window bridge）の事前登録はこの結果を見てから行う。reverse には触れていない。
