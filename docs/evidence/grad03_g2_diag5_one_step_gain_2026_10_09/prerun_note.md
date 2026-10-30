# G2-DIAG5 事前登録: 1 step map の gain はどこで作られ、AD の tangent は有限振幅の応答と一致するか（実行前に固定）

DIAG1–4 の結果の上に置く、**最後の局所診断を 1 回だけ**。長期 trajectory ではなく、保存した T4 の状態に対する 1 step map `F` の線形化の gain を見る。
δ 未決、GRAD-03 verdict なし、reverse 未着手、6 flag false、Float64 なし、D1/D2/P1 なし、bridge・FD-08 ĝ の比較なし、tangent の clip・reset・sanitize なし。
次の判断は結果を見たユーザーが行う（推測で次へ進まない。8740 step の bridge は自動では走らせない）。

## 1. 問い
corner の tangent mode（x-min/y-min/z-max の遠方場の角、箱 `i 1..12, j 1..8, k 49..56`）は 1 step で約 ×1.3 に増える（DIAG1 追補: BDIM ×2.26、project1 ×0.58、BDIM ×2.80、scale ×0.5、project2 ×0.71）。次の 5 つを因果の順に分ける。
- E1 どこで gain が生まれるか（stage と項。conv_diff の対流・粘性、境界 slice、BDIM の項）
- E2 selector の kink（`quick` の枝の境目）はそこにあるか
- E3 1 step の JVP は有限振幅の中心差分と一致するか
- E4 導関数の convention だけを変えると gain が消えるか
- E5 本物の有限摂動も成長するか
- E6 primal の丸め（±1 ulp）で tangent はどれだけ変わるか（報告のみ。分類には使わない）

## 2. 実行環境と状態
- **CPU（Mac、Float32、Dual 幅 1、`julia -t 1`）。T4 は使わない**。保存した T4 の状態を CPU で 1 step map として再評価する（evidence class: `cpu_reevaluation_of_stored_t4_states`）。
  E0（CPU の 1 step を保存した次 step と比べる harness 検証）が下の gate を満たさないときだけ、同じコードを T4 kernel で 1 回走らせる（その場合は新しい pre-registration の追補を書く）。
- 状態（DIAG1 の B0 trajectory、git 外 `/Users/sota/kg_diag1/out1/grad_g2_diag1/snapshots/`。SHA は git 内の `snapshot_index.json` に固定し、job が検証する）:
  `S900`（step 900 の u, p）、`S1000`（step 1000 の u, p）、E0 のための `R1188 → R1189`（ring）。Δt は checksum CSV の bit から。step 780–850 の保存状態は存在しない。onset の瞬間は見ない。
- **persistent state の定義**（WaterLily 1.8.0 のコードから）: `F` の入力は `x = (u（ghost cell を含む）, p)`。`p` は scratch ではない: `mom_project!` は `b.x .*= dt  # ... solution IC` で前 step の `p` を Poisson の初期値に使い、
  Poisson は primal の残差だけで停止する（既定 `tol=1e-4`、最低 1 反復）ので、`p` は次 step の出力に効く。`u⁰`, `f`, `σ`, `μ₀`, `μ₁`, `V` は step の頭で作り直され、`Δt[end] = CFL(u)` は u から決まる（`sim_step!` が最後に `push!(a.Δt, CFL(a))`）。
  したがって有限摂動は `x± = (u ± ε t_u, p ± ε t_p)`、`Δt[end] = CFL(u±)`。E0 で `CFL(保存した u)` が保存した Δt の値と tangent に一致することを検証する。
- **方向の規格化（固定）**: `t = (δu, δp) / max|δu|`（interior、全成分）。`‖ε t_u‖∞ = ε`。AD の入力は同じ `t`（E3 だけは Float32 に丸めた後の実効方向 `(x⁺−x⁻)/(2ε)` を使う）。
  - 変種 A（主）: 保存した `(δu, δp)`。AD 自身の trajectory の tangent なので、solver が実際に保持する状態の組。ghost も保存された値（`BC!` を再適用しても ghost は 1 ulp しか変わらない: E0 で記録）。
  - 変種 B（対照）: `p` を摂動しない。
  - 変種 C（対照）: 速度の方向を solver 自身の演算子（`div`、`L = μ₀`、face gradient、tol 1e-7）で離散 solenoidal 部分空間へ射影し、再規格化。tangent の相対 divergence rms（step 100 の dry-run: 2.3e-2、primal は 5e-6）が示す off-manifold 成分の影響を見る。
  C は分類に使わず、報告する。

