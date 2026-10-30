# B-7 predict-then-run の設計メモ（未決・未登録）

証拠区分は `solver_free_design_and_simulation_unregistered`。全 qualification flag は false。calibration と formal は実行・登録していない。B-3〜B-7 と ladder は未決。本メモは B-7 の判断材料であり、R5 の新 gate 評価を行わない。

## 固定した内挿予測を新しい state と比較する案

calibration の各 direction,response で model A の `(g_hat,c_hat)`、非 scale covariance `C=(X^TWX)^−1`、pilot と重み、使った全 ε と S、params の数値・SHA-256、選択・停止規則を freeze する。新点を解いた後に再 fit、共分散 scale、tolerance 変更、選別をしない。g は N/mm の内部 fit 値、ε は mm、予測 S は N として単位を固定する。

新しい内部 ε の候補は `epsilon_new=sqrt(epsilon_i*epsilon_(i+1))`。3 個の interval を **calibration 値を観測する前に**決める案として、n 点 ladder の `i={0,floor((n-2)/2),n-2}` を使う。全候補が端点の内側にあり、calibration のどの ε とも一致しないことを nominal ε と float32 signed phi bytes の両方で確認する。jitter の ε と重なる場合の扱いも preregistration 前に決める。重複が分かった後で response を見ながら代替点を選ばない。

`x_new=(epsilon_new,epsilon_new³)`、`S_pred=x_new*(g_hat,c_hat)`。2 sign の新 solve から `S_obs=(F_plus−F_minus)/2` を得て、案として次の境界で比較する。

`sigma_pred² = sigma0_n² + (rho*S_pred)² + x_new^T*C*x_new`

`abs(S_obs-S_pred) <= max(3*sigma_pred, tol_hold*abs(S_pred))`

σ0、ρ、tol_hold は v2 params の仮定値（暫定案・未承認）を事前に固定する。σ0 を jitter 測定で更新する案は、その estimator・bias/correlation の扱い・CI と実行順序を登録前に確定する別判断である。ここでは更新しない。3σ は各点の条件付き境界で、全 4 directions ×2 responses ×3 ε の simultaneous 95% coverage を与えるものではない。共通 model bias と response 間の相関をこれで排除しない。

設計は `4方向×3 ε×2符号=24 state`。現行丸め runtime 仮定では solver 約 2608.8 s、overhead 約 1776 s、経過約 4384.8 s。baseline と再測定 jitter はこの 24 に含めていない。4 方向の採用は B-4/B-6 の未決選択であり、現行 3 方向を変更した事実ではない。calibration に jitter を含めた総予算とは別で、同一 kernel に足すか分割するかも未決。

この検証が与えるのは、**同じ solver、同じ direction における当てはめの内挿予測**への新しい入力 byte 列の検証である。決定論的 solver でも fresh33 の同一条件再実行より入力上の情報がある。protocol の方向間一般化、ε→0 の真の微分、solver の物理妥当性、#23 の勾配 backend の資格化を保証しない。g の誤りと c の補償で内部予測だけが合うこともあり得る。calibration gate と prediction 比較の両方を別に報告する。

## 取り置き direction との比較

| 案 | 新しい情報 | state 数・実装 | 統計的・科学的限界 |
| --- | --- | --- | --- |
| predict-then-run | 各固定 direction の calibration 未使用 ε の予測 | 4×3×2=24 state。新方向 generator が不要 | 同じ方向の内挿予測。外挿・protocol 一般化を評価しない |
| 取り置き direction 2 個 | 未使用の空間方向に対する gate | 2×n ε×2 sign に baseline/jitter を別計上。新 generator と hash 契約が必要 | 2 directions しかなく、2 responses と ε を独立な方向試行数に水増ししない。取り置き側の fit が pass しても calibration 方向の g を直接検証しない |
| 併用 | 方向内予測と方向間の情報 | 上記両方の費用・契約 | 同じ solver を共有。独立な物理 reference ではない |

2/2 PASS を独立・同一分布の Bernoulli directions とみなす場合でも、合格確率 p の Clopper–Pearson **片側 95% 下限**は `sqrt(0.05)=0.223606798`（計画文の約 0.22）。**両側 95% 区間の下限**は `sqrt(0.025)=0.158113883`。したがって「95% 下限 約 0.22」は片側の意味でのみ正しい。恣意的な 2 directions の選択や同じ生成器・solver による相関があるなら、Bernoulli の独立同分布仮定自体が保証されない。取り置きの成功で強い一般化を主張しない。

## ladder 上端 5 mm /15 mm の判断材料

指示文 §5 が求める、model B 真値 `g*epsilon+k*epsilon|epsilon|` を model A が吸収する限界は、Stage 1 の固定シミュレーションで比較する。5 mm ladder は `geomspace(0.5,5,6)` と `geomspace(0.3,5,8)`、15 mm は `geomspace(0.5,15,7)`。**曲率比は両上端とも `abs(k)*5 mm/abs(g)` で固定**し、同じ物理曲線を比較する。15 mm で曲率係数を小さく調整すると同じ上端曲率になり、上端拡張の情報を比較できなくなる。

数値比較の正式記録は同ディレクトリの [simulation_report.md](simulation_report.md) と [simulation_result.json](simulation_result.json) の上端 tradeoff を参照する（primary の固定シミュレーションが作成）。比較対象は各曲率比・g・既定 params の PASS/FAIL/UNRESOLVED、誤通過、g 相対誤差である。弱い model 差だけを見て ladder を選ばない。5 mm 以下は model A が非解析的 model B をよく近似し得る一方、15 mm は曲率の違いを拡大するが、背景計画が指摘する D0 の非線形域を含む。後者は既存の診断上の設計リスクであり、15 mm での solver 挙動を本作業が測定したという意味ではない。新たな ladder の上端・点数・span は本メモで決めない。

## 既存登録との衝突

`scripts/register_fd08_formal.py:207-213` は formal ladder を calibration の連続 5 点部分集合に制約し、`:111` の build は旧 selection・raw inventory と source hash を再計算して結合する。`scripts/verify_fd08_formal.py:87` は fresh33 と旧 gate を検証する。`src/cfd_sdf/fd08_contract.py:17` の run count は 33、`:48` の design は 3 baseline +3×5×2。predict-then-run には別の登録・検証契約が必要である。これらの source、criteria、既存 evidence は一切編集しない。

参照: `docs/issues/46_fd08_v2_stage1_instruction_2026_10_06.md §5`、`docs/issues/46_fd08_B_decision_plan_2026_10_06.md §3 B-7, §4-§5`。B-7 の採用、取り置き方向との併用、被覆規則と #23 の scope、R6 の登録はユーザー判断として残し、Stage 1 で停止する。
