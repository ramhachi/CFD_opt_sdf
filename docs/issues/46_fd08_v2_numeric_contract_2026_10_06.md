# #46 FD-08 v2 Stage 1.5 数値計算契約（提案・未承認）

証拠区分 `solver_free_numeric_contract_design_unregistered`。R6/formal未登録、solver/Kaggle未実行。基点はintegration `5e67022374335aebe5eb7aba5c4c41f90f708628`。[固定仕様](../evidence/fd08_v2_stage1p5_2026_10_06/numeric_contract.md)、[実行前freeze](../evidence/fd08_v2_stage1p5_2026_10_06/comparison_rule_freeze.json)、[停止監査](../evidence/fd08_v2_stage1p5_2026_10_06/unseen_seed_validation.json)を正本とする。freeze SHA `cd00beccc6a115baf34c6ed97e98fd206f1a11850c5ed23217dacf2e1eda4226`。

## 結論を4つに分ける

1. **historical Stage 1 strict numeric condition: unmet 17**。旧C1の5600比較のうち17未達、5583内、判定580比較の不一致0、20/20 verdict一致を維持。旧source/params/comparator/evidenceは変更0。
2. **root cause: explained**。mm fitの同じ勾配をmmのまま差し引く経路と、表示N/mへ丸め換算した後の経路の違いが近ゼロの相対差に出る。主量/fit/判定に影響する本質的アルゴリズム差は、今回の参照検証で見つからなかった。旧診断と新C5からの帰結で説明できるが、旧strict conditionをPASSにしない。
3. **将来のcanonical arithmetic推奨: N1**。fitはmm、無次元量は同じfit単位で形成し、g/SE表示時だけN/mへ換算する。結果に合わせてSIへ変更しない。
4. **将来の独立比較規則推奨: C5+C4**。被演算子/fitからの条件付きforward errorとsemantic/閾値margin認証を併用する。未定義bound・曖昧marginはUNRESOLVED、判定差はstop。これは新規則であり旧C1の修正ではない。

## 算術と参照の定義

N1はX_A=[εmm,εmm³]、X_B=[εmm,εmm|εmm|]。N2はεm=εmm/1000、Aの列はdiag(1e−3,1e−9)、Bはdiag(1e−3,1e−6)。係数・共分散はそれぞれ逆対角変換を持ち、報告時にcanonical mmへ戻す。N3はx=εmm/εref、εref=max(full ladder)、全subsetで同じrefを維持する。N3はconditioning比較のみで、ladder未決のproduction選択ではない。

Decimal80を数学参照とし、Decimal120を独立precision実行で比較した。入力・paramsは保存済みbinary64のexact conversion。OLS pilot→一回WLS、公称逆Gram共分散、全subset/holdoutと閾値をDecimalのまま計算する。80/120比較はfloat変換前で、raw reference decimal stringsを圧縮結果に保存した。参照の作者はprimaryを読んでおり、**第三の独立実装ではない**。既存blindは変更せず新fixtureにも再実行した。

## 事前比較規則と帰結

C5はu=2^-53、γ_k=k u/(1−k u)、k(n)=8n+32、Gram/solve/inverseの明示的後退摂動、pilot→variance→√weight→WLS→coef/cov→SE/prediction/ratio/marginの伝播を固定した。これはLAPACK/SVDのcertified boundではなく、[独立数値レビュー](../evidence/fd08_v2_stage1p5_2026_10_06/independent_numerical_review.md)が前提を限定したengineering envelope。規則は出力を評価する前に完成・hash固定し、凍結後の調整0。

比r=|a−b|/|b|は参照被演算子の誤差Ea/Ebを使い、D=|b|−Eb>0、t=|a−b|として

`Br=(Ea+Eb)/D + t*Eb/(|b|D) + γ3*(|a|+Ea+|b|+Eb)/D`。

係数Cを17から逆算せず、fit conditioningと被演算子のboundから導く。exact/近ゼロ比は最終rのULPが極小で、最後の値のpure relative/ULPは丸め誤差の尺度として不適合。実対象のnested shiftが1e−3を大きく超えるという提示事実に対し、今回の特異な近ゼロはノイズなし合成fixtureの構造による。これは対象データを再評価した所見ではない。

