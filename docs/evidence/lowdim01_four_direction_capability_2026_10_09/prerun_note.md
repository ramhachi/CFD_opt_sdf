# #48 LOWDIM-01 事前登録: 固定 4 方向 basis での capability（実行前に固定）

目的: 固定した低次元 basis（初回は検証済みの D0 / D1 / D2 / P1 の 4 方向）で、**centered FD で proposal 方向を作り、その方向を信用せずに、実 CFD の片側応答で line search して accept / reject する**手順が成立するかを示す。
結果は「4 次元 basis の capability」であって、full-field gradient でも OPT-01（#30）でも insurance path 全体の成立でもない。δ 未決、GRAD-03 verdict なし、6 flag false、FD-08 verdict 不変、AD なし。

## 1. 設計（STEP-01 の結果を受けた形）
- **basis**: `D0_interface_offset`、`D1_filtered_seed11`、`D2_filtered_seed2026`、`P1_upstream_lobe`（FD-08 の方向、max-norm 1）。baseline = `cal_baseline_01`（FD-08 の `baseline_v17`）。
- **係数勾配（proposal 専用）**: STEP-01 の ±2.5 mm の centered な差 `g_i = [R_downforce(+2.5 mm) − R_downforce(−2.5 mm)] / (2 × 2.5 mm)`（N/m、unit-max-norm の basis 方向あたり）を **hash 束縛で再利用**する（同じ baseline・同じ job・決定論的。STEP-01 の kernel は baseline が FD-08 と byte 同一だった）。
  束縛: `step01_analysis.json` 全体の SHA（freeze に固定、analyzer も照合）に加えて、inventory の `g_sec` と step が STEP-01 の値と一致することを analyzer が照合する（`r_plus`・`r_minus`・ĝ は照合しない）。この kernel でも baseline の byte 同一を gate にする。
- **proposal 方向（downforce を最大化）**: `c = g / ‖g‖₂`（係数空間の Euclid 勾配。曲率の重みなし）、`v = Σ c_i d_i`（float64）、`d_prop = v / max|v|`（`<f4`、max-norm 1）。step `s`（= max|Δφ|）は基底ごとに `c_i / m · s` の係数を与える（m = max|v| = 1.4028）。
  g = (D0 +0.7807, D1 −0.1084, D2 −0.0961, P1 −0.3823) N/m、c = (+0.886, −0.123, −0.109, −0.434)、基底係数（per mm of s）= (+0.632, −0.088, −0.078, −0.309)。
  **合成した方向は係数勾配を足すだけでなく physical な Δφ に落としてから max|Δφ| で正規化する**（STEP-01 で D0+P1 が非加法的だったため、予測は accept に使わない）。
- **line-search 候補**: `s ∈ {1.25, 2.5, 5.0, 7.5} mm`（`Δφ = s · d_prop`、`phi_child = float32(float64(phi) + s/1000 · float64(d_prop))` = STEP-01 と同じ演算）。
  STEP-01 から、単一方向で downforce が上がる**方向ごとの変位**は D0 で ≲1.8 mm、P1 で ≲3.1 mm、D1・D2 で ≲2.3 mm、改善の最大でも約 3e-4 N（downforce 0.33 N の約 0.1%）と狭い。候補の s は合成方向の max|Δφ| なので、方向ごとの変位は `s · c_i/m`（D0 は 0.63 s、P1 は 0.31 s）。したがって合成では s ≲ 3 mm 程度まで一次の改善が見込まれ、下限側の 1.25 mm を加えた。
