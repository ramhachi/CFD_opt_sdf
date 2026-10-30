# #48 LOWDIM-01 結果: `LOWDIM_ACCEPT`（固定 4 方向 basis で 1 つの coefficient 空間の step が accept された。capability の statement）

事前登録（`prerun_freeze.json`、独立レビュー 2 本の指摘を反映済み）どおりに T4 の 1 kernel（baseline + 候補 4 + control 2 = 7 state）を 1 回実行し、解析器（freeze に SHA を固定）を 1 回だけ実行した（`lowdim01_analysis.json`）。
source `4c99143c`、freeze `8ef70f05…`。baseline の力 CSV は FD-08 の `baseline_v17` と byte 同一（STEP-01 の 3 kernel と同じ）、全 state 完了、host 再計算と Julia の summary が相対 1e-9 で一致、integrity pass。
**full-field gradient でも OPT-01（#30）でもない**。単一 trial・単一 flow grid（flow_24）・[80,120] tU/L の時間加重の力・決定論的な Float32 T4 の結果で、grid-independent な downforce でも物理的な downforce でもない。σ0（3e-6 N）は FD-08 の nominal な値。reinitialization は使っていない。δ 未決、GRAD-03 verdict なし、6 flag・FD-08 verdict は不変、AD なし。出力は `kernel_output/`。

## 手順（登録どおり）
basis = D0 / D1 / D2 / P1。係数勾配は STEP-01 の ±2.5 mm の downforce の centered な差（hash 束縛）で、proposal 専用: `g = (+0.781, −0.108, −0.096, −0.382)` N/m、`c = g/‖g‖`、`d_prop = normalise(Σ c_i d_i)`（max-norm 1）。候補 `s ∈ {1.25, 2.5, 5.0, 7.5} mm` を実 CFD で評価し、accept は実応答と hard gate だけ（予測は参考）。control は逆向き（accept しない）。

## 結果（baseline: downforce 0.33163 N、drag 0.32390 N）
| 候補（max\|Δφ\|） | Δdownforce（N） | Δdrag（N） | 分解された改善 | hard gate | 線形予測（参考） | accept |
|---|---:|---:|---|---|---:|---|
| 1.25 mm | **+4.05e-4**（+0.12%） | −1.68e-4 | はい | 通過（volume −2.1%、Eikonal 0.019） | +7.85e-4 | **accept（選択）** |
| 2.5 mm | −5.0e-5 | −7.4e-4 | いいえ（負） | 通過（−4.2%、0.038） | +1.57e-3 | reject |
| 5.0 mm | −3.4e-3 | −3.1e-3 | いいえ | 通過（−8.2%、0.074） | +3.14e-3 | reject |
| 7.5 mm | −1.0e-2 | −7.1e-3 | いいえ | **失敗**（−11.9%、0.108） | +4.71e-3 | reject |
- accept は 1.25 mm のみ。downforce は +4.05e-4 N（baseline の 0.12%、閾値 3e-5 N の 13 倍）、drag は 1.7e-4 N 下がった（制約は満たす）。volume −2.1%、Eikonal の中央値 0.019、clearance・mask・component 数も満たす。
- 事前の予想（2 次モデル）は 1.25 mm で +5.0e-4 N、2.5 mm で +4.2e-4 N だった。1.25 mm はほぼ合い（実際 +4.05e-4）、2.5 mm は外れた（実際 −5e-5。D0+P1 の非加法性などが原因の可能性。未検証）。

## control（逆向き。accept しない）と proposal の符号
| step | 順方向の Δdownforce | 逆方向の Δdownforce | 奇数部（(順−逆)/2） | 線形予測 | 奇数部/予測 | 偶数部（(順+逆)/2） |
|---|---:|---:|---:|---:|---:|---:|
| 1.25 mm | +4.05e-4 | −1.21e-3 | +8.10e-4 | +7.85e-4 | 1.031 | −4.04e-4 |
| 2.5 mm | −5.0e-5 | −3.19e-3 | +1.57e-3 | +1.57e-3 | 0.998 | −1.62e-3 |
- **FD で作った proposal の符号と大きさは、奇数部としてほぼ正確に実現した**（奇数部が線形予測の 1.031 倍と 0.998 倍）。逆方向は確実に downforce を下げる。したがって accept は「勾配が正の向きへ微小 step を踏んだだけ」ではなく、proposal が情報を持っている。
- 一方、偶数部（曲率）は負で s² に比例する（−4.04e-4 → −1.62e-3、比 4.0）。**改善は奇数部が偶数部を上回る間だけ**: `改善(s) ≈ a·s − b·s²`（a = 6.5e-4 N/mm、b = 2.6e-4 N/mm²）で、ゼロ点は 2.5 mm、最大は 1.25 mm で約 4.05e-4 N（今回の候補がほぼ最適点）。この方向に沿った 1 回の step で取れる downforce の増加は約 0.12% が上限で、それ以上は再線形化（次の反復）か曲率の扱いが要る（post-hoc の記述。登録した判定ではない）。

## 何が言えて、何が言えないか
- 言える: 固定した 4 方向 basis について、centered FD で proposal を作り、実 primal の片側 line search と hard gate（clearance・mask・component・volume・Eikonal の中央値、reinit なし）で accept した step が 1 つ存在する。proposal の奇数部の予測は 0.2〜3% の精度で当たった。
- 言えない: full-field gradient、OPT-01（#30）の代替、一般的な descent 方向、複数 step の最適化の成立、downforce の大きな改善、grid 非依存・物理的な downforce、reinitialization の影響、basis を 10〜30 次元に広げたときの挙動。accept は 1 trial の actual primal の結果で、FD-08 の verdict・flag・δ・GRAD-03 に影響しない。#48 から #30 への置換には phase_plan での正式な contract supersession が別途必要。
- **次の判断（ユーザー）**: (a) 受け入れた状態から次の反復（8 run の centered FD + line search で、1 反復あたり約 0.1% の downforce）を事前登録して回し、step 幅の contract（半径 ≈ 1.25 mm）と反復での累積を見る、(b) basis を広げる（10〜30 次元）、(c) 曲率を扱う（2 次モデルを line search に組み込む）、(d) reinitialization（#28）を扱う。自動では進めない。
