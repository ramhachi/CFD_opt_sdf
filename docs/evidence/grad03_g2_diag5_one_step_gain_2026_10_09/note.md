# G2-DIAG5 結果: 登録した判定は **R4_INCONCLUSIVE**（診断。gradient の qualification ではない）。ただし登録外の記述的観測が強い（下の「post-hoc」）

事前登録（`prerun_freeze.json`、独立レビュー 2 本の指摘を反映済み）どおりに CPU で 1 回実行した（21 process、`julia -t 1`、source `e06e3364`、保存した T4 の状態の再評価）。解析器（freeze に SHA を固定）を 1 回だけ実行（`diag5_analysis.json`）。integrity と全 gate が pass。
δ 未決、GRAD-03 verdict なし、reverse 未着手、6 flag false、Float64 なし、bridge・FD-08 ĝ の比較なし。**R4 の意味: current long-window forward-AD qualification program の bounded No-Go であり、full-field AD という方法一般が不可能という主張ではない。**
生の出力（CSV・JSON）は `run_output/`。

## 登録した判定（機械的）
- 両 state（S900、S1000）とも `R4_INCONCLUSIVE`。
- gate: E0 の closure（dt の tangent 8e-7、primal u 3.8e-6、primal p 1.2e-4）、`Δt[end]=CFL(u)` が全 state で保存値に厳密一致、instrumented step は `sim_step!` と bit 同一、E3/E5AD の全 variant で primal 同一、ghost は `BC!` で厳密に再現、が全て満たされた。
- R2: どの ε でも corner box の flip 率が 3%（ε=1e-6）〜59%（ε=1e-2）あり、smooth の振幅が存在しない（`r2_testable = false`）。R3: baseline の AD は有限差分と全 ε で一致しない。
- R1 が成立しなかった理由（登録した条件のどれか）: (2) 不一致と flip 率の順位相関 ≥ 0.8 → S900 −0.8、S1000 −1.0（不一致は最小の ε=1e-6 で既に O(1) で、flip 率に依存して増えない）。(3) tie1e-5 は不一致を 88–89% 減らし gain も一致したが、相対 L2 が 0.126（S900）、0.157（S1000）で一致の閾値 0.10 に届かない。(4) S1000 では 40 step の AD の成長率が −0.003 で +0.02 に届かない。
  （登録後に基準を動かさない。(2)(4) は設計上の弱点: 最小の振幅でも箱の flip 率が 3% あり、また 40 step 全体の線形回帰は後半の崩れを含む。）

## post-hoc の記述的観測（登録外。解釈は未検証。事前の分類を変えない）
1. **有限振幅の応答は ε を 4 桁変えても一定で、AD の baseline と違う**。corner box での 1 step の gain（最大値の比）: S900 の有限差分は ε=1e-6…1e-2 で 0.53, 0.56, 0.59, 0.59, 0.59（S1000: 0.53, 0.53, 0.55, 0.55, 0.55）、
   AD の baseline は 1.33–1.39（S900）、1.44–1.49（S1000）で、約 2.4 倍。cos は 0.90–0.96、ノルム比は 1.9–2.4。つまり有限差分には安定した「導関数のような量」があり、AD の baseline はそれと一致しない。
2. **tie-averaged の surrogate 導関数は有限差分に合う**: tie1e-5 の 1 step の gain は 0.586（有限差分 0.589、S900）、0.538（0.551、S1000）。ノルム比 1.015 / 1.038、cos 0.992 / 0.989、相対 L2 0.126 / 0.157。unlimited QUICK の導関数（linear）も 0.509 / 0.470 で近い。tie1e-4 は合わない（1.12、窓が広すぎる）。
3. **多 step: 有限摂動は減衰し、AD の baseline だけが増える**。corner box の L2（S900、k = 0, 5, 10, 20）: AD baseline 2.08 → 9.8 → 52 → 1240（20 step で約 0.14 decade/step の成長、その後 k=40 で 131 に崩れる）。
   有限差分（ε=1e-3、変種 A）0.372 → 0.100 → 0.0053 は減衰（約 −0.13 decade/step）。tie1e-5 の AD は 0.298 → 0.045 → 0.0074 で有限差分と同じ減衰。変種 B（p を摂動しない）と C（solenoidal な方向）の有限差分の減衰率は A と同じ（−0.058 / −0.059 / −0.058、S1000）。
   → 試した近傍では「genuine な有限摂動の不安定性（R3）」は観測されない（ε=1e-5…1e-2、変種 A/B/C）。
