# G2-DIAG4: forced-32 Poisson は D0 の corner tangent モードを消すのか、onset を遅らせるだけか — 実行前の登録（未登録の診断）

証拠区分: `gpu_d0_forced32_long_horizon_diagnostic_unregistered`。**診断のみ。** gradient の qualification ではない。bridge の値・FD-08 の ĝ との比較・δ・GRAD-03 verdict を出さない。reverse には触らない。
6 つの qualification flag は false のまま。Float64 は走らせない。D1/D2/P1 は走らせない。**forced-32 は別の solver/backend 候補であり、AD の修正ではない。** FD-08 の既存の証拠は元の Poisson の意味に bind されたままである。
この note と `prerun_freeze.json` は T4 の最初の意味のある観測より前に固定する。G2・DIAG1〜3 の evidence は immutable。

## 問い（これだけ）
forced-32 の Poisson（step 780 まで元の意味で進め、781 から固定 32 反復）は、D0 の corner tangent モードを step 1500 までの長い horizon で**消す**のか、**onset を遅らせるだけ**なのか。
メカニズムの詳細（BDIM・`conv_diff!` の境界・面・角への分解）は調べない（DIAG5 以降）。

## 開示（この note より前に見たもの）
- DIAG1〜3 の結果。特に: DIAG2 の V1c と DIAG3 の F32 は step 781〜980 で u・p・Δt の全 bit が一致（200/200 step）。DIAG3 の straight 再生（元の意味）は step 0〜980 の全 bit の checksum を保存している。
- **forced-32 の corner の箱の max（step 781〜980）はスパイク状**: 通常 1.3e-2、step 891 に 2.1e-1、step 861 に全体の max 210 まで跳ねてすぐ戻る。区間の傾きは窓の取り方に敏感（[880,980] 0.0006、[931,980] 0.019、[951,980] 0.036）。このため区間 1 本の傾きだけで判定しない（下の持続の定義）。
- 元の run（baseline）の onset は約 838 step（箱の max が 1 を超える step）。1500 はその約 1.8 倍にすぎない。
- primal は tangent の overflow の後も有限（DIAG1 の step 1196: primal が非有限の行 0、tangent が非有限の行 31）。
- CPU の小さな dry-run（fork 6 step、end 14 step）でコードパス・clone の bit 一致・独立性・gate・例外時の挙動を確認した。成長は再現しない（科学データではない）。

## 構成（1 つの kernel、同一プロセスで 3 つの独立な simulation を lock-step）
D0、canonical v17、Candidate C、flow_24、Float32、Dual 幅 1、CuArray。各 simulation は自分専用の device 上の幾何・場・Poisson の配列を持つ（共有なし。`Base.mightalias` で全配列の組を検査）。
- **B0**: 元の意味（`sim_step!`）、step 0 → 1500。止まるのは primal が非有限になったときだけ。tangent が非有限になっても clip・reset・sanitize せず進める（primal は tangent に依存しない）。非有限になった後の B0 の tangent の統計は無効として扱い、primal の比較だけに使う。
- **B32fork（主）**: step 780 完了時に B0 の状態（`u`・`p`・Δt のベクトル）を host に複写して新しい simulation に書き戻す（bit 一致を検査）。以後 step 781 → 1500 を DIAG2/DIAG3 と同じ forced-32（`solver!(b; tol=0.0, itmx=32)`、他は元のまま）で進める。自分の最初の非有限（primal か tangent）で止める。
- **B32fresh（副、履歴依存の診断のみ）**: step 0 から forced-32、step 0 → 1500、完全に独立。**主 verdict には一切使わない。** B32fork の閾値・分類を変える根拠にしない。fresh を採用 backend にする判断は今回しない。

