# G2-DIAG3: tangent-only の Poisson 継続は遠方場 corner の tangent モードを消すか — 実行前の登録（未登録の診断）

証拠区分: `gpu_d0_tangent_only_poisson_continuation_diagnostic_unregistered`。**診断のみ。** gradient の qualification ではない。bridge の値・FD-08 の ĝ との比較・δ・GRAD-03 verdict を出さない。
reverse には触らない。6 つの qualification flag は false のまま。Float64 は走らせない。D1/D2/P1 は走らせない。production の backend を選ばない。
この note と `prerun_freeze.json` は T4 の最初の意味のある観測より前に固定する。G2・DIAG1・DIAG2 の evidence は immutable。

## 問い
**G2/DIAG1 で使った元の primal Poisson の意味を変えずに、tangent の Poisson 解だけを追加で収束させたとき、遠方場 corner の tangent モードは消えるか。**
「32 反復を本番採用する」実験ではない。primal の解をより厳密にすること（DIAG2 の V1）と tangent の解をより厳密にすることを分離する。

## 開示（この note より前に見たもの）
- DIAG1/DIAG2 の結果（DIAG2: baseline 成長 0.1009 decade/step、4 反復 0.1713、16 反復 0.0394、32 反復 −0.0003、corner/面の tangent を殺すと消える、Δt・ghost・exit は無効）。
- DIAG1 追補: Poisson は step 31 以降 1 反復、primal の相対残差 約 1e-3、tangent の相対残差 2〜4 %。
- **WaterLily 1.8.0 の Poisson のソース**（`Poisson.jl` / `MultiLevelPoisson.jl`）を読んだ。下の「Poisson の意味」に記す。
- **CPU の小さな fixture**（Dual の球の body、32³、Float64）で、tangent-only 継続の数学を検証済み（`fixture_results.json`、`scripts/test_grad_g2_diag3_poisson_fixture.jl`）:
  収束した Dual の tangent と一致（定数モードを除き 7e-16）、Dual の残差の tangent が有限差分と一致（2e-7）、primal 収束時に k 回の tangent-only 反復が k 回の Dual 反復と一致（2e-16）、primal の bytes が不変、反復の停止・上限・固定回数が正しく働く。
- 最終版の job の CPU dry-run（小さい fork、数 step）でコードパスを確認した。成長は再現しない（onset の前）ので科学データではない。

## 原案からの修正（開示）
1. **「tangent-only の最初の N 回が baseline の Dual の最初の N 回と一致」は数学的に成立しない**: Dual の反復は primal も更新し、反復写像の微分に `(∂M/∂θ)·r`（前処理の微分 × primal 残差）を含むため。
   代わりに、(a) 収束した Dual の tangent との極限の一致、(b) primal 収束時の k 回の一致、(c) Dual の残差の tangent と有限差分の一致、(d) primal の bytes 不変、を fixture で検証した。
2. **A′ ≠ 0**: `A = A(L)`、`L = μ₀` は body 帯域で tangent を持つ（max 30）。`dA x` の項は Dual の残差に自動的に入る（A′ を 0 と仮定していない）。遠方場では `L` の tangent は 0。
3. **primal identity は「値だけの checksum」**で測る。既存の checksum は tangent の bit を含み、介入のない run でも tangent が変われば一致しない。step ごとに u・p の値の xor と和、Δt の値の bit を plain 再生と比べる。
4. **近傍床（floor）の定義**: DIAG2 では形式化されていなかった。**plain 再生の fork step（780）での全体の max|tangent u|**と定義する（DIAG2 の baseline で約 21）。
5. **Stage B の primal の同一性**: baseline の D0 は step 1196 で壊れるので全 horizon の bit 比較はできない。Stage B の primal は、**G2 の plain Float32 の履歴**と窓平均で比べる（G2 の登録済みの harness gate、相対 1e-3）。
6. **選択規則に余裕を足す**: plateau の最も緩い端は選ばない（緩い隣が suppresses であること）。候補は threshold family のみ（固定回数の arm は plateau の証拠と地図）。
7. **tangent の停止判定の尺度**: `max|δr| ≤ τt · max|δz|`（DIAG2 で報告した相対残差 `r/z` と同じ定義）。反復は 1 回の tangent 残差の評価ごとに 1 V-cycle、最大 64。
8. **ガウジ（定数モード）の扱い**を明示した: Dual の `residual!` は primal の平均が `2·eps` 以下だと**平均の補正を tangent にも行わない**（fixture で確認: tangent の平均が 30 回の Dual 反復後も不変）。
   tangent の RHS が活性セル（`iD ≠ 0`）上で不整合になりうる。継続では活性集合の平均を除いた RHS（マスク済み）を解き、**除いた平均を記録**する（`tangent_mean`）。報告する残差は生の値と、活性集合の平均を除いた値の両方。post-hoc の仮説 H14 として記録する。
