# G2: full-window forward-AD bridge — 結果 **G2-BLOCKED**（試行 1、未登録の測定）

証拠区分: `gpu_full_window_forward_ad_bridge_measurement_unregistered`。gradient の qualification ではない。δ は未選択、GRAD-03 の verdict なし、reverse には触れていない、6 つの qualification flag は false のまま。
判定は事前登録の規則（`prerun_note.md`、`prerun_freeze.json`）どおり。bridge の解析（`analyze_grad_g2_bridge.py`）は**実行していない**（host の terminal 検証が FAIL のため、規則どおり禁止）。

## 何が起きたか
- Kaggle kernel `ramhachi888/cfd-opt-sdf-grad-g2-full-window-bridge` version 1（Tesla T4、source commit `e44d0f08…`、runner SHA `d0d942eb…`、push 2026-10-08T09:10Z）。pin はすべて検証済み。
- **plain Float32 baseline は完走**（8,740 ステップ、1,093 サンプル、t=120.003、ループ 108 秒・合計 166 秒、VRAM ピーク 83 MB）。
  host で再計算した窓平均は、登録済み FD-08 formal の `baseline_v17` と**相対差 0.0（ビット一致）**:
  drag 0.3239039699743226 N、downforce 0.3316344583180616 N。測定の意味の再利用（1093 サンプル、窓の補間、1/900 のスケール）が T4 上で正しく再現されたことを示す。
- 次の **D0 の Dual run が step 1200（t=16.41、起動直後の過渡）で非有限値を検出して abort**（`non-finite force/tangent`）。
  事前登録の fail-fast と fail-closed が設計どおり動き、残りの 3 方向は実行されず、DONE は書かれず、runner は exit 1 で終了した。出力は回収できた。
- terminal 検証: `FAIL_G2_TERMINAL_INTEGRITY`（DONE なし、ERROR あり、run 在庫が 5 つでない）。analyzer は拒否した。

## 判定: G2-BLOCKED
規則: 「途中の run の primal または tangent が非有限 → G2-BLOCKED、部分的な方向だけで bridge の結論を作らない、Dual 幅 4 への切替の retry はしない」。bridge の値（AD と FD-08 の傾きの差）は得られていない。

## 分かっていること・分かっていないこと
- 分かっている: Dual{Float32,1} の tangent を、Candidate C の flow_24 で約 1,200 ステップまでは安全に伝播できない。D0 でこの時点（t=16.4）に非有限が出る。
  G1（2 ステップ）では有限だったので、長時間の挙動は G1 の capability から外挿できなかった。
- 分かっていない: 非有限になったのが tangent（桁あふれ）か、Dual 側の primal か、その原因。harness は失敗した run の部分時系列を保存しない設計だったため（失敗時の情報は `error` の 1 行だけ）、
  物理的な指数的増幅、Float32 での `μ₀` ほぼ縮退による 1/μ₀ の増幅、Poisson の有限反復の微分、のどれかを切り分けるデータが無い。仮説は検証していない。

## 次の選択肢（ユーザー判断。いずれも新しい source identity と事前登録が必要で、この freeze は上書きしない）
1. **診断 run**（安価）: D0 のみ、失敗時に部分時系列を保存し、どの量がいつ・どの桁で非有限になるかを記録する（数分の T4）。原因の切り分けだけで、bridge の値は出さない。
2. **Float64 の Dual**: T4 の FP64 は遅い（G1 の 1 ステップは JIT 込みで約 44 秒）。1 方向あたり 15〜45 分の見積もり（未測定）で、4 方向なら約 1〜3 時間。GPU 残量（約 15 時間）には収まる。
3. 長時間の窓平均の bridge を断念し、GRAD-03 の δ を別の根拠（短時間の AD、FD-08 の不確かさ、案 D の 3b）で決める。

## 保存した証跡
`kernel_attempt1/`（出力一式、kernel log、push log）、`terminal_verification_attempt1.json`、`identity_free_check.json`、`prerun_freeze.json`、`independent_reviews.md`、`cpu_dryrun_diagnostic/`。