- **control（accept にも selection にも使わない）**: 同じ step（1.25、2.5 mm）を**逆向き**（−d_prop）に踏む 2 state。順方向と逆方向の downforce 変化の差（奇数部）と和（偶数部）を記録し、proposal の符号が情報を持つか（「FD の proposal が有効」か「勾配が正の向きへ微小 step を踏んだだけ」でなくても偶数部だけで改善して見えるか）を記述的に見る。
- **実行**: FD-08 の per-state Julia job をそのまま使う（STEP-01 と同じ）。T4 の 1 kernel（baseline + 候補 4 + control 2 = 7 state、≈ 30 分）。
- **reinitialization は使わない**（`reinitialization = none`）。#28 は Round 3 が FAIL（thin box と canonical で Eikonal・smoothed-volume drift・edge displacement・idempotence の gate を通らない）で未 qualified。
  その代わりに SDF 品質・geometry・volume の gate を記録し、下の hard gate は accept の必要条件にする。

## 2. accept / reject（実 CFD の応答と hard gate だけが権威）
候補が accept されるのは**全て**を満たすとき:
1. downforce の実応答が baseline より **3e-5 N 超**増える（10σ0、FD-08 の nominal T2 の分解能。分解された改善のみ）。
2. drag の実応答が baseline より **3e-5 N 超**は増えない（drag 制約。#30 の downforce objective + drag / volume constraints と整合）。
3. 次の hard geometry gate を全て満たす（solver 前に inventory に登録済み。runner が phi の SHA を検証するので、登録値はその phi の値）:
   - clearance（zero-level からの距離）≥ 0.15 m、fixed / forbidden / root / design mask と support の保持、固体 cell の face-connected component が baseline と同数（1）
   - **smoothed volume**（`sdf_native_smoothed_volume_v1`）の相対変化 `|V_ε(候補)/V_ε(baseline) − 1| ≤ 10%`
   - **narrow-band の Eikonal の中央値** `median | |∇φ| − 1 | ≤ 0.10`（reinit なしで SDF 性がどれだけ崩れるかの gate。baseline は 2.5e-7）
   閾値（10% と 0.10。丸い値）は、候補の geometry を計算する前に（registrar のコードに定数として書いてから実行した）、STEP-01 の 44 state の solver なしの探索（`geometry_exploration_step01_states.json`: D0 は 2.5 mm あたり smoothed volume ±5.5% と Eikonal 中央値 +0.05、P1 は ±2.4%、D1/D2 は ±0.01%）から決めた。なお clearance と mask の gate は、違反する候補を registrar の `construct_state` が例外で拒否する（登録の段階で abort する）ので、登録に残る候補では常に真。記録のみで gate にしない量: sharp volume の変化、Eikonal の p95 / max（baseline 自身が p95 0.29 / max 1.0）、node の component 数、最小 feature 幅・gap。
4. control は accept されない。予測は accept に使わない（参考として「線形予測 / 実際」を併記）。モデルが外れても、実際に改善して制約を満たせば accept。
- drag 制約は「baseline より 3e-5 N 超は増えない」で、drag が減る分には（どれだけ減っても）制約を満たす（極端な drag 減は gate にしない）。力の単位は N（[80,120] tU/L の時間加重平均）。σ0 = 3e-6 N は FD-08 の nominal な値で、再実行ノイズの実測ではない（solver は決定論的）。
- 選択: accept された候補のうち**実 downforce の改善が最大のもの**（同値なら小さい step。厳密に同値でなくても差が分解能未満なら大きい step が選ばれうる）。1 つ以上 accept → `LOWDIM_ACCEPT`（4 次元 basis の capability の statement）。全て reject → `LOWDIM_NO_GO`（bounded No-Go。有効な結果）。integrity が崩れれば `LOWDIM_INCOMPLETE`。