## 3. 実験
- **E0（R1188 → R1189、faithful な geometry seed を同じ 2^-117 でスケール）**: gate = dt の tangent の相対差 ≤ 1e-4（入力・出力）、primal u の相対 L2 ≤ 1e-5、primal p の相対 L2 ≤ 1e-3。corner tangent の一致は gate にしない（丸めに敏感なため。報告する）。
- **E1（各 state、homogeneous = geometry seed 0）**: 入力 = 全体 / box だけ / box の外だけ。DIAG1 の stage 列（28 stage のうち tangent を持つもの）の max・L2・box L2・最大点。conv_diff（予測・修正）を role（advecting velocity / advected field / viscous）× (i,j) × region（内部 / 境界 slice）に分解し、
  total との閉じ（closure）を記録する。BDIM の項（`u⁰`, `dt·δf`, `δdt·f`, 現在の u の tangent）。導関数 convention は baseline と tie1e-5。
- **E2（各 state、値のみ）**: 内部の `quick` 呼び出しの枝の個数（id 1・2・3・5。id 4 =「内側の median が c を返し、外側がそれを選ぶ」は WaterLily の `median` の同値処理により構造上起きない）と kink 距離（候補の最小の間隔）、距離 < {1e-6, 1e-5, 1e-4} の割合、`19ε` より近い flip-prone の割合。
- **E3（各 state）**: `ε ∈ {1e-6, 1e-5, 1e-4, 1e-3, 1e-2}`。x⁺, x⁻ を 1 step 進めた中心差分（**有限差分側も Dual 型・tangent 0 の simulation で進める**: plain Float32 は `quick`・`div`・`μddn` の `@fastmath` により丸めが Dual と異なる別の map になる。step 100 で quick 呼び出しの 44%、1 step 後の u の 1.23M/1.89M 要素が違った）と、AD の JVP（baseline = 現行の枝固定の導関数、tie1e-5、tie1e-4、linear）を box と interior で比較（相対 L2、cos、ノルム比、box の max 比の gain）。
  枝の flip: 第 1・第 2 の conv_diff で x⁺, x⁻ の枝が x₀ と違う flux の割合（box と全体）。不一致エネルギーが flip を含む cell（1 と 2 cell 膨張）にある割合と、その cell の割合（enrichment = 割合の比。記述的な報告のみ）。primal のビットは全 variant で同一でなければならない（gate）。
- **E4（上の導関数 variant）**: `QuickTie(τ)`: **値は元の `quick` そのまま**（呼び出しており、bit 同一）、partials は選ばれた値から `τ`（1e-5, 1e-4）以内にある全候補の partials の平均（内側の median、外側の median の順）。`QuickLinear`: 制限なしの QUICK 候補の partials（対照）。
  baseline は ForwardDiff が primal の値の比較で選んだ枝の導関数（= frozen branch）で、これが対照。**これは surrogate / generalized design derivative であり、実装した map の導関数ではない**。
- **E5（各 state、K = 40 step）**: AD baseline・tie1e-5・tie1e-4・linear と変種 C の方向の AD。有限振幅: 各 ε ∈ {1e-5, 1e-4, 1e-3, 1e-2} の変種 A、ε ∈ {1e-4, 1e-3} で変種 B と C。`D_k = (x⁺_k − x⁻_k)/(2ε)` の box の L2 の成長率（decade/step）を、
  線形領域（`ε·max_box|D_j| ≤ 0.1` が成り立つ最後の step まで）で AD の tangent と比べる。**step instrumented の AD（baseline）は最初の 3 step で `sim_step!` と値・tangent が bit 同一**でなければならない（gate）。全 variant の primal の checksum は全 step で同一でなければならない（gate）。
