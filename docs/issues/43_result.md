# Issue #43 (GEN-17) 結果: genesis v17 と局所 FD 診断 (2026-09-30)

エビデンス種別: contract / capability (genesis) + numerical diagnostic (CPU、短時間)。
qualified FD oracle、勾配、物理量の claim はしない。v16 とその証跡は変更していない。

## 1. genesis v17 の登録

- スクリプト: `scripts/sdf_native_genesis_v17_2026_09.py --register`
- 証跡: `docs/evidence/sdf_native_genesis_v17_2026_09.json`
  (SHA-256 `8335cb7569dae7f75780b133e3f588b802e3b13258f012c391339ffc6a1c10b5`)
- 入力は v16 と同一: handoff manifest、surface STL (`5e6d2107…8d11`)、source density VTI。すべて hash を照合した。
- 格子: 原点 (-1.0, -0.8, -0.6)、h = 0.025 m、節点 121x65x49 (v16 は h = 0.05 m、61x33x25)。
- mask: v16 の source cell mask を各軸 2 倍に複製し、v16 と同じ genesis の射影規則を適用した。design 節点は 107415、fixed/forbidden/root は 0。
- state_sha256 `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`。
  state と phi (f4 Fortran) は gitignore された `work/sdf_native_genesis_v17/` にあり、スクリプトで再生成できる。
- **再現性 gate**: 同じ標本化コードを h = 0.05 で実行すると、v16 の phi とビット単位で一致した (最大差 0)。
  したがって、v16 との違いは格子間隔だけである。

### 力に効く帯の勾配 gate (事前登録: 帯 |phi(center)| <= 0.05 m、閾値 |∇phi| < 0.25 で fail)

| | 帯のセル数 | < 1e-6 | < 0.25 | 判定 |
|---|---|---|---|---|
| v16 | 2470 | 66 | 66 | fail |
| v17 | 19376 | 0 | 3 | **fail** |

v17 の 3 セルはどれも |∇phi| = 0.1265、セル中心 phi = -0.0499 である。厚さ 2h の固体の内部で、中心線 (medial axis) 上にあり、帯のちょうど端に位置する。
表面上で勾配がつぶれている v16 の問題とは性質が違うが、gate は登録どおり fail として記録する。
gate の定義 (帯の端での内部 medial axis の扱い) を直すには、新しい版として登録し直す必要がある。

## 2. 局所 FD 診断 (CPU Julia、今の bridge と診断用の正則化 τ = 0.1)

- 摂動: `scripts/sdf_native_fd04_v17_perturbations.py`。登録済みの生成器 (`generate_directions` / `perturbed_state`) を v17 に適用し、変更していない。
  v17 では narrow band = h = 0.025 m なので、方向の台 (support) は v16 より狭い。
- 診断スクリプトは #36 と同じもので、格子は `FD04_SHAPE` / `FD04_H` で指定する。
- 生データ: `docs/evidence/sdf_native_fd04_v17_{frozen,full}_response_2026_09.csv` (+ `.sha256`)。

### 圧力固定 (baseline flow の t = 3, 8 の圧力場を固定)

今の bridge で、± の力の差は ε に比例した (t = 3、Fx)。

- D0: 0.016 / 0.032 / 0.080 / 0.162 / 0.341 (ε = 0.5 / 1 / 2.5 / 5 / 10 mm、比 1:2:5:10:21)
- D1: 0.004 / 0.007 / 0.019 / 0.037 / 0.076
- D2 (Fz): 0.012 / 0.024 / 0.061 / 0.122 / 0.244

正則化の有無による差は、どの方向でも 5% 以下だった。**v17 では法線の正則化は不要。**

### フル解析 (t = 0〜2、平均窓 1〜2、今の bridge)

± の力の差 (ε = 0.5 / 2.5 / 10 mm):