## 3. gate（fail-closed）
runner: baseline の `flow_24.forces.csv` が FD-08 の `baseline_v17`（SHA `39370386…`）と byte 同一でなければ以降の候補を走らせず停止。pin・phi の SHA・変化 node 数の検証。DONE は全 state 完了のときだけ。
analyzer: DONE/ERROR、manifest（全 state の 3 ファイルを列挙）、pin、T4、plan の一致、各 state の summary（phi/state/NPZ の SHA、margin、有限、`t_end_reached ≥ 120`、threads = 1）、host の力の再計算と summary が相対 1e-9、baseline の byte 照合と drag 0.3239039699743226 N・downforce 0.3316344583180616 N との相対 1e-12、凍結した analyzer・contract・states module・force_io・formal criteria・inventory（正規 JSON）・束縛した STEP-01 の解析の SHA。1 回だけ書く（`--check` で先に gate だけ確認）。

## 4. 言い方の規則
結果は「固定 4 方向 basis の capability」で、単一 trial・単一 flow grid（flow_24）・[80,120] tU/L の時間加重の力・決定論的な Float32 T4 の結果に限る。grid-independent な downforce でも物理的な downforce でもない。full-field gradient でも OPT-01 でも、proposal 方向が一般に descent 方向だという主張でもない。`LOWDIM_NO_GO` は「この basis・proposal・候補集合の bounded No-Go」で、低次元最適化一般の No-Go ではない。
accept は 1 trial の actual primal の結果で、勾配の qualification・FD-08 の verdict・flag・δ・GRAD-03 に影響しない。#48 から #30 への置換には phase_plan での正式な contract supersession が別途必要。

## 5. 事前の確認の開示
- STEP-01 の結果（登録済み）: centered secant は 12.5 mm まで符号一定だが片側応答は曲率支配で、downforce を上げる側は 4 方向とも 2.5〜5 mm で局所傾きの予測から外れる。これが候補に 1.25 mm を加えた理由。
- **閾値の決め方の開示**: 閾値を決めるとき、探索の数値（D0 の 2.5 mm あたりの volume と Eikonal の変化）から proposal の候補の大きさ別の volume を**粗く見積もっていた**（5 mm と 7.5 mm は帯の縁か外になると予想）。候補の正確な値は閾値を定数として固定した後に初めて計算した（見積もりは実際より大きめだった: 5 mm の −8.2% は帯の内側）。7.5 mm が帯の外に出ることは、閾値を決めた時点でおおむね予想していた。
- solver なしの探索: 44 の STEP-01 state の volume・Eikonal・component（`geometry_exploration_step01_states.json`）。候補 4 の geometry gate の結果は登録時点で既知: 1.25 / 2.5 / 5.0 mm は全 gate を通り（smoothed volume −2.1% / −4.2% / −8.2%、Eikonal 中央値 0.019 / 0.038 / 0.074）、**7.5 mm は volume（−11.9%）と Eikonal（0.1085）の gate で落ちる**。7.5 mm は情報として走らせるが accept されない。
- **結果の予想（登録時点）**: 参考の線形予測（局所傾き × 係数）は +0.79 / +1.6 / +3.1 / +4.7 mN だが、STEP-01 の曲率を入れると実際はずっと小さい。単一方向ごとに STEP-01 の奇数部・偶数部から 2 次モデル `g·x + c·x²` を作って和を取ると、1.25 mm で **+5.0e-4 N**、2.5 mm で +4.2e-4 N（閾値 3e-5 N の十倍超）、5.0 mm で −1.4e-3 N、7.5 mm で −5.6e-3 N。したがって**1.25 / 2.5 mm での `LOWDIM_ACCEPT` がありそう**。
  ただし、(a) STEP-01 で D0+P1 は非加法的だったので和の予測は不確か（STEP-01 の格子点だけの補間では 1.25 mm で −3e-5 N と逆の符号になる。2 次モデルは格子点間の山を捉えるが、それも仮定）、(b) **ACCEPT になっても STEP-01 の曲率から概ね予見できる結果で、「FD の proposal が優れている」ことの強い証拠ではない**（control で順方向と逆方向を比べる）、(c) 全 reject（`LOWDIM_NO_GO`）も有効な結果。
- 候補の追加（control と 1.25 mm）は、STEP-01 の結果を見た後、solver 前に登録した。
