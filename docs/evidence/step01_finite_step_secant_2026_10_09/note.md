# #47 STEP-01 結果: `STEP01_RECORDED`（有限 step の応答の記録。gradient の qualification ではない）

事前登録（`prerun_freeze.json`、独立レビュー 2 本の指摘を反映済み）どおりに T4 の 3 kernel（A: 21 state、B: 21 state、C: 5 state、計 47 run）を 1 回ずつ実行し、解析器（freeze に SHA を固定）を 1 回だけ実行した（`step01_analysis.json`）。
source `d7bd1fda`、freeze `e82bacf0…`。**3 kernel の baseline の力 CSV は FD-08 の `baseline_v17` と byte 同一**（SHA `39370386…`）、全 state が完了、host 再計算と Julia の summary が相対 1e-9 で一致、integrity と全 gate が pass。
δ 未決、GRAD-03 verdict なし、FD-08 verdict・6 flag は不変、reverse 未着手、AD なし。出力は `kernel_output/{a,b,c}/`。

## 登録した量（centered secant `g_sec(s) = [R(+s) − R(−s)] / (2s)`、N/m）
| series（direction | response） | FD-08 の ĝ | g_sec（2.5 → 12.5 mm） | g_sec/ĝ | 符号 | 30% / 50% agreement radius |
|---|---:|---|---|---|---|---|
| D0 | downforce | +0.8015 | 0.781, 0.763, 0.712, 0.642, 0.566 | 0.97 → 0.71 | 一定・ĝ と同符号 | 12.5 / 12.5 mm |
| D0 | drag | −0.1040 | −0.113, −0.130, −0.127, −0.129, −0.158 | 1.08 → 1.52 | 一定・同符号 | 10 / 10 mm |
| D1 | downforce | −0.1064 | −0.108, −0.099, −0.095, −0.089, −0.079 | 1.02 → 0.74 | 一定（2.5 mm は未分解） | 12.5 / 12.5 mm |
| D1 | drag | −0.0637 | −0.068, −0.068, −0.070, −0.064, −0.058 | 1.06 → 0.92 | 一定・同符号 | 12.5 / 12.5 mm |
| D2 | downforce | −0.0917 | −0.096, −0.097, −0.096, −0.095, −0.094 | 1.05 → 1.02 | 一定（2.5 mm は未分解） | 12.5 / 12.5 mm |
| D2 | drag | −0.1698 | −0.169, −0.170, −0.169, −0.167, −0.166 | 0.99 → 0.98 | 一定・同符号 | 12.5 / 12.5 mm |
| P1 | downforce | −0.3852 | −0.382, −0.368, −0.361, −0.350, −0.335 | 0.99 → 0.87 | 一定・同符号 | 12.5 / 12.5 mm |
| P1 | drag | −0.2143 | −0.213, −0.209, −0.206, −0.201, −0.194 | 0.99 → 0.90 | 一定・同符号 | 12.5 / 12.5 mm |
- **centered secant は 8 series すべてで 12.5 mm まで符号が一定で ĝ と同符号**。ĝ に対する比は 0.71〜1.52 で、30% agreement radius は 7 series で 12.5 mm、D0 drag で 10 mm（比 1.52 の 12.5 mm で外れる）。drift（2.5 mm に対する曲がり）が 30% を超えるのは D0 drag の 12.5 mm だけ。
  **agreement radius は記述的な量で、step が正しいという意味ではない**（ĝ は Model A の局所傾きで、5 mm 超は FD-08 の校正範囲外の外挿）。
- **η_even（偶数部 / 奇数部）が 1 を超える**: D0 downforce は 2.5 mm で 1.37、12.5 mm で 8.75（他の series は 2.5 mm で 0.21〜4.8、12.5 mm で 1.1〜16）。偶数部（`R(+s)+R(−s)−2R(0)`）は s² に比例する（D0 downforce で 2.5 → 5 → 10 mm が 5.4e-3 → 2.15e-2 → 8.2e-2 N）。つまり **応答の曲率成分が奇数成分（局所傾き）を上回る**。
- 合成方向（±7.5 mm、最大変位 0.3h に再正規化）の加法性: `D1+D2`（成分 4.67 mm）は相対 0.8〜25%（downforce は 0.8% と 8.6%、drag は 5.8% と 25%。drag の minus は 4e-4 N と小さい）、
  **`D0+P1`（成分 7.5 mm）は大きく崩れる**（相対 130〜450%。合成の ΔR は −5.1e-3〜−1.1e-2 N に対し、単一方向の和の予測は −2.8e-2〜−3.3e-2 N）。補間の不確かさは D0+P1 で 1e-10 N（格子点上）、D1+D2 で 2e-5〜6e-5 N。