- **E6（各 state）**: primal の u（ghost 含む）の全要素に独立に ±1 ulp（seed 1..16）を加え、1 step の AD の corner tangent の pattern の相対変化と gain、および ε = 1e-3 の有限差分の変化。

## 4. 登録した判定（結果を見る前に固定。独立レビューの指摘を反映した版）
各 state を分類し、**両 state が同じ label のときだけ**それを最終とする（食い違えば R4）。優先順は R2 > R3 > R1 > R4。mechanical gate が破れれば `DIAG5_INCOMPLETE`（その場合は分類を書かない）。
- 一致の定義（corner box、baseline）: 相対 L2 ≤ 0.10 かつ cos ≥ 0.99 かつノルム比 ∈ [0.95, 1.05]。
- smooth の振幅: `1e-5 ≤ ε ≤ 1e-3` で box の flip 率（予測・修正の大きい方）< 0.01 の ε（ε = 1e-6 は Float32 の差分の丸め誤差が大きく、ε = 1e-2 は map 自身の有限振幅の非線形性があるので、判定に使わない）。そのような ε が無ければ R2 は判定不能（`r2_testable = false`）で、R2 にはならない。
- **R2_LINEARISATION_DEFECT**: smooth の振幅のどれかで baseline が一致しない。→ 「線形化の欠陥が候補」であって、確定ではない（E1 の項の分解で局所化する）。大振幅（ε = 1e-2）の非線形性だけでは R2 にならない（ε = 1e-2 は分類に使わない）。
- **R3_FINITE_INSTABILITY**: ε ∈ {1e-5, 1e-4, 1e-3} の全て（欠けていれば不成立）で baseline が一致し、かつ ε ∈ {1e-4, 1e-3} で（有限差分の成長率 / AD の成長率）∈ [0.7, 1.3]。**AD の成長率は ≥ +0.02 decade/step が必要**（減衰・平坦な AD は R3 にも R1 にもならない）。
  言い方: 「観測された不安定な tangent mode は、試した近傍における実装された離散 map の genuine な有限摂動の不安定性である」。**「smooth な map が不安定」とは言わない**（limiter があるため）。
- **R1_SELECTOR_CONVENTION**（次の 5 条件が全て必要）:
  (1) ε = 1e-3 で baseline が一致しない、
  (2) ε ≤ 1e-3 の 4 点で baseline の不一致（相対 L2）と box の flip 率の Spearman 順位相関 ≥ 0.8（不一致が flip 率とともに増える）、
  (3) ε = 1e-3 で tie1e-5 か tie1e-4 の一方が不一致（相対 L2）を ≥ 50% 減らし、かつ**一致の定義を満たし**、gain が有限差分の gain の ±20% に入る、
  (4) ε = 1e-3 の有限差分の成長率 ≤ 0.5 × AD の成長率（AD は ≥ +0.02）、
  (5) その surrogate の AD の成長率が有限差分の成長率に `max(0.3 × |rate|, 0.02)` 以内で一致する。
  言い方: 「不安定性は selector の導関数の convention に敏感である」。surrogate は実装した map の導関数ではない。AD の bug とも gradient の qualification とも言わない。
  （事前版にあった「flip を含む cell への不一致エネルギーの集中（enrichment）」と「E6 の ulp 感度」は、flip cell が box をほぼ覆い飽和するため・OR で条件を無効化するため、分類から外した。記述的に報告する。）
- **R4_INCONCLUSIVE** = 上のどれでもない。**意味の限定: current long-window forward-AD qualification program の bounded No-Go であり、full-field AD という方法一般が不可能という主張ではない**。
  言い方: 「事前に定めた診断の予算では qualified な導関数の解釈を特定できず、gradient の correctness を主張せずに現在の long-horizon AD の経路を終了した」。
- gate（全て必要）: 全 state の `Δt[end] = CFL(u)` が保存した Δt に一致（value 相対 1e-6、tangent 相対 1e-4）、E0（dt の tangent の相対差 ≤ 1e-4、primal u の相対 L2 ≤ 1e-5、primal p の相対 L2 ≤ 1e-3）、instrumented step が `sim_step!` と bit 同一、E3・E3C の全 variant で primal の checksum が同一（キーは文字列から数値に parse して照合）、E5AD の全 variant が全 step で primal 同一、
  E3/E3C は ε × variant × region の 40 行が過不足なく存在し全て有限、E5FD が登録した variant と 41 行、E6 が n = 16 で全て有限、status（dryrun false、k = 40、threads = 1、flag 全 false、runtime source hash）、凍結した analyzer の SHA、pin。
