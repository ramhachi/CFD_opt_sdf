# #46 Stage 1.5 実施記録

証拠区分: `solver_free_numeric_contract_design_unregistered`。integration 起点 `5e67022374335aebe5eb7aba5c4c41f90f708628`。R6/formal 未登録、solver/Kaggle 未実行。qualification flags: fd_oracle / field_gradient / reverse / optimizer / topology / shape_update_allowed = false。

## 数値セクション終了と停止条件監査（設計セクション開始前）

比較規則、コード、params、scenario source、seed、runtime を出力がない状態で固定した。freeze SHA-256 `cd00beccc6a115baf34c6ed97e98fd206f1a11850c5ed23217dacf2e1eda4226`。freeze が記録する時刻と source hashes は `comparison_rule_freeze.json`。実行は `validation/numeric_execution.log`、判定は `unseen_seed_validation.json`。

未使用 seed 46 系列 + historical20、primary / unchanged blind / N1 / N2 / N3 と Decimal80/120 の参照を比較。C5 超過0、availability・符号・6項目・holdout・verdict 差0、precision違反0、曖昧margin0。停止(a)本質的な判定アルゴリズム差=false、(b)未見seedで説明不能な規則超過=false、(c)候補間の判定差=false。この監査後にのみ B-3〜B-7 等の設計を開始した。

- **historical Stage 1 strict numeric condition: unmet 17**。旧の5600比較/17不一致、580判定比較/0不一致を保持。旧params・primary・blind・comparator・入力・出力を編集していない。
- **root cause: explained**。同じmm fitの勾配をmmのまま差し引くか、表示N/mへ丸め換算してから差し引くかで、近ゼロの比に丸め差が現れる。高精度参照に対する主量・判定の差はC5条件内。旧17に新規則を適用した帰結は17/17が条件付きenvelope内だが、旧のpure-relative条件は未達のまま。
- **将来の canonical arithmetic 推奨: N1**。無次元量をfit単位で形成し、表示時にのみ換算。SI/N3で旧結果へ合わせない。N3のproduction選択はladder決定後。
- **将来の独立比較規則の推奨: C5 + C4**。C5 forward envelopes、availability/sign/判定一致、閾値margin認証を合わせる。C1〜C3は診断として保存する。未定義bound・曖昧marginはUNRESOLVED。C5係数は数学的な後退誤差仮定であり、LAPACKの保証ではない。

高精度参照の作者はprimaryを読んでいる。第三の独立実装とは呼ばない。独立レビュー担当2名にはprompt/specだけを渡し、primaryの結論を与えていない。数値レビューは実行前に誤差式の欠落を指摘し、fixtureを評価する前に修正した。凍結後のパラメータ・規則・シナリオ調整0。

## Decision packet とレビューの帰結

推奨 RCFG-1 は N1、C5+C4、one-pass pilotWLS/A主B対照、公称cov非scale、T2の8 provisional値、COV-A全登録4方向×両response、D0/D1/D2維持+P1局在ローブ、6点 .5–5mm、jitterなし、別formal内部3点。R6候補49states、formal baseline1込み25states。20%込み6391.56/10742.76 s（solver/kernel）、formal3261/5481 s。提案capは6600/11200、formal3300/5600。57statesのjitter代案は20%込み7435.08/12496.68で現両上限が不足する。

scientific reviewerはformal1内部点の低費用案とsurface-chart bumpを提示した。親は3点と既存grid上のC²ローブを推奨する。費用/内挿samplingと実装のtradeoffとしてdecision表に残す。T2はδに基づくaccuracy/physicsのqualificationではない。B-3〜B-7、予算、ladderは未承認。

canonical NPZとFloat32 Fortran phi hashesは別々に照合。解析lobe式の一時的active-node値だけで、D0/D1/D2相関を測定した。新full-grid/Float32direction、hash、signedstatesを作らない。実active107415、保護方向support8339と旧4718を混同せず、実changednode監査は未実施とした。

focused39passed、compileall/py_compile成功、full1530tests:37failed/1484passed/9skipped、保存済みfailureIDとの新規0/解消0。37failureの原因修正は今回のscopeではない。JUnit原本とfull logをgzipで保存し、raw SHAも保持。既存変更0、旧Stage1 manifest/source/paramsを再検証する。既存37があるので「fullpytest成功」とは記述しない。

**停止点: R6/formal登録前。** solver/WaterLily/Kaggle/fresh33未実行、#23scope/direction登録/criteria変更0、phase_plan変更0、6qualification flags=false。ユーザーが推奨セットを承認した場合だけ、登録前host gatesと新immutable契約を別作業で実装する。