4. **gain が作られる場所**（E1、S900）: conv_diff の予測・修正の `f` の tangent は入力の 6.7 倍・8.9 倍、BDIM の項では `dt·δf` が支配的（`u⁰` の 2.1 に対し 4.6 と 6.1）。conv_diff の項の分解では **(i=1, j=1)、role = fld（limiter を通る advected field）、interior** が圧倒的（8.9 / 13.6 に対し 2 番目は粘性項の 1.7）。
   advecting velocity の項と境界 slice は小さい。S1000 も同じ（11.4 / 15.7）。つまり gain は x 方向の運動量の対流 flux の limiter の導関数で作られる。
5. **AD の tangent は primal の丸めに敏感**: 全ての primal u に ±1 ulp のノイズ（16 個）を入れると、同じ状態の corner の tangent の pattern は中央値で 59%（S900）/ 65%（S1000）変わり、1 step の gain は 0.52–1.20（baseline 1.39）にばらつく。有限差分（ε=1e-3）の同じ変化は 0.09% / 0.10%。
   CPU の再評価の 1 step の gain（E0、step 1188→1189）は 1.12、T4 の保存値は 1.33。
6. kink の密度（E2、S900 の box の予測 conv_diff）: 4881 flux のうち 74.8% が kink 距離 < 1e-5、40% が < 1e-6、距離の中央値 1.9e-6（枝は A 4159 / c 641 / 10c−9u 75 / d 6）。
7. 参考: stored の tangent の方向の相対 divergence rms は 5.9e-2 / 6.3e-2（primal は 1e-6）。solenoidal に射影すると 8e-5。

## 読み方（post-hoc の仮説。解釈の限定）
- 登録した判定は R4 で、DIAG5 の事前の約束に従えば「現在の long-window forward-AD の qualification の経路は bounded No-Go」。
- 記述的には、R3（実装した離散 map の genuine な有限摂動の不安定性）は支持されず、観測は「ほぼ一様流の corner で limiter の枝が同値に近く（kink 距離の中央値 2e-6）、AD の baseline が選んだ枝の導関数が有限応答と 2.4 倍違い、丸めで揺れる」という selector の導関数の convention への敏感さと整合する。
  tie-averaged の導関数が有限差分の 1 step の gain と多 step の減衰に合うのは、導関数の convention を変えれば不安定が消えることを示唆する。ただし surrogate は**実装した map の導関数ではない**。採用するなら別の gradient contract で、独自の事前登録（FD-08 ĝ との関係、短窓での検証）が必要。DIAG5 はそれを主張しない。
- したがって次の判断は 2 つに分かれる（ユーザーの判断。推測で進めない）: (a) 登録どおり R4 として full-window exact AD を打ち切り #47 STEP-01 と #48 LOWDIM-01 へ pivot する、(b) 上の surrogate を「別の gradient contract」として別の事前登録で調べる（これは DIAG ではなく GRAD の仕事。優先順位は #47・#48 の後でもよい）。
- 有限差分の応答が ε=1e-6…1e-2 で一定で、変種 A/B/C でも変わらないことは、有限差分の oracle と低次元の係数空間の最適化（#47、#48）の根拠を補強する。

## 範囲
診断のみ。bridge の表なし、FD-08 ĝ との比較なし、δ 未決、GRAD-03 verdict なし、reverse 未着手、6 flag false。8740 step の bridge は走らせていない。T4 は使っていない（E0 が gate を満たした）。
