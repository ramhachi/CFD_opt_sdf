# G2-DIAG4 結果: FORCED32_DELAYED_ONSET（診断。forced-32 は onset を遅らせ成長率を下げたが、corner の tangent mode は消えなかった）

事前登録（freeze `prerun_freeze.json`、独立レビュー 2 本の指摘を反映済み）どおりに 1 回だけ実行し、解析器（`diag4_analysis.json`、SHA は freeze に固定）を 1 回だけ実行した。
source commit `a6ecbc61`、T4（Tesla T4、Julia 1.12.6、WaterLily 1.8.0）、約 787 s、status COMPLETE、DONE あり、integrity 全 pass。δ 未決、GRAD-03 verdict なし、reverse 未着手、6 flag false、Float64・D1/D2/P1・bridge・FD-08 ĝ の比較なし。

## 回帰 gate（必須、全 bit 一致）
- B0 の step 1–980 = DIAG3 straight（980/980 一致）、B32fork の step 781–980 = DIAG3 F32 arm = DIAG2 V1c（200/200 一致）、fork 時点の clone は u・p・Δt が bit 一致、3 simulation の独立性（`Base.mightalias`）確認済み。これにより step 980 以降も同じ介入の延長として読める。
- control の B0 は登録規則どおり成長を再現し corner に局在（box 内エネルギー割合の中央値 0.9997）。onset: box max > 1 が step 838、magnitude gate が 864、persistent が 925、tangent が非有限になるのが step 1196（DIAG1 と同じ）。primal は 1500 まで有限。

## 主 verdict: B32fork（step 780 の B0 の厳密な clone + forced 32 反復）
`FORCED32_DELAYED_ONSET`。1500 step まで primal・tangent とも有限（tangent は 9e9 まで成長するが非有限にはならない）。
| 量 | B0（元の semantics） | B32fork（forced-32） |
|---|---|---|
| box max tangent > 1 となる最初の step | 838 | 1216 |
| magnitude gate（box > 1e3）| 864 | 1261 |
| persistent gate（連続 2 窓）が成立する step | 925 | 1300 |
| 成長率（log10 box max の傾き、decade/step）| 0.101（[880,980]）、0.112（[980,1100]）、0.097（[1100,1200]） | 0.046（[1200,1350]、R² 0.76）、0.039（[1350,1500]、R² 0.83） |
| 局在 | corner（エネルギー割合 0.9997）| corner（0.9999、最大点 (6;4;51)、(5;4;50)）|
- [880,980]、[980,1100]、[1100,1200] は傾き ≈ 0（−0.001〜0.002）で、DIAG2/DIAG3 の 200 step の抑制はその間は正しく観測されていた。しかし抑制は step ≈ 1200 まで続いた後に崩れ、tangent は同じ corner（x-min/y-min/z-max の遠方場の角）から再び指数的に増える。onset は B0 の約 1.45 倍（838 → 1216）に遅れ、成長率は約 1/2〜1/3。
- step 1500 では global max（9.1e9）が box max（1.65e8）を超え、最大点が (24;61;40) に移る（成長が box の外に広がった後の状態。mode の判定は登録どおり dominance 到達後の 25 step、step 1263 から。そこでは corner）。
- primal は B0 とほとんど変わらないが、差は記述的な報告だけにする: B32fork vs B0 の u の相対 L2 は最大 3.7e-6、p は 2.3e-3、drag は 4.2e-5、downforce は 8.5e-5（相対）。最大差の位置は (62;50;21)（p）と (61;50;21;3)（u）。

## 副 arm: B32fresh（step 0 から forced-32。主 verdict・閾値には使わない）
登録規則による分類は `DIFFERENT_MODE`、ただし限定つきで読むこと。
- growth event は step 838（magnitude gate、box > 1e3 ではなく global > 1e6）。global max が step 838 で 1.0e6、1000 で 6.5e14、1500 で 2.4e24 に達する。B32fresh の成長は B32fork より早く（B0 とほぼ同時期の 838）、成長率も大きい。
- 登録規則の mode 判定は「global max が floor の 100 倍（≈2100）に最初に達した step から 25 step」で、その step は 445 だった。step 445 は 2143 の孤立した spike（最大点は body 近傍 (88;42;37;3)、前後の step は 21 に戻る）で、成長 event（838）より前にある。この点で評価したため DIFFERENT_MODE となった。これは登録した評価点の弱さであり、事後に規則・閾値を変えない。
- 記述的な事実（分類には使っていない）: step 838–853 の最大点は (6;70;51)、(5;70;50)（x-min の端、z-max 側。j=70 は y の反対側）で、箱（j 1..8）の外。後の step では (12;8;54)、(6;3;53) と箱の中に入る。
- B32fresh の primal は B0 と、特に最初の数十 step で大きく違う（p の相対 L2 の最大 0.47、drag 0.021、downforce 0.023、最大は step 24 付近。forced-32 は始動過渡で元の収束した解と別の p を作る）が、最終的には 1e-5〜3.5e-3 に戻る。

## fork × fresh（副、機械的）
unstable × unstable。「DIAG2/DIAG3 の 200 step の抑制は delay か transient だった可能性が大きい」。B32fork（B0 の履歴の上で forced-32 に切り替え）も B32fresh（最初から forced-32）も、1500 step までに tangent が成長した。

## 何が言えて、何が言えないか
- 言える: 固定 32 反復の Poisson は、この D0・この窓では onset を step 838 から 1216 に遅らせ、成長率を下げるが、遠方場の corner の tangent mode は除かれない。DIAG2/3 の「抑制」は 200 step の窓の制約によるものだった。したがって forced-32 を「AD の修正」とも「安定な候補 semantics」とも呼べない。
- 言えない: 成長の機構（BDIM・`conv_diff!` の境界・corner の結合のどれか）、遅れの理由、Float64 での挙動、ĝ との整合、onset が 1500 以降に別の形であるか。登録どおり horizon は延長していない。
- Path A（fixed32 を候補 semantics として採用し transfer study）は、この結果では根拠が弱い。登録時の期待どおり、Path B（元の semantics を保ち corner/BDIM/conv_diff の線形化 mode を分解 = DIAG5）を優先すべきと考えるが、次の判断はユーザーに委ねる。Float64 は優先度が低い。

## 範囲
診断のみ。bridge 表なし、FD-08 ĝ との比較なし、δ 未決、GRAD-03 verdict なし、reverse 未着手、6 flag false、Float64・D1/D2/P1 なし。8740 step の bridge は走らせていない。
raw snapshot（175 MB）は git の外 `/Users/sota/kg_diag4/out1/grad_g2_diag4/snapshots/`（SHA は `kernel_output/snapshot_index.json` と `output_manifest.json`）。