- D0 Fx: 0.140 / 0.721 / 3.140
- D1 Fx: 0.014 / 0.057 / 0.204
- D2 Fz: 0.023 / 0.092 / 0.344

概ね ε に比例した。ε = 10 mm ではやや比例より小さい (非線形か、初期過渡の影響)。D2 の Fx は信号が 0.003 程度で、過渡ノイズと同じ程度。

## 3. 重要な副作用: baseline の力が変わる

同じ flow 設定で、baseline の力は大きく変わった。

- 圧力固定 (t = 3) の Fx: v16 は 93.3、v17 は 59.7
- フル解析 (t = 0〜2) の Fx: v16 は 144.7、v17 は 98.5

v16 では、勾配がほぼ 0 のセルで向きのでたらめな単位法線が使われていた。そのため、偽の力が加わっていた可能性がある (未検証)。
どちらが真の値に近いかは、body-fitted の参照解がないので判断できない。
**v16 の W3 / W4 / FD の数値と qualification は、v17 に引き継げない。**

## 4. 限界

- 短時間の計算で、登録された平均窓 t = 80〜120 では計算していない。CPU、Float32、各ケース 1 run で、noise floor は測っていない。
- flow 格子は flow_16 (0.05 m) のまま。厚さ 0.05 m の板は、flow 側では 1 セル分しかない。

## 5. 次の手順 (#37 / #42 への含意)

1. v17 用の W3 (primal contract) と W4 (sensitivity) の criteria を、新しい round として登録する。
   v16 の形状と state hash が約 15 ファイル (W3 / W4 / FD の job と registrar、`V16PhysicalProfile.jl`) にハードコードされているので、ここを引数化する必要がある。
2. その後に #37 で、v17 の状態を使って FD round を登録する。ε ラダーと判定基準は変えない。
3. 勾配 gate の定義修正 (帯の端での内部 medial axis の除外) は、新しい版として #29 で扱う。


## W4 v17 canonical sensitivity matrix (2026-09-30)

証拠種別: 登録済み有限boxの数値感度・実行能力証拠。物理profile、絶対空力値、格子収束の資格化ではない。W4 v16のcriteria/resultは変更していない。

### 登録・実行・host検証

- canonical state: h = 0.025 m、point shape 121x65x49、state SHA `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`。
- 登録source commit: `4c20787c1ab55ea45f98631e6e78ba6d5502a1a2`。W3 v17 criteria SHA `00af9ed92111b48a69d0eebebfa143db7e23c7caee322bb88cdb6ac36ff2e608` とPASS result SHA `e7d48a98d912e570ea3b077bb5904106c2558c845fd286684775bd6907e68bba` に束縛。
- W4 v17 criteria: [`kaggle_w4_v17_sensitivity_criteria_2026_09.json`](../evidence/kaggle_w4_v17_sensitivity_criteria_2026_09.json)、SHA-256 `5eceb62c17e347679cdadc88c68266e7fe00b392da40a8029ed3544a002e0f01`。loader互換名 [`w4_v17_criteria.json`](../evidence/w4_v17_criteria.json) は同じbyte列/hash。
- Private dataset `ramhachi888/cfd-opt-sdf-v17-w4-sensitivity`, version 1。remote inventoryは5 filesで登録・stage内容と全件一致。canonical inventory SHA-256 `d3cbdfb385f443e5f8b413fc07675d79f319250b8e01bb617476041c651bc6fb`。state NPZ SHA `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`、Fortran phi SHA `e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`。
- Exact private T4 kernel `ramhachi888/cfd-opt-sdf-w4-v17-sensitivity/1` は `KernelWorkerStatus.COMPLETE`。terminal-status log SHA-256 `f68a2f79c37b8a345270e5629923874db1bfed09310393164e7599c448b1cb44`。
- output SHA manifest SHA-256 `c19eef6a90c7a99408ce8639a42dd1138ee7d00666697dc4b6b491ef19c8ebbb`、検証済みoutput files 24。
- host result: [`kaggle_w4_v17_sensitivity_result_2026_09.json`](../evidence/kaggle_w4_v17_sensitivity_result_2026_09.json)、SHA-256 `25297c4646d048050974d6beccbb90ac672c910eeb558a99c1006226bdd59933`。sidecar SHA-256 `3abd19b88f70790de965ce94c1676074693bb197884bfb8305bd269a27d667be`。登録source commit `4c20787c…` のdetached worktreeでT0–T10を再計算し、10項すべてPASS。