## post-hoc の記述（登録した表からの派生。登録外）
1. **centered secant が安定でも、片側の応答は ĝ の符号に従わない**。`ΔR(+s)` と `ΔR(−s)` の符号を ĝ の予測（+s で ĝ·s、−s で −ĝ·s）と比べると:
   - drag を下げる側（ĝ<0 で +s）は 4 方向とも 12.5 mm まで予測どおり（D0 drag の ΔR(+s) = −1.6e-3〜−3.4e-2 N）。
   - **downforce を上げる側は 4 方向とも予測どおりにならない**: D0 downforce の ΔR(+s) は 2.5 mm から負（−7.3e-4 N、予測は正）、D1・D2 downforce の ΔR(−s) は全 step で負（予測は正。2.5 mm は未分解）、P1 downforce の ΔR(−s) は 2.5 mm だけ予測どおりで 5 mm 以降は負。
   - 両側が予測どおりに保たれるのは D1 drag で 5 mm、D2 drag で 10 mm、P1 の 2 series は 2.5 mm まで。D0 の 2 series は 2.5 mm でも片側が外れる。
   - ΔR(+s) と ΔR(−s) がともに負になる場合が多く、偶数部は 8 series すべてで負（どの方向に動かしても drag も downforce も下がる傾向）。
2. η_even = 1 となる step（偶数部が奇数部を上回り始める）の線形外挿: D0 drag 0.5 mm、D0 downforce 1.8 mm、D2 downforce 2.2 mm、D1 downforce 2.3 mm、P1 downforce 3.1 mm、P1 drag 4.5 mm、D1 drag 5.7 mm、D2 drag 11 mm。
3. 偶数部の起源は未検証。物理的な曲率かもしれないが、`phi + ε·d` は距離場（|∇φ| = 1）を保たないので、SDF の性質の崩れ（再初期化の有無）が寄与している可能性がある（#48 で再初期化を含めるかを事前登録で決める材料）。
4. FD-08 の ĝ（奇数部だけを測る centered な応答）はここでも整合した（centered secant が 12.5 mm まで ĝ の 0.7〜1.5 倍）。FD-08 の結論は変わらない。

## 何が言えて、何が言えないか
- 言える: 8 series の centered secant は 0.1〜0.5 h で符号が保たれ、ĝ と整合する。一方、実際に optimizer が踏む片側の応答は曲率成分に支配され、特に downforce を上げる側は 2.5〜5 mm で局所傾きの予測から外れる。複数方向の合成は D0+P1 で加法的でない。
- 言えない: gradient の qualification、optimizer の安全な step 幅、偶数部の原因、ĝ の外挿の妥当性、決定論的な noise の大きさ（σ0 は nominal）。agreement radius は検証ではない。
- **#48 LOWDIM-01 への含意（ユーザー判断）**: 係数空間の step 幅の contract は、centered な傾きではなく**実際の片側応答に対する accept/reject（actual primal）と曲率を前提にする**必要がある。step 幅は 2.5 mm 級から始め、downforce の改善は片側応答の符号が予測と一致するかを毎 step 確認する。再初期化の扱いを事前登録に含めるか、合成方向をどう使うか（D0+P1 は加法的でない）も決める。

## 範囲
診断のみ。gradient・FD-08 verdict・flag・δ・GRAD-03 に触れない。kernel の identity: `ramhachi888/cfd-opt-sdf-step01-{a,b,c}`（Tesla T4、Julia 1.12.6）。T4 の state 時間は A 4028 s、B 3811 s、C 858 s（合計約 2.4 時間。A と B は並列）。
