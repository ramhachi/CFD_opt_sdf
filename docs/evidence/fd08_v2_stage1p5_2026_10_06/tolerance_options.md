# B-5 tolerance と B-3 estimator（提案・未承認）

## B-3 の式と不確かさの意味

各full/subset/holdoutの**当該点集合**で無重みOLS pilotを作り、v_i=σ0²+(ρ S_pilot,i)²、w_i=1/v_i。WLSは Σ_i w_i(S_i-X_iβ)² を一回最小化する。NumPyの行スケールは a_i=√w_i=1/√v_i、Xw=diag(a)X、yw=diag(a)S。B計画の1/√表記は行スケールに対応し、目的関数の重みは1/分散である。反復再重み付け、事後χ²scale、応答を見たモデル選択はしない。

主A: S=gε+cε³、対照B: S=gε+kε|ε|（εは正のmm）。C=(X^TWX)^−1 は公称共分散。既知で正しい各観測分散、独立誤差、正しい平均モデルと固定重みの下でこの形の条件付き解釈が成立する。pilotから推定した重みを固定と扱うため、その推定不確かさは公称Cに入らない。ρ/σ0が誤ればSE/holdout標準化を過小・過大評価し、重み依存のgも変わる。決定論的model bias・相関・discretizationはCで除けない。sandwich C(X^TWΩWX)C は誤分散を考える別案であり、少数点・重み推定・model biasを自動解決しない。本作業では変更しない。

[Stage1 simulation_report](../fd08_v2_stage1_2026_10_06/simulation_report.md)を固定事実として再利用する。5mm上端・B真値の曲率比25%では全4条件100%PASS、g相対誤差中央値4.248–4.995%。AのcがBの曲率を吸収でき、モデル差gateはこの誤指定を検出しない。曲率比150/200%では5mmの全条件FAIL、100%はPASS7.4–100%で点数・gに依存する。15mm比較では50%曲率のPASS0.05%/5.70%へ低下するが、25%はなお100%PASSでg bias約9.55–10.13%。上端・点数・下端も異なる比較で、上端だけの因果効果やtarget挙動ではない。A4の対象内0%誤通過はモデル識別が十分という証拠ではない。

## T1: ユーザーがδを指定した場合のみ

[#23](https://github.com/ramhachi/CFD_opt_sdf/issues/23)には数値δがない。Codexはδを作らない。将来δが登録された場合、同じ単位・normalizer・信頼水準で、比較差の誤差を

`E_comparison ≤ E_FD_numeric + E_FD_stat + E_FD_bias + E_gradient + E_mapping`

として接続する。案のFDへのδ/3 allocationは設計上の配分であり定理ではない。SEだけをδ/3と同一視せず、例えばユーザーが選ぶ信頼係数zによるz·SE、モデルbias、realizeddirection誤差、backend誤差へ分割する。点ごとのSE10%/モデル差15%を足してδに見立てない。数値例は置かない。

#23と衝突し得るのは、(1)全登録方向から部分coverageへ縮小、(2)drag/downforce片側だけを選ぶ、(3)固定canonical/directionsを変更、(4)g_field·dのinnerproductとSDF/法線/名目εの尺度を混同、(5)Poisson等solver toleranceを未結合、(6)非有限・符号・登録error gateを相対SE/モデル内挿だけで代替、(7)FD-08 prerequisite未完了を個別方向PASSで満たす、である。T1はこれらを改訂する承認を含まない。

## T2: 暫定paramsを明示的に受け入れる選択肢

すべて既存Stage1指示§2の**arbitrary-provisional**値であり、targetからmeasured/derivedでも、Stage1でsynthetic-calibratedされた数値でもない。合成シミュレーションは選定後の性能測定であり、値の用途上の根拠を後付けしない。

| parameter | 値 | 分類 | 意味・出所 |
| --- | ---: | --- | --- |
| tol_se | 0.10 | arbitrary-provisional | AのSE/|g|≤10%、Stage1指示§2 |
| tol_nested | 0.15 | arbitrary-provisional | 末尾1/2点を除いたAのg相対ずれ各≤15% |
| tol_model | 0.15 | arbitrary-provisional | |g_A-g_B|/|g_A|≤15% |
| tol_hold | 0.15 | arbitrary-provisional | 内部holdout error≤max(3σpred,0.15|Spred|) |
| k_mag | 5 | arbitrary-provisional | |S|≥5σ0の点が4以上。方向g/SEの条件ではない |
| sigma0_n | 3e-6 N | arbitrary-provisional | centered Sの絶対noiseモデル仮定。force Fのσと同一ではない |
| rho | 0.05 | arbitrary-provisional | pilot予測に比例するvariance仮定 |
| nested_drop | 2 | arbitrary-provisional | stability用末尾drop数。signは別に1..3 |

**推奨T2**は、R6をこの条件付きのモデル検証として承認する場合の案。正確なδに裏付けられたoracle精度や物理的資格を意味しない。δ接続を成功条件にしたい場合はT1を選び、δ指定までR6を登録しない。旧paramsのSHA c5f3fe1a3875c44d5fd0b87d48fd0bd0c06bdf22fb74581cb399e382dbac95baを維持する。感度5/10/15/20%の旧結果をreport-onlyで添えるが、観測後に通る水準を選ばない。R6への実装で新hashを固定するのは承認後の別作業。