9. **Stage B の時間**: 1 kernel の timeout を 9000 s にする（Stage A 約 10〜15 分 + Stage B 約 15〜30 分の見込み、未測定）。
10. **Stage B で bridge の表を作らない**: 窓平均の tangent の値は解釈せず、有限性と、host の再計算が kernel の summary と相対 1e-9 で一致することだけを検証する。

## レビュー反映（freeze 前）
- Review A（数学・AD）PASS-WITH-FINDINGS: 線形化・ガウジの射影・`aux_solve!`・primal の bytes は正しい。反映: `DualStop` の停止判定も活性集合の平均を除いた tangent 残差に統一。fixture の残差の検証は `dA x` の項に感度があることを示す（`dA x` が tangent 残差の約 137 倍）。
  fixture の検証 (4) は hook そのものを primal を緩く解いた系（1 cycle で primal 停止）で呼ぶ。補助の値だけの演算子が生きた Dual の演算子と一致することを smoke・各 arm の終わりで検査（不一致は例外 = INCONCLUSIVE）。
- Review B（独立性・GPU）PASS-WITH-FINDINGS: Stage B が打ち切られた・失敗した場合に科学的な verdict が出ないようにした（トップレベルの `verdict` は全工程が COMPLETE のときだけ。Stage B 中の status は `RUNNING_STAGE_B`。analyzer は status ≠ COMPLETE を integrity failure とし、Stage B の結果がなければ INCONCLUSIVE）。
  smoke を強化（非有限は `count` で検査、固定回数の継続が 2 cycle 走ったこと、threshold 継続で tangent 残差が減ること）。Stage B に 20000 step の上限、400 step ごとの履歴の保存、進捗の記録。analyzer は freeze 済みの自分自身の SHA を検査。
  descriptive: τ ごとの「cycle の上限に達した projection の割合」と「達成した残差の中央値」を報告（規則は変えない。τ=1e-6/1e-7 は Float32 の値だけの系で上限 64 に達しうる。plateau の arm が同じ実効精度なら証拠は弱い）。

## Poisson の意味（WaterLily 1.8.0 のソースから）
- 系は `A(L) x = z`（Neumann）。`L = μ₀`（面の係数）、`D`・`iD` は `L` から作る。`b.x` は `flow.p`、`b.z` は `flow.σ`。
- ForwardDiff の下で、保存される残差は `r = z − A x`、その tangent は `δr = δz − δA x − A δx`。
- `solver!` は残差の L₂ の**値**が `tol=1e-4` 未満になったら止まる（`itmx=32`、`ω` の適応）。tangent は反復写像の微分として、primal と同じ反復回数だけ進む。
- 継続（A1）: primal の `solver!` はそのまま。その後 `δr`（`residual!` で再計算した Dual の残差の tangent）を RHS にして、**値だけの**多重格子（同じ V-cycle・同じ smoother・同じ `ω` の適応）で `A e = δr` を解き、`x` の**tangent だけ**に `e` を足す（`dx ← dx + e`）。`x` の値は書かない。
  これは、primal の反復解 `x_n` が正しいとみなして `A δx = δz − δA x_n` を解く反復改良であり、`x_n ≈ x*` なら収束解の導関数に一致する。
- 補助の値だけの系は `L` の値を複写して作る（同じ演算子）。`measure!` が毎 step `L` を再計算するが、Candidate C の幾何は時間不変（値は bit 同一）。

## 構成（1 つの kernel、D0 のみ）
1. smoke（production の経路で 2 step。tangent-only の arm が primal を変えないことと有限性を確認。失敗すれば長い再生の前に停止）。
2. **S（straight）**: plain の `sim_step!` を step 0 から 980 まで再生。毎 step の checksum（全 bit と値のみ）。step 780 の状態を host にコピー。step 800, 820, …, 980 の u・p の値と力（`sample_row`）を drift の基準として保存。
3. **arm**（fork から 200 step、新しい simulation に状態を復元）:
   - `A0_baseline`: 元の primal 停止規則のみ。S と bit 一致（全 bit）が gate。
   - `A1_tau_{1e-4,1e-5,1e-6,1e-7}`（主）: tangent-only 継続、停止は `max|δr| ≤ τ·max|δz|`、最大 64 cycle。
   - `A1_n{01,02,04,08,12,16,20,24,28,32,40,48,56,64}`（地図）: 固定 cycle 数の tangent-only 継続。primal は常に元の規則。
   - `D_tau_{1e-4,…,1e-7}`（副。primal も変わる）: primal と tangent の両方の残差が小さくなるまで Dual 反復を続ける（最大 64）。
   - `F32_forced_dual_32`: DIAG2 の V1c（primal も変わる）。primal の変化量を測る。
4. 各 arm の観測: 毎 step、全体と corner の箱の max|tangent u|、primal の max|u|、非有限数、各 u stage 後の箱の max、Poisson の反復数・RHS・残差、tangent-only の cycle 数・残差（前後、活性集合の平均除去後）・除いた平均、全 bit と値のみの checksum。drift の基準 step で `rel_l2(u)`, `rel_l2(p)`, 力の相対差。

