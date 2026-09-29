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
