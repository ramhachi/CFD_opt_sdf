# FD-06 に向けた診断: 法線の下限 (normal floor) で FD-05 の不連続は消えるか

- 実施日: 2026-10-01
- 証拠の区分: **診断のみ**（CPU の短時間計算）。qualified な力の値ではなく、FD-05 の判定も変えない。
- 前提: [`37_fd05_solver_free_diagnosis.md`](37_fd05_solver_free_diagnosis.md)
- スクリプト: `scripts/sdf_native_fd06_normal_floor_cpu_probe.jl`、
  `scripts/sdf_native_fd05_normal_census.py`
- 生データ: `docs/evidence/sdf_native_fd06_normal_floor_cpu_probe_2026_10/`（14 本の CSV と `MANIFEST.sha256`）

## 変更の内容と、τ を決めた根拠

- 法線を `n = g / |g|` から `n = g / max(|g|, τ)` に変える。流れの計算（BDIM）と力の積分の両方に効く。
- τ = 0.25。これは repo が genesis の census で登録済みの「平坦」の閾値（`FLOW_GRADIENT_THRESHOLD = 0.25`）と同じ値で、**力の応答を見る前に決めた**。
- τ を大きくするほど、法線が ε に比例して変わる範囲が広がる。solver を使わない法線の診断（flow_24 の band 38,561 点）で、法線の最大変化量を比べた。

| τ | D1 の法線変化 (ε = 0.5 / 1 / 2.5 / 5 / 10 mm) |
|---|---|
| 0（現行） | 2.0 / 2.0 / 2.0 / 2.0 / 2.0（ε に依存しない反転） |
| 0.1 | 0.16 / 0.32 / 0.81 / 1.0 / 1.0 |
| 0.25 | 0.065 / 0.13 / 0.32 / 0.65 / 1.0 |

- τ=0.25 なら、登録済みの plateau 判定に使う最初の 3 つの ε（0.5、1、2.5 mm）の範囲で、法線の変化が ε に比例する。頭打ちになるのは 10 mm。
- 1e-3〜0.05 の空白帯に τ を置く案は採らなかった。ε=0.5 mm の摂動でも |∇φ| が約 0.02 動くので、τ が小さいと変化がすぐ頭打ちになり、反転を隠せない。

## CPU の短時間計算

- 条件: flow_24（W4 の case）、v17 の canonical φ、t = 6 tU/L まで。窓は tU/L 4–6。
- FD-05 の raw データでは ±ε の差が tU/L 5–20 の時点で確定していたので、短時間の計算で見る。
- 検証: CPU の raw baseline は、Kaggle の GPU の値と序盤で 0.07% 以内で一致した（tU/L=0.09 で drag 547.74 と 547.36）。
- 注意: 窓の違い（4–6 と 80–120）と、CPU/GPU の float の差があるので、Kaggle の値との直接比較はしない。raw と floor の比較は CPU 同士で行う。

### ±ε の差と片側の差（N）。ベースラインとの差は R(±ε) − R(0)

| 方向 | ε | 変種 | drag の差 (+ε−(−ε)) | drag の片側 (+ε / −ε) | viscous Fx の片側 (+ε / −ε) |
|---|---|---|---|---|---|
| D1 | 0.5 mm | raw | −0.00205 | −0.00338 / −0.00133 | −0.00296 / −0.00235 |
| D1 | 0.5 mm | **floor** | −0.00007 | −0.00005 / +0.00003 | −0.00002 / +0.00002 |
| D2 | 0.5 mm | raw | +0.00147 | −0.00159 / −0.00306 | −0.00222 / −0.00311 |
| D2 | 0.5 mm | **floor** | −0.00017 | −0.00009 / +0.00008 | +0.00001 / −0.00001 |
| D1 | 2.5 mm | raw | −0.00208 | −0.00344 / −0.00135 | −0.00296 / −0.00237 |
| D1 | 2.5 mm | **floor** | −0.00039 | −0.00028 / +0.00012 | −0.00012 / +0.00007 |

## 分かったこと

1. **raw は CPU でも FD-05 の現象を再現した。** +ε と −ε の両方が、ベースラインから同じ向きに約 −0.002〜−0.003 N ずれ、ε を 5 倍にしてもほぼ変わらない。
2. **floor を入れるとこのずれが消えた。**
   - 片側の差が +ε と −ε で符号が逆になった（反対称）。
   - 大きさは 1e-4 N 以下に下がった。
   - D1 の drag の差は ε=0.5 mm で −7e-5 N、2.5 mm で −3.9e-4 N で、ε が 5 倍のとき約 5.6 倍だった。ε に比例している。
3. **ベースラインの変化は小さい。** floor により drag は −0.0024 N（約 0.7%）、downforce は −0.0013 N 動いた（CPU、tU/L 4–6）。

## 主張できること・できないこと

**主張できる**
- FD-05 の ε 非依存の不連続は、法線の `g/|g|` の反転が原因である可能性が高い。floor を入れるとずれが消えるという介入の結果がこの仮説と一致する。
- τ=0.25 の floor は、ε=0.5〜2.5 mm の範囲で ±ε の応答を反対称・ε 比例にする（D1/D2、tU/L 6 まで）。

**主張できない**
- 発達後の窓（tU/L 80–120）で、5% の plateau 判定に通ること（未確認）。
- D0 の挙動（今回は流していない）。ε=5、10 mm での挙動。
- 物理的な力の精度。floor は primal を変えるので、W3/W4 相当の baseline を取り直す必要がある。
- FD oracle や勾配の qualified 化。qualified 関連のフラグはすべて false のまま。

## 次の手順（FD-06。未登録）

1. 本体の `WaterLilyBody.jl` に `normal_floor` を追加する。既定値は 0 で、現行の挙動と hash はビット単位で変えない。テストを追加する。
2. FD-06 を新しい契約として登録する。canonical state は v17、flow は flow_24、ε・判定基準・33 run の構成は FD-05 と同一にし、変更するのは normal_floor=0.25 だけ。
3. 別件の修正として、FD の runner と host verifier の間の criteria hash の食い違いを直す。FD-05 で T12 が FAIL した原因。
4. Kaggle で 33 本を実行し、host で厳密に検証する。

## Correction (2026-10-01, append-only)

The "次の手順" above and the #37 comment said the floor would live in `GridSDFWaterLilyBody` (`normal_floor`, merge
`a13a4fc`). That in-place change broke a W2b round-5 test that pins `WaterLilyBody.jl`'s hash, so it was reverted and the
floor now lives in a separate file, `julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl`
(`NormalFloorWaterLilyBody`). `WaterLilyBody.jl` is byte-identical to its state before `a13a4fc`. Result:
[`37_fd06_result.md`](37_fd06_result.md).
