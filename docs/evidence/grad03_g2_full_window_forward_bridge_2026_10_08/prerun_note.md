# G2: full-window forward-AD bridge 測定 — 実行前の登録（未登録の診断・測定）

証拠区分: `gpu_full_window_forward_ad_bridge_measurement_unregistered`。gradient の qualification ではない。**δ を選ばない。GRAD-03 の PASS/FAIL を出さない。**
reverse（CPU/CUDA/custom adjoint）には触らない。6 つの qualification flag は false のまま。FD-08 は再 fit しない。
この note と `prerun_freeze.json` は、T4 の最初の意味のある観測より前に固定する。

## 問い
FD-08 の観測量（Candidate C / canonical v17 / flow_24 / 窓 [80,120] tU/L の時間加重平均力）について、
forward-mode AD の**点別の方向微分** `g_forward`（N/m）と、FD-08 が固定した Model A の**有限振幅の回帰傾き** ĝ（ε 0.5〜5 mm）は、どの程度一致するか。
これは GRAD-03 の δ を後で決めるための校正データであり、判定ではない。

## 開示（この note より前に見たもの）
- G1（T4、2 ステップ、D0、Dual 幅 1）は G1-PASS（Fx 0.6%、Fz 8.0% で CPU Float64 と一致）。長時間の挙動は未観測。
- CPU の短い dry-run（`G2_BACKEND=cpu`、窓を 0.3 tU/L に縮めた code-path 確認）は、診断として実行した（保存する場合は診断と明記。科学データではない）。
- FD-08 の ĝ・SE は immutable な scope record から読む（`record.json`、SHA `3f8b7d3e…`）。G2 の結果は ĝ を変えない。

## 測定（固定）
- 5 つの独立した simulation を、同一 kernel・同一 T4 で、この順に実行する: plain（Float32）、D0、D1、D2、P1（それぞれ `Dual{Tag,Float32,1}`）。
  Dual 幅 4 は使わない（G1 が検証したのは幅 1 のみ）。各 run は新規に構築し、状態を共有しない。
- 摂動: `phi(α) = phi0 + α·d`、`α = Dual(0,1)`、単位は m。tangent は solver 力 / m で、host が `1/900`（ρU²Δx²）を掛けて N/m にする（ĝ と同じ単位）。
- 観測量は登録済み FD-08 job と同一: `sim_step!(sim)`（既定の remeasure あり。G1 の `remeasure=false` とは**異なる**）、1 ステップ目の warm-up を step 1 に数える、
  8 ステップごと（と終端）に `-(pressure+viscous)`（candidate のみ）を採取、drag = Fx、downforce = −Fz、窓の端点は線形補間、台形の時間加重平均。Poisson は WaterLily 既定。
- 保存する時系列: step、時刻（値と tangent）、Fx・Fy・Fz・圧力 3 成分・粘性 3 成分（それぞれ値と tangent）。host が全て独立に再計算できる。
- 時刻の扱い: 時刻 `sim_time` は Δt（CFL）経由で phi に依存する Dual。**主**は時刻の tangent を伝播する版（FD oracle が時間格子の変化込みの微分を測っているため）。
  参考として時刻を固定した版も同じ表に載せ、差を記録する。

## 判定（インフラ・capability のみ。科学的な PASS/FAIL ではない）
- **G2-MEASURED**: 次を全て満たす。source・入力・hash の同一性、T4 の runtime 記録、plain と 4 方向が全て完了（5/5、想定外の run なし）、全 run が必要な終端時刻に到達、窓が成立、
  primal・tangent が有限、全時系列が存在、host の再計算（kernel の summary と相対 1e-9 で一致）、CUDA の scalar fallback なし、
  Dual run と plain の primal の整合（**窓平均**の相対差 ≤ 1e-3。時系列の最大差は報告のみ）、
  plain の窓平均が、登録済み formal の `baseline_v17`（host 再計算の drag/downforce）を相対 1e-6 以内で再現すること（測定の再利用に誤りがない確認。事前登録した harness の gate で、科学的な閾値ではない）。
- **G2-BLOCKED**: 上のどれかが成立しない（途中の run が非有限なら残りを打ち切る fail-fast）。部分的な方向だけで bridge の結論を作らない。Dual 幅 4 への切替の retry はしない。
- AD と FD-08 の傾きの差の大きさ・符号は、G2-MEASURED/BLOCKED の判定には使わない。それは測定する科学データそのもの。

## 解析（実行前に凍結、1 回だけ実行）
terminal の host 検証（`PASS_G2_TERMINAL_INTEGRITY`）の後にのみ、`scripts/analyze_grad_g2_bridge.py` を 1 回走らせる。8 行（4 方向 × drag/downforce）を必ず出し、欠落があれば集計を作らない。
各行: `g_forward`、`g_hat_fd08_modelA`、`se_g_fd08`、符号、絶対差、`|Δ|/|ĝ|`、`|Δ|/SE`、比 `g_forward/ĝ`、時刻固定版の値。集計: 相対差の最大・中央値、`|Δ|/SE` の最大、符号の不一致の数。
`selected_delta = null`、`grad03_verdict = null`。結果を見て解析コード・閾値・FD-08 の値を変えて再実行しない。

## 結果の意味（限定）
測るのは「厳密な離散の窓平均目的関数の点別微分」と「FD-08 の有限振幅 Model A 回帰傾き」の差。一致しても、ε→0 の連続な微分・物理的な真値・格子独立性・任意方向・全場勾配・reverse の正しさは主張しない。
不一致でも、直ちに「AD が誤り」とは言わない（メソスケールの傾きとの差として記録する）。

## retry 規則
転送・download の一時的な失敗で、意味のある力・tangent が 1 件も生成されておらず、source・登録・kernel の同一性が不変なら retry 可。
source や infra の bug は attempt を保存し、source を変えるなら同じ freeze を上書きせず新しい identity を作る。科学的な不一致（大きな差・符号の不一致）は結果であり、retry しない。

## 追記（独立レビューの指摘を反映、freeze 前）
- tangent は有限回反復の Poisson 解（収束判定は primal の値だけで行う）と、CFL の `max` の枝、最終サンプル「t ≥ 120 になった最初のステップ」の選択を、そのまま微分する。
  したがって `g_forward` は「この離散アルゴリズムの点別の微分」であり、FD oracle が ε の有限振幅で見るこれらの分岐の影響とは一致しないことがありうる。大きな差を「AD の誤り」とは読まない。
- 流れが非定常なら、時刻の tangent を伝播する値と固定した値の差が大きくなりうる。差は `time_tangent_effect_relative` に記録する。解釈は「測定した、検証してはいない」に留める。
- plain と登録済み `baseline_v17` の 1e-6 の gate は、同じ T4 型で Float32 の reduction が決定論的であることを前提にする。不一致なら G2-BLOCKED（登録した規則）。