## 判定規則（固定）
- 成長率: `[880, 980]` の `log10(max|tangent u|)` の最小二乗の傾き（全体と corner の箱の両方）。
- **suppresses** = 非有限なし、かつ 全体の傾き ≤ 0.005 **かつ** 箱の傾き ≤ 0.005 **かつ** 980 step の全体の max ≤ 2 × floor。**reduces** = 両方の傾き ≤ 0.5 × baseline の傾き（suppresses を除く）。それ以外 no_effect。非有限で止まれば diverged。これらは診断の gate であり、gradient の qualification の閾値ではない。
- primal identity: 各 arm の値のみの checksum が S と全 step で一致（A0 は全 bit も）。A1 の arm が不一致なら、その arm は plateau・選択から除く。
- **plateau** = 同じ family（threshold または count）の順序（緩い→厳しい）で、identity PASS かつ suppresses の設定が**連続して 3 つ以上**。
- **TANGENT_ONLY_CAUSAL_SUPPORT** = baseline の傾き ≥ 0.05（成長が再現）、A0 が S と bit 一致で 200 step 完走、plateau が threshold か count のどちらかに存在、例外なし、host の検証 PASS。
  **TANGENT_ONLY_NO_SUPPORT** = 上の前提が満たされ plateau がない（孤立した suppresses を含む）。**DIAG3_NOT_REPRODUCED** = baseline の傾き < 0.05。**DIAG3_INCONCLUSIVE** = 例外、A0 の不一致、smoke の失敗など。
- **選択（機械的）**: TANGENT_ONLY_CAUSAL_SUPPORT のとき、threshold family の中で「identity PASS・suppresses・plateau に属し・緩い隣も suppresses」を満たす arm のうち、平均 tangent cycle 数が最小のもの（同率なら τ が小さいほう）。なければ Stage B は走らせない。結果を見て候補を手で差し替えない。
- **Stage B**（選ばれた候補のみ、同じ kernel の次の段階）: 新しい D0 を step 0 から `sim_time ≥ 120 tU/L` まで（G2 の測定と同じ、8 step ごとの `sample_row`）。
  **DIAG3_LONG_HORIZON_STABLE** = 窓まで完走、全 step で primal・tangent が有限、sample の失敗なし、全 step で corner の箱の max|tangent u| ≤ 1e3 かつ全体の max ≤ 1e6、host の再計算が kernel の summary と 1e-9 で一致、窓平均の primal が G2 の plain と相対 1e-3 以内。それ以外は DIAG3_LONG_HORIZON_NOT_STABLE。
- **次の提案（機械的）**: STABLE → G2 bridge の再試行を別作業として提案（登録が必要）。CAUSAL_SUPPORT だが NOT_STABLE、または NO_SUPPORT → Poisson / 線形化 solver の意味をさらに掘る。それ以外 → ユーザー判断。**提案であり、実行は次のユーザー判断。**

## 解析（実行前に凍結、1 回だけ実行）
host の terminal 検証（manifest の SHA、DONE/ERROR の排他、source・pin・入力 hash・runtime source hash・flag false・dryrun false・登録した fork/end/slope 区間・arm の一覧）が PASS した出力に対して `scripts/analyze_grad_g2_diag3.py` を **1 回**だけ実行する。結果を見て規則・閾値を変えて再実行しない。

## 禁止（今回やらないこと）
Float64 Dual / D1・D2・P1 / bridge の表・FD-08 の ĝ との比較 / δ の選択 / GRAD-03 verdict / reverse の修復 / Candidate C の変更 / production backend の選択 / flag の変更 / 結果を見た後の閾値・候補の差し替え。corner の詳細な内部分解（BDIM・面・角）は保留。

## retry 規則
provider の一時障害で、意味のある観測が 1 件も出ておらず、source・登録・kernel の同一性が不変なら retry 可。
**instrumentation / source の不具合**（診断コードの bug、例: GPU でのコンパイル失敗、smoke の失敗）は attempt を保存し、source を変えるなら同じ freeze を上書きせず**新しい identity で最大 1 回**直す。
科学的な結果（NO_SUPPORT・NOT_REPRODUCED・NOT_STABLE を含む）は retry しない。

## 結果の意味（限定）
tangent-only 継続が primal の bytes を保ったまま成長を消すなら、「長い horizon の forward AD の失敗は、primal の流れや Candidate C の幾何ではなく、**打ち切られた Poisson 反復の微分**（tangent の解が未収束であること、および反復写像の微分に入る前処理の微分 × primal 残差の項を含む）に起因する」という強い証拠になる。継続は `dx_n` 全体を置き換えるので、この 2 つはここでは分離できない。
ただし、厳密な導関数・格子独立性・物理的な真値・任意の方向・production の勾配は主張しない。継続が目標にするのは「primal の反復解を正しいとみなした `A δx = δz − δA x_n` の解」であり、FD-08 の観測量（打ち切り Poisson を含む軌道）の有限差分と一致することを保証しない（その差は次の bridge で初めて測る）。