| 規則 | 定義・役割 | 66系列の各実装×参照での帰結 |
| --- | --- | --- |
| C1 | rtol1e−9、atol0。診断 | 各実装20250比較中128未達。主に近ゼロの曲率/派生量/holdout残差。旧の5600/17とは比較対象が異なる |
| C2 | C1 + γ_k×次元に沿う入力尺度。診断 | 全実装で未達0。atolは17由来ではない |
| C3 | binary64最終値のbit距離、8ULP allowance。診断 | primary/blind/N1/N2/N3の未達1487/1492/1487/1901/1612。近ゼロ値では被演算子の丸めを表さない |
| C4 | availability/finite、符号、6項目・holdout閾値側、verdict、margin | 不一致0、誤差区間で曖昧なmargin0 |
| C5 | 条件付きfit/被演算子forward envelopes | 各実装20250比較、計101250で超過0・bound未定義0。C5を普遍誤差定理とは呼ばない |

旧17の新C5+両出力12有効桁serialization allowance下での帰結は17/17 envelope内。[arithmetic_comparison.json](../evidence/fd08_v2_stage1p5_2026_10_06/arithmetic_comparison.json)は旧差をそのまま保持し、`historical_strict_status=unmet_preserved`と別fieldにする。

## 未使用seed・条件数・forward error

seed=46150000+1000*scenario_number+ladder_count、PCG64。Stage1のscenario定義を変更せず、20scenario×6/8点=40系列と、6scenario×15mm上端7点=6系列。具体seed、旧seed集合との重複0、NumPy2.5.2/Python3.12.13、12有効桁保存/同一parsed input、draw順序、generator/source/params hashesをfreezeした。未使用46を先に、historical20を後に処理した。新seed35PASS/11FAIL、historical18PASS/2FAIL、全66は53PASS/13FAIL/0UNRESOLVEDで全実装一致。これは合成判定でCFDのqualificationではない。

全full/subset/holdoutのcond2(X)/cond2(Xw)、norm2、conversion、g/SE/β/cov/pilot/weights/nested/model/holdoutのforward errorを保存した。

| implementation | 最大design cond2 | 最大weighted cond2 | full A/Bの最大g誤差 N/m | full A/B最大SE誤差 N/m | 最大error/bound（全数値） |
| --- | ---: | ---: | ---: | ---: | ---: |
| primary / blind / N1 | 626.1028 | 96.58512 | 1.4567e−16 | 6.5956e−18 | .00392725 |
| N2 SI | 1935008.3 | 1910796.4 | 1.9399e−16 | 5.5196e−18 | .0000876299 |
| N3 scaled | 85.08390 | 86.87472 | 1.6577e−16 | 5.7282e−18 | .00795544 |

primary/blindのdesignはN1と同じである。condは単位に依存し、N2が大きいことは物理的identifiabilityの比較ではない。N3の条件数改善だけで精度・モデルbiasの解決を主張しない。N2の小さいerror/bound比は実装が最良という意味ではなく、その条件付きenvelopeが大きい影響を含む。

80/120 reference最大scaled delta=3.24921436e−78、bound最大scaled delta=1.88588341e−67で事前1e−60条件内。raw precision差はJSONのdecimal stringsに記録。two-precisionの収束は数学式の正しさや厳密interval保証の証明ではない。

停止(a)(b)(c)はすべてfalse。[stage1p5_note](../evidence/fd08_v2_stage1p5_2026_10_06/stage1p5_note.md)に設計開始前の監査を記録した。結果に合わせた規則・tolerance・seed・scenario変更0。6flags=false、phase_plan未変更、R5 force/result/analysis/dataset方向raw未使用。

## 検証・再現

- 実行前freeze: `python scripts/validate_fd08_v2_numeric_contract.py --freeze`（既存freezeの上書き不可）。
- 66fixture実行: 同CLI、freeze/source/runtimeを検証し既存結果の上書きを拒否。再実行は同一commitの新checkout/別出力領域で行う設計であり、保存済みevidenceを削除しない。
- focused: `python -m pytest -q tests/test_fd08_v2_numeric_contract.py tests/test_fd08_v2_gate.py` →39passed。
- compileall src tests/新scriptsのpy_compile →exit0。
- fullpytest →37failed/1484passed/9skipped、1530tests、exit1。保存済み37failure IDsとの差分0。raw JUnit/logをgzipで保持しuncompressed hashesも保存。
- [validation_summary](../evidence/fd08_v2_stage1p5_2026_10_06/validation/validation_summary.json)・[SHA256SUMS](../evidence/fd08_v2_stage1p5_2026_10_06/SHA256SUMS)を参照。Git/source/old evidence hashesはfinal verificationで確認。