実装の事前検証ログ (source treeはfeature commit `827938652b058ae1e04a17e6794f4645b07c272d` と登録merge commit `4c20787c…` で同一):

- focused pytest: `47 passed in 0.53s`; log SHA-256 `0738a7adb3d90d6cb0ec6c904ec51408d8e64f4e7d8924f188d7db7a1e6f2330`。
- `python -m compileall src tests scripts`: pass; log SHA-256 `6991fb3ab12c4d29fa89532334a19de4a3008624bb98caec5fab96edde8ed866`。
- Julia parse: pass; log SHA-256 `d5e3afea8893a428fdc4cfcbb2eb68d56c639abe114ce0c5f705e549ef37a257`。
- W4 Julia contract test: 9/9 pass; log SHA-256 `6afb1f3e8d92de6f4ce340b2da167177d3a37c21c6ed564d1e311e45084e4403`。
- W3 profile adapter test: 16 checks pass, no solver step; log SHA-256 `9edf147abbdab74f13397d1c73ccc794cdb8dcf8683ff2102114ac36017bc81d`。
- full pytest: `1201 passed, 4 skipped, 37 failed`; log SHA-256 `30fac7e9989b044a3bf5353d91c8564e5032a33c48c7005b3a720c2a801de2c2`。37件は既知のignored `work/` fixture欠落によるbaseline failureと同じ集合で、新規failureは確認されなかった。
- validation logs: `work/issue43_w4_v17/validation/`。criteria登録前に `git diff --check` もpass。

| Case | Pressure drag (N) | Viscous drag (N) | Total drag (N) | Pressure downforce (N) | Viscous downforce (N) | Total downforce (N) | Cd |
|---|---:|---:|---:|---:|---:|---:|---:|
| `flow_16` | 0.139154 | 0.084024 | 0.223177 | 0.263313 | -0.009832 | 0.253482 | 0.697430 |
| `flow_24` | 0.224426 | 0.101891 | 0.326317 | 0.338420 | -0.007391 | 0.331029 | 1.019742 |
| `flow_32` | 0.238758 | 0.111243 | 0.350002 | 0.367534 | -0.006273 | 0.361261 | 1.093756 |
| `domain_xplus1m_16` | 0.138946 | 0.084031 | 0.222977 | 0.263966 | -0.009834 | 0.254132 | 0.696802 |

Downforceは `-Fz` とし、圧力成分に対して粘性 downforce 成分は反対向きなので負値である。stationarity値は登録窓のrelative half-window drift。peak VRAMはdecimal MBで記載。

| Case | Drag stationarity | Downforce stationarity | Wall time (s) | Peak VRAM (MB) |
|---|---:|---:|---:|---:|
| `flow_16` | 2.552e-6 | 6.270e-6 | 36.61 | 26.3 |
| `flow_24` | 1.180e-6 | 6.318e-6 | 102.02 | 82.9 |
| `flow_32` | 1.939e-5 | 1.326e-5 | 339.92 | 185.7 |
| `domain_xplus1m_16` | 8.181e-6 | 1.931e-5 | 30.58 | 31.0 |

全ケースでstationarity threshold 0.02を満たした。

### 登録ケース間の変化

下表の相対値は登録定義 `100 × |to−from| / max(|from|, |to|)`。Δはto−fromの符号を保つ。