- 継続（R1/R2）の場合も DIAG5 は verdict を持たない。継続には別の事前登録が要る: 導関数の規則が primal を変えないこと、1 step の FD で独立に検証されること、短窓の FD-08 ĝ との関係（これは GRAD-03 の仕事）。
- reverse AD について: `‖Jᵀ‖ = ‖J‖` なので forward で大きな gain を持つ写像を reverse にするだけでは良条件にならない。ただし objective の adjoint がその singular subspace をどれだけ励起するかは別問題で、forward の D0 tangent の爆発から reverse が必ず爆発するとは言えない。DIAG5 は reverse について何も主張しない。

## 5. 実行と記録
`scripts/run_grad_g2_diag5_local.py`（21 process = R1188/E0 + 2 状態 × 10 group、`julia -t 1`、並列度 ≤ 8）。pin（job・stages・Julia project/manifest・`julia/CFDSDFWaterLily/src` の tree hash・snapshot index・checksum CSV の SHA、source commit が HEAD の祖先であること、tracked file が clean であること）を実行前に検証し、不一致・非 0 終了・欠落があれば ERROR.txt（DONE なし）。
解析器 `scripts/analyze_grad_g2_diag5.py` は、`--check` で gate だけを（何も書かず・分類せず）確認でき、本実行は 1 回だけ（`open("x")`）、結果を `diag5_analysis.json` に書く。生の CSV・JSON は git に入れる（小さい）。

## 6. 事前の探索と dry-run の開示（freeze の `pre_freeze_disclosures` と同じ）
1. 保存した step 500 と 900 の u の numpy による枝の監査（x 方向のみ、advecting velocity を face の平均で近似）: corner box の limiter 呼び出しの約 79% が制限なしの QUICK 候補、19% が中央値 c、2% が制限された枝。候補の値の間隔の中央値 4.5e-6（box の速度の標準偏差 2e-5）。
2. CPU の試作: 保存した step 1188 から 1 step 進めた結果と保存した 1189 の比較。dt の tangent は 8e-7 で再現、primal u の相対 L2 3.6e-6、corner の tangent の gain は CPU 1.12 に対して T4 の保存値 1.33（pattern の相対 L2 差 0.47）。
   primal の全要素に ±1 ulp を加えると corner tangent の pattern は 0.1% の cell で 1.7e-5、10% で 0.046、100% で 0.24 変わり、gain は 0〜2.5% 変わる。**CPU と T4 の 1 step の tangent が一致しないこと自体が、tangent が primal の丸めに敏感であることを示している**。
3. 全 group を step 100 の保存状態（登録外）で K=3、ensemble 2 の dry-run（コード経路の確認）。E2 を step 100 で見ると corner box の limiter 呼び出しの 74% が既に kink 距離 < 1e-5。stored tangent の相対 divergence は 2.3e-2（primal は 5e-6）。
4. E0 は登録した状態そのもので dry-run 済み（登録時の実行と同じ設定）。
5. 独立レビュー（job）の指摘で、plain Float32 の simulation は Dual の simulation と別の丸めの map であることが分かった（上記）。これを受けて有限差分側を全て Dual 型 zero-tangent に変更し、枝の audit を WaterLily の `median` の operand 選択の複製に直し、`CFL(u)` と保存した Δt の一致（value 1e-6、tangent 1e-4）を全 state の gate に加えた。
登録した S900 / S1000 の E1–E6 の結果は freeze の時点で誰も見ていない。

## 7. 禁止
Float64 の simulation、D1/D2/P1、bridge の表と FD-08 ĝ との比較、δ の選択、GRAD-03 verdict、flag の変更、reverse、tangent の clip・reset・sanitize、結果を見た後の状態・ε・閾値・variant の追加、8740 step の bridge の自動実行、
R4 を「AD は不可能」と書くこと、R1 の surrogate を「正しい導関数」と呼ぶこと。
