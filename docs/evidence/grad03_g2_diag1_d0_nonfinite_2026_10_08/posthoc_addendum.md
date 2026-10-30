# G2-DIAG1 への post-hoc 追補（DIAG2 の前提。登録した規則の外の探索であり、DIAG1 の freeze・analysis・verdict は変更しない）

再現: `scripts/posthoc_grad_g2_diag1_addendum.py`（出力 `posthoc_addendum.json`）。ledger 由来の数値は git 内の gzip ledger から、snapshot 由来の数値は git 外の raw snapshot から再計算できる。

## 訂正: H4（有限反復 Poisson の derivative）の status
DIAG1 の機械的な規則は H4 の refutes を「直前 20 steps で itmx=32 に一度も達しない」で与えた。しかし Poisson の停止判定は **primal の残差だけ**で行われる（Dual の比較は値で行う）。
したがって反復数は tangent の収束について何も言わない。実データでは Poisson は step 31 以降ずっと **1 反復**で、primal の相対残差 |r|/|z| は約 1.0e-3、
tangent の相対残差は 1.7〜4.3 %（step 100〜1000 の全測定点）と、全期間にわたって 20〜40 倍大きい。**DIAG1 の「H4 refutes」は取り下げ、H4 は unresolved に戻す**（H11 として下に再定義）。

## 観測（post-hoc）
1. **局在**: u の tangent のエネルギーの 99.97 %（step 900）が角の箱 `i<12, j<8, k≥48` に入る。境界面から 3〜8 セルの層に 94 %（step 900）/ 76 %（step 1100）。
   最大点は 0-based `(5,3,50)` で、x 方向の符号が交互に反転する（最大点を 1.0 として `-0.53, 1.0, -0.68, 0.20`）。最大点の primal は一様流（u = 0.99999899, −1.8e-4, −4.3e-4）。
2. **onset は実在する**: 箱内の max|tangent| は step 2〜500 で 1.2〜1.5e-2 の定常（log10 ≈ −1.9）、step 900 で 2.4e7、1000 で 4.7e16、1100 で 3.2e27（0.093 decade/step）。
   step 500 の水準から 900〜1000 の傾きで外挿した onset は **step 約 800**（max に見えるのは step 849 から。物体側の tangent は 21 前後で定常のため）。箱の外の tangent は 900 で 2.1e5、1100 で 2.2e25 と、箱より約 2 桁小さく追随する。
3. **Δt の tangent は原因ではない**: 4.84e-2 の定常が step 860 まで続き、900 で 0.093、1000 で 1.3e7 と、モードの成長の後で増える（Δt の値は 0.3297 で一定）。
4. **stage ごとの倍率**（step 871、u の max|tangent|）: predict の BDIM ×2.26、project1 の勾配補正 ×0.58、correct の BDIM ×2.80、スケール ×0.5、project2 の勾配補正 ×0.71。1 step の正味は **×1.31**。増幅は 2 つの BDIM stage で作られ、projection が部分的に打ち消している。
   （BDIM は `u += μ₁∂n(...) + V + μ₀ f`、`f` は直前の `conv_diff!` の出力。倍率が stage の局所作用素の固有値ではないことに注意: 全域 max の比であり、モードが支配する step 870 付近でのみ意味がある。）

## 解釈の限定（未検証の仮説）
- **H11（post-hoc）**: tangent の Poisson 解が primal の停止判定のため未収束で、境界付近の高波数モード（符号交互の形）を減衰させきれない。
- primal は同じ領域を 1e-7 級の丸め誤差ごと数百 step 運んでいるのに増幅していない。真の Jacobian に固有値 > 1 のモードがあれば primal の丸め誤差にも出るはずなので、
  これは**物理的な Lyapunov 成長ではなく、AD の tangent 演算が primal の摂動の線形化と一致していない**（停止した反復解法・分岐・境界処理）ことを示唆する。ただし証明ではない。
- step 約 800 で何が切り替わったかは未解明。DIAG2 の fork 再生（step 780 から）で onset の再現を確認する。