| Transition | Total drag ΔN (%) | Pressure drag ΔN (%) | Viscous drag ΔN (%) | Total downforce ΔN (%) | Pressure downforce ΔN (%) | Viscous downforce ΔN (%) |
|---|---:|---:|---:|---:|---:|---:|
| flow16 → flow24 | +0.103140 (31.61%) | +0.085273 (38.00%) | +0.017867 (17.54%) | +0.077547 (23.43%) | +0.075107 (22.19%) | +0.002441 (24.82%) |
| flow24 → flow32 | +0.023684 (6.77%) | +0.014332 (6.00%) | +0.009352 (8.41%) | +0.030232 (8.37%) | +0.029114 (7.92%) | +0.001118 (15.13%) |
| flow16 → domain x+1 m | -0.000201 (0.09%) | -0.000208 (0.15%) | +0.000007 (0.01%) | +0.000651 (0.26%) | +0.000653 (0.25%) | -0.000002 (0.02%) |

解像度を上げるとpressure/viscous双方のdragが増加した。flow16→24ではpressure drag差が `0.085273 N`、viscous drag差が `0.017867 N`。flow24→32ではそれぞれ `0.014332 N` と `0.009352 N`。domain x+延長の全force変化は最大でも0.26%だった。

### v16比較と解釈の範囲

同じflow16条件で、v16 round 4からv17への変化はtotal drag `0.336018 → 0.223177 N` (-33.58%)、total downforce `0.353373 → 0.253482 N` (-28.27%)。pressure dragは `0.228125 → 0.139154 N` (-39.00%)、viscous dragは `0.107893 → 0.084024 N` (-22.12%)。pressure downforceは `0.362322 → 0.263313 N` (-27.33%)、viscous downforceは `-0.008949 → -0.009832 N` (symmetric relative 8.97%)。これはcanonical SDF stateが違うcross-state diagnosticであり、v16結果のtransferや物理精度の根拠ではない。Stage Vとの比較は行っていない。

W3 v17のflow16値とW4 v17 flow16値は出力上完全一致した。ただしW3/W4間の数値repeatability gateは登録されていないので、独立再現性の資格化とは扱わない。

**事実:** flow16→24とflow24→32で有限なforce差があり、domain x+1 mの差は小さい。v16 round4 flow16からcanonical v17 flow16へのtotal force差は大きく、主に圧力成分に現れた。全T0–T10はPASS。

**推論:** この結果はtested domain changeよりflow resolutionへの応答が大きいこと、また薄い形状の解像度不足仮説と整合する。ただし、単一形状・有限の3 resolutionと1 domain extensionだけなのでgrid convergenceや薄板透過を確定しない。flow24→32にもdrag 6.77%、downforce 8.37%の差が残り、どのflow gridをFD oracleに使うべきかはこのmatrix単独では決められない。

### verifier invocationの記録と停止点

通常CLIでの最初のhost verifier invocationは、`remote_inventory_sha256`引数が同名helper関数をshadowし、inventory hashを作る箇所で `TypeError: 'NoneType' object is not callable` を出してfail-closedした。この試行は [`kaggle_w4_v17_sensitivity_host_cli_attempt_diagnostic_2026_09.json`](../evidence/kaggle_w4_v17_sensitivity_host_cli_attempt_diagnostic_2026_09.json) (SHA-256 `6a520b17db979021bca68f345bc5f99f71f4204f3eeda30aa7df58247c5e8508`) として別に保存した。sourceを変えず、登録source commitの同じ `verify()` 関数へhash helper callableを渡す外部driverでhost検証をやり直し、上記PASS resultを得た。今後のCLI利用前にこのshadowingは修正が必要。

PASS resultの `fd_entry_gate` は `OPEN` だが、`fd05_execution_authorized=false`。#37 FD-05のcriteria登録・dataset upload・kernel実行はいずれも行っていない。W4 PASSをもってflow resolutionを選んだり、FD-05へ自動進行したりせず、ここで停止してユーザーの判断を待つ。