## 必須の回帰 gate（不一致なら停止し DIAG4_INCOMPLETE。980 以降は科学的データとして扱わない）
1. B0 の step 1〜980 の全 bit の checksum が DIAG3 の straight 再生と一致。
2. B32fork の step 781〜980 の全 bit の checksum が DIAG3 の F32 arm（= DIAG2 V1c）と一致。
3. clone が fork step で B0 と bit 一致。
参照の CSV は kernel の source 取得時に SHA で固定する（runner の pin）。host の analyzer も同じ gate を CSV から再導出する。

## 毎 step の観測（3 arm とも）
step、時刻、全体の max|tangent u|、corner の箱（`i∈1:12, j∈1:8, k∈49:56`）の max|tangent u|、tangent のエネルギー（全体・箱。`Σ|tangent|²`）、max の位置、primal の max|u|、primal・tangent の非有限数、
Poisson の反復数（2 回の projection）、最後の projection の primal・tangent の残差（max）、力（fx・fz の値と tangent）、全 bit と値のみの checksum。
参考（分類には使わない）: fork step の tangent に対する増分の max・エネルギー（全体・箱）・最大点。
B32fork と B32fresh は B0 との比較を毎 step（B0 が primal 有限の間）: u・p の相対 L2 差、最大差とその位置、箱の局所差、drag・downforce の相対差。B32fresh と B32fork の比較も記録。
snapshot（u・p）: step 1000, 1250, 1500 と、止まった arm の最後の step。raw は git に入れず SHA のみ。

## 区間と判定（結果を見る前に固定）
- 報告する区間（B0・B32fork・B32fresh それぞれ、全体と箱の `log10(max|tangent u|)` の傾きと R²）: `[880,980]`, `[980,1100]`, `[1100,1200]`, `[1200,1350]`, `[1350,1500]`。
- **持続的な成長の判定**: 100 step の rolling window を 25 step 刻みで全列挙（`800–900, 825–925, …, 1400–1500` の 25 本）。window は全 step が有効（有限）なときだけ評価。
  window が「成長」= 全体または箱の傾き ≥ 0.02 decade/step **かつ** R² ≥ 0.9（点数 ≥ 10）。**連続する 2 window 以上が成長**なら persistent gate。
- **magnitude gate（瞬間の escape）**: 有効な任意の step で 箱の max > 1e3 または 全体の max > 1e6。あるいは、step 1500 に到達する前に primal か tangent が非有限になった場合（arm が止まった）。
- **growth event** = persistent gate または magnitude gate または早期の非有限。event の step = 最も早いもの（persistent は 2 本目の window の終端）。
- **mode の局在**（event がある arm のみ。生の tangent 場で判定）: 全体の max が near-body floor の 100 倍（floor = 元の run の fork step での全体の max、約 21）以上に最初に達した step から 25 step（有効なもの）で、
  箱のエネルギー割合 `Σ_box|tangent|² / Σ_global|tangent|²` の中央値 ≥ 0.90、かつ最大点が箱の外にある step の割合 ≤ 0.5 なら「corner に局在」。
  global が dominance level に達しない場合は評価できない（`GROWTH_UNLOCALIZED`）。
- **control**: 同じ規則を B0 に適用し、B0 が growth event を持ち corner に局在と判定されなければ規則の検証に失敗しており、DIAG4_INCOMPLETE。
- **B32fork の分類（主 verdict）**:
  - `FORCED32_NO_ONSET_OBSERVED_TO_1500`: step 1500 まで有限で growth event なし。**「消えた」とは言わない**（onset が 1500 の後にある可能性を排除できない）。
  - `FORCED32_DELAYED_ONSET`: growth event があり、mode が corner に局在。
  - `FORCED32_DIFFERENT_MODE`: growth event があり、mode が corner に局在しない。
  - `FORCED32_GROWTH_UNLOCALIZED`: growth event があるが dominance level に達しない（局在を判定できない）。
  - `DIAG4_INCOMPLETE`: 回帰 gate・control・arm の欠落・kernel の status ≠ COMPLETE・integrity の失敗。
