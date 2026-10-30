# B-7 formal predict-then-run（第一候補・未承認）

[Stage1設計](../fd08_v2_stage1_2026_10_06/design_note_predict_then_run.md)を具体化する。solver未実行、formal未登録。

calibration全点のOLS pilot→one WLSでAのĝ/ĉ、C、model identity、params、ladder、source/runtime/direction/state hashesを固定する。formal結果からの再fit、χ² scale、model/点の選別、tolerance変更はしない。方向×response全系列を同一の事前規則で比較する。

n点の承認ladder eに対し、index i={0,floor((n−2)/2),n−2}の3intervalを固定し、εformal=sqrt(e_i e_(i+1))。これは端点の内側でcalibrationのどのfitにも使わない。六点案ならi={0,2,4}。将来の実装ではnominalεだけでなく、±Float32 phi byte列がcalibration/他formal/jitterと異なることを登録前に検査する。重複時は登録を停止し、responseを見た別点への置換を許さない。

x=(εmm,εmm³)、Spred=x^T(ĝ,ĉ)、σpred²=σ0²+(ρSpred)²+x^T C x。T2選択時の候補判定は、全点で有限/byte-integrity、非ゼロ同符号、|Spred|/|Sobs|がともに5σ0以上、|Sobs−Spred|≤max(3σpred,tol_hold|Spred|)。有限でerror/sign不合格はFAIL、noise-model magnitude未解決または数値bound/margin未解決はUNRESOLVED。全登録方向×両response×3点がPASSでformalPASS。relativeerror=abs(error)/abs(Spred)（分母0はnull）、標準化error=abs(error)/σpred、符号、absoluteerror[N]を保存。Magnitude/符号のformal条件は今回の**新しいengineering choice**で、T2 paramsとは別に承認を要する本セットに含む。

3σは条件付き点wiseモデル境界であり、24方向-response-pointのjoint95%保証ではない。T1を選ぶ場合はユーザーδ・bias/CI配分を同時に決め、calibration開始前にformalの式・閾値もhash固定する。R6結果を見てformal判定基準を作る構造にしない。

決定論的solverにおける検証内容は、calibration点で固定した応答モデルが、**未使用のinterior εに対応する未使用phi bytesへ補間できるか**である。独立noise validation、外挿、ε→0真の導関数、方向間一般化、別solver/物理的正確さを検証しない。gのbiasをcが補償し内部予測だけ合う可能性も残る。

4方向×3ε×2sign=24paired states。別kernelのidentity/sanity用baselineを1つ含める推奨運用は**25 states**（baselineはnoise推定に使わない）。calibrationPASS後に初めてformalを登録するが、形式・criteriaテンプレートはR6前に承認/固定する。calibration49とformal25は別kernel・別roundで、同一canonical/direction/solver/tolerance/source identityとcalibration artifact hashesを結合する。formalFAIL/UNRESOLVEDはcampaign成功に昇格せず、R6を再調整しない。

取り置き2directionsという代案は方向間の情報だが、2/2成功でも iid Bernoulli仮定の片側95%下限sqrt(.05)=.2236、両側95%下限sqrt(.025)=.1581。恣意的な方向選択や相関でこの解釈自体が壊れる。推奨セットは取り置きを追加しない。既存fresh33とは別契約が必要で、既存登録/verifierには適用しない。

現HEAD source anchors: scripts/register_fd08_formal.py:111（build）, :207–213（calibration連続5点制約）、scripts/verify_fd08_formal.py:87（旧verifier）, :115（固定3方向inventory）, src/cfd_sdf/fd08_contract.py:48（3 baseline/3方向/5ε矩形）。変更は次作業のみ。
