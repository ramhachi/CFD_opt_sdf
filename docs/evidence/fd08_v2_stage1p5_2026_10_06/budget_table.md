# P-1 state・solver/kernel予算（提案・未承認）

現HEADを再検索した位置:
- kernel_limit: `docs/phase_plan.md:6053`
- r5_kernel_limit: `docs/phase_plan.md:6219`
- solver_budget: `docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json:100`

5400 sはaggregate solver上限、10800 sはkernel実行上限で別の制約。B計画のregister_fd08_calibration.py:54は現在BASE_CRITERIA定義であり、上限数値の所在ではない。現registrar:515のbase copyと継承元criteria:100、phase_plan:6053–6054/6219–6220を参照。登録済みコードを変更していない。

固定見積りはsolver108.7 s/state、overhead74.0、elapsed182.7 s/state。旧Stage1 design_tables.mdとユーザー提示のaggregate実績を再利用し、R5 force/result/analysisを読まず計算した。新方向・largeεのruntime保証ではなく、起動/コンパイルの固定費と遅いstateを含むruntime実装が別途必要。

| 案 | states | solver s | elapsed s | solver +20% | elapsed +20% | 現上限+margin |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 4directions_6epsilon_baseline1_jitter0_per_direction | 49 | 5326.30 | 8952.30 | 6391.56 | 10742.76 | solver=不足, kernel=可 |
| 4directions_6epsilon_baseline1_jitter2_per_direction | 57 | 6195.90 | 10413.90 | 7435.08 | 12496.68 | solver=不足, kernel=不足 |
| 4directions_6epsilon_baseline1_jitter4_per_direction | 65 | 7065.50 | 11875.50 | 8478.60 | 14250.60 | solver=不足, kernel=不足 |
| 4directions_8epsilon_baseline1_nojitter | 65 | 7065.50 | 11875.50 | 8478.60 | 14250.60 | solver=不足, kernel=不足 |
| formal_pairs_only | 24 | 2608.80 | 4384.80 | 3130.56 | 5261.76 | solver=可, kernel=可 |
| formal_with_baseline1 | 25 | 2717.50 | 4567.50 | 3261.00 | 5481.00 | solver=可, kernel=可 |
| recommended_total_two_separate_rounds | 74 | 8043.80 | 13519.80 | 9652.56 | 16223.76 | solver=不足, kernel=不足 |

57 statesは6195.9 s /10413.9 s、20%込み7435.08 s /12496.68 sで**両上限不足**。49 statesもsolver marginが不足する。74 statesはcalibration49+formal25の合計であり、単一kernelへ入れる案ではない。別kernelの追加起動固定費はこの比例見積りに完全には表れない。

| Option | 内容 | identity/科学的依存 | 推奨 |
| --- | --- | --- | --- |
| Budget A | 両上限引上げ。49stateなら6600solver/11200kernel、formal25は3300/5600候補 | 見積り20%以上。後の登録が上限を明記し、Kaggleが提供する実行制限を確認 | 第一候補。実行は今回しない |
| Budget B | kernel分割 | partition/subset manifestとaggregate counts/hash検証、同一criteria/source/canonical/direction/solver/tolerance identity。二重solveの扱い、setup固定費、クロスkernelruntimeを結合。単に各kernel5400へリセットしてaggregate超過を隠さない | platformがA不可なら新契約が必要。承認なしで切替しない |
| Budget C | 方向/点/baseline/jitter削減 | 登録済み方向を落とさず、6点/内部holdout/末尾dropを壊さない。8→6は情報tradeoff、baseline5→1はnoise estimatorの変更 | 6点とjitterなしの科学的選択として採用。予算だけの削除をしない |
| Budget D | jitter別round | report-onlyなら後でも可。σ0推定に使うなら独立roundとbias/estimator/CIをR6前に固定し完了しなければならない | 今回の推奨はjitterなし。後付けnoise更新不可 |

推奨Aのcalibration上限6600/11200は現5400/10800からの提案引上げ。formalは別round/別予算。formalの上限はcalibration開始前に承認し、calibrationPASS後だけその事前仕様を登録する。現runner/criteriaの上限はこのメモで変わらない。