- **B32fresh の読み方（副、機械的、verdict に使わない）**: fork × fresh の 2×2（stable = NO_ONSET_OBSERVED、unstable = それ以外）。
  stable/stable = fixed32 の写像自体が安定である可能性と整合（1 run・1500 step、証明ではない）、stable/unstable = 効果が履歴依存の可能性、unstable/stable = step 780 以前に形成された mode を fixed32 では消せない可能性、unstable/unstable = DIAG2 の 200 step の抑制は delay/transient だった可能性が大きい。

## 登録時に開示する解析上の選択（ユーザー承認の文言を具体化・拡張した点。結果を見る前に固定）
- 持続成長の傾きは「全体 max 系列」または「箱 max 系列」（承認文言は箱が中心。箱外の成長を見落として NO_ONSET にしないため全体も含めた）。
- mode の局在は「成長 event の step」ではなく「全体 max が near-body floor の 100 倍以上に最初に達した step から 25 step」で評価。最大点の位置が不明（空）な step は箱外として数える（保守側）。箱外 step の割合 ≤ 0.5（`MODE_OUTSIDE_FRACTION`）。
  この評価点は承認文言（「最大点が箱外 or エネルギー割合 <0.90 なら DIFFERENT_MODE」）より緩い/遅い。body 近傍の定常最大点（≈21）を「別モード」と誤判定しないための具体化であり、dominance level に達しない場合は `GROWTH_UNLOCALIZED` とする。
- arm の履歴に欠番・重複・開始 step の誤り、または有限と記録された行の tangent max が非数値の場合は `INCOMPLETE_ARM`（NO_ONSET にはしない）。
- B32fresh は fork×fresh 表にだけ使う。B32fresh の欠落・壊れた CSV は完全性の失敗として DIAG4_INCOMPLETE にする（fail-closed）が、主 verdict の閾値・floor・control には一切使わない。
- 解釈文・次の判断の文言は verdict ごとに固定（NO_ONSET 以外で「onset なし」とは書かない）。

## 解釈の規則
`NO_ONSET_OBSERVED_TO_1500` でも forced-32 を AD の修正とは呼ばない。正しい言い方は「primal の反復 solver の写像を元の停止規則から固定 32 反復に変えると tangent の安定性が変わる（solver 写像の感度）」。primal 出力の差の大きさは `cmp_*.csv` の要約を記述的に報告するだけで、「わずか」とは断定しない。
DIAG3 で、収束度（残差）や primal の変化量では説明できないことが分かっている（Dual 停止 arm は残差が同程度でも不安定）。ここで言えるのは「固定 32 回という離散反復写像が例外的に安定化している」ことだけである。

## 禁止
g_forward と ĝ の表、δ の選択、GRAD-03 の qualification、flag（特に `field_gradient`）の変更、Float64、D1/D2/P1、reverse、DIAG5 の内部分解（BDIM・`conv_diff!` の境界・x-min/y-min/z-max の角の結合）、結果を見た後の区間・閾値の追加、適応的な追加 arm。
**B32 が安定でも 8740 step の bridge を自動では走らせない。** step 1500 の evidence で止まる。次のユーザー判断: Path A（fixed32 を候補の solver semantics として採用し、まず primal と有限方向の応答の bounded な transfer/equivalence study）か Path B（元の semantics を保ち corner/BDIM/conv_diff の線形化モードの分解）。
**delayed onset の場合**はさらに延長しない。結論は「forced32 は成長率/onset を変えるが不安定な tangent モードを消さない」とし、内部の線形化モードの分解を優先、Float64 は低優先度。

## retry 規則
provider の一時障害で、意味のある観測が 1 件も出ておらず、source・登録・kernel の同一性が不変なら retry 可。**instrumentation / source の不具合**は attempt を保存し、source を変えるなら同じ freeze を上書きせず新しい identity で最大 1 回。科学的な結果は retry しない。
