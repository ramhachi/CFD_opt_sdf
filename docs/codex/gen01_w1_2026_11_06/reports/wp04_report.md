# WP4 TOPO-2D-00 WaterLily 側 — Amendment 6 報告

## 状態

**PARTIAL：N1／N3、登録どおりの N2 実装、CPU 検証は完了。N2 の Monte Carlo 受け入れ条件が1件未達。**
重点 pytest は **314 passed / 1 failed**、CPU Julia 自己テストは **86/86 pass**。
未達を隠すための定数・seed・assertion の変更や xfail は行っていない。

基点0741a474、branch feat/gen01-w1-04-topo2d-waterlily、開始時差分は空。
今回の authority は follow-ups worktree の登録 **Amendment 7** と
reviews/wp04_review_2_opus.md。読取元の絶対 path／SHA は
[authority.json](wp04_validation_amend6/authority.json)。
これは software contract／短い CPU capability evidence で、本測定は NOT_RUN。

最新ユーザー Amendment 6 に従い、commit／push／PR #89 更新は Claude host が担当する。
この agent は stage／commit／push を行っていない。
job・Julia helper・自己テスト・幾何・scene・登録本文・既存 evidence は変更していない。
GPU、Kaggle、RANS、登録・凍結・ロードマップ改定も行っていない。

## 作ったもの（パス、1行ずつ）

- scripts/topo2d00/analyze.py：非単調順位のΔ13を両側で必須化し、jointly resolved pairだけで順位比較。DOMAIN欠測とDOMAIN-only capを記述用に扱う。
- scripts/topo2d00/check.py：analyzerや共有評価helperをimportせず、同じ登録規則を独立再計算。
- scripts/topo2d00/prerun_window.py：最初のsample起点のburn候補、±2 SE、fallback、点推定S0、W clip、全候補と両flagを記録。
- src/cfd_harness/scene_campaign.py：parent_windowの400超過拒否をclipに変更し、SHA／raw再計算によるformal admissionを維持。
- tests/topo2d00/test_analyze.py：h′、resolved13逆順、W/R片側非単調、worst qualified cell、DOMAIN欠測、raw capのrole scope。
- tests/topo2d00/test_check.py：analyzerをimportしないchecker単体の非単調順位／DOMAIN到達性。
- tests/topo2d00/test_prerun_window.py：既知S0、独立端点積分、first sample offset、fallback／clip、200 seed×3条件のAR(1)。真値50の条件はfailを保持。
- tests/topo2d00/test_campaign.py：parent_windowが400へclipする契約。
- reports/wp04_design.md：最新設計、必読文書の全文確認、worker fallbackの記録。
- reports/wp04_validation_amend6/：実行記録、raw CPU出力、TDD logs、AR(1)全seed、独立算術audit、protected path検査、GPU smoke runbook。

commitすべき完全な一覧（各pathの変更／新規区分）は
[wp04_pending_files.json](wp04_validation_amend6/wp04_pending_files.json)。
移動と削除はない。大きい人工checkpointはサイズ／SHAを記録して保存対象から除き、
raw logsはdeterministic gzipで保存する。

## インターフェース（他WPが使う関数・CLI・ファイル形式）

N1：Wと全qualified R cellのdownforce Δ12／Δ23は常に必要。
Wまたはいずれかのqualified R cellでE2が最良／最悪となるときは、Δ13も両側で必要とする。
必要区間が0を含めばそのReはUNRESOLVED。順位逆転は両側でresolvedな同じ対に限る。
waterlily.<Re>.13、rans.<cell>.13のdownforce／drag統計量と
agreement.<Re>.required_pairsをJSONへ追加し、Markdownにも13の区間を出す。
Amendment 5のper-Re combination、manipulationと研究ラベル優先順位は維持した。
INVALIDを除く8研究ラベル、含めた9ラベルをテストする。

N2：prerun_window.py SERIES SUMMARYのwritten-once recordは引き続き
topo2d-parent-window-v1。旧s0_upperを **s0_point** に置き換えた。
今回のsource/test以外に旧fieldのconsumerはなく、formalな既存parent recordはない。
単位はdownforce=N/m（ρ=1,U=1）、時刻=c1/U、S0=(N/m)²·c1/U。

- 候補はfirst_sample_time+50k。520以内の完全100幅候補を全件記録する。
- 候補100幅平均と残り全体の平均を比較し、残りの完全20幅batch meansのsample SEの±2倍を使う。SEには2batch以上を要求し、末尾の不完全batchは除く。
- 最初の合格候補からB=max(80,candidate_start)。合格なしはB=130、BURN_IN_FALLBACK=true。20幅2batch未満の後方候補も理由付きで記録する。
- B以後のL=10／20／40のL×sample_variance(batch means)の最大がS0。χ²上限は使わない。
- Wは1.5% SE条件を満たす最小50倍数を400へclipし、超過ならWINDOW_CAPPED=true。元の丸めた幅をuncapped_window_widthにも残す。

flagsは両booleanを常に持つ。累積trapezoidと部分線分の二次原始関数で、
区分線形時系列の端点補間付き時間積分を計算する。
source／scene／series SHA、全統計値の再計算、observable／高さ／runtime検査、
exclusive-createは維持。formal campaignはrecordからB／Wを読み、手入力を拒否する。
実GPU pre-runは未実行なので、docs/harness/topo2d00_window_re*.jsonは作っていない。

N3：不完全・timeout・readout欠測・単一位相・不対・primaryに対応しないDOMAINは
両実装で **DOMAIN_NOT_JUDGED**。有効な2位相以上は従来の3 pooled SEで記述用判定を行う。
DOMAIN-only timeout／overrunのreceiptと未測定markerをprovenanceへ残し、
それだけではnormalized study cap_hitを立てない。
primaryなど他roleに影響するcap、明示的study freeze cap、および実際の非有限solveの
NUMERICALは登録どおり保持する。raw verifierのintegrity拒否は緩めていない。

WP5共有RANS schemaとgeometry schemaは今回変更なし。
observable=pressure_clはsharp／Cp比較、total_clはthick／WaterLily比較で、跨ぐ差分は拒否する。
共有schemaは[topo2d00_rans_result_schema.json](topo2d00_rans_result_schema.json)、
SHA256=5bba0a153fc033d2a9a0a6f42bbb37d0efe134bce7b8f96fa57472dafad4d175。

## テスト（コマンドと結果）

- TDD red：解析側34 failed / 178 passed、14.77秒。窓側11 failed / 11 passed、3.58秒。
- N1／N3専用green：213 passed、7.07秒。analyzer／独立checkerの数値・ラベル比較を含む。
- 窓推定＋campaign（MC以外）：51 passed / 3 deselected、33.71秒。
- .venv/bin/python -m pytest -q tests/topo2d00 -p no:cacheprovider -rf --junitxml=<validation>/targeted_junit.xml -o junit_family=xunit1：**314 passed / 1 failed、68.83秒**（process68.96秒）。失敗nodeは下記のみ。実行前後のsource hash一致。
- JULIA_NUM_THREADS=1 julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl <validation>/cpu_selftest：**86/86 pass、test56.8秒／process58.06秒**。親環境からTOPO2D_*／W4_*／CUDA_*を除去し、外部provider注入なし。正確なargv／環境はcpu_execution.json。
- .venv/bin/python -m compileall src tests：**exit0**。
- git diff --check：**exit0**。
- 全体pytestは最新Amendment 6 item5に従い **未実行**。過去の全体greenを今回の全体検証とは呼ばない。

唯一の失敗node：

    tests/topo2d00/test_prerun_window.py::test_stationary_ar1_two_hundred_seeds_have_no_refusal_and_calibrated_median[50]

CPUはJulia1.12.6／WaterLily1.8.0／Array／Float32／QUICK／1thread。
E1/E2のfinite force、moving-ground近傍u=U、共通phase translation、
remeasure=falseとtrueのbit一致、branch内WP1 Checkpoint再開、tuple unionのisbitstype、
人工tiny-Δtの実job exit42／NUMERICALを確認した。
WP2 Force00.jlはこのbranchに無く **NOT_INTEGRATED_CUR_ONLY**。
nds／cvは予約列であり、3readout／GPUの成功は主張しない。

## N2の未達：AR(1)の指定受け入れ条件

reviewと同じmean0.17 N/m、τ=1 c1/U、dt=0.05、horizon520、定常初期値、
seed0–199（各条件で同じ200seed）で実行した。
φ=exp(-dt/τ)、S0=variance×dt×(1+φ)/(1−φ)を使い、
S0=W_true×(0.015×0.17)²から分散を設定した。

| 真のW | 拒否 | 中央値W | 中央値／真値 | 1.5倍以内 |
| ---: | ---: | ---: | ---: | --- |
| 50 | 0/200 | 100 | 2.0 | **FAIL** |
| 100 | 0/200 | 150 | 1.5 | PASS |
| 150 | 0/200 | 200 | 1.333333 | PASS |

600履歴すべて窓を生成し、この設定ではfallback／clipの使用は0。
真値50の分布はW50が82件、W100が114件、W150が4件。
最大point S0と50刻み切上げによる量子化が中央値100に結び付いている。
これはこの設定での観測であり、あらゆるseed集合に対する不可能性の証明ではない。

独立のirregular-time算術auditは20履歴／540比較でPASS。
生産コードの積分helperを使わずnp.interpとnp.trapezoidで照合し、
最大差はremainder mean8.88e−16、SE4.61e−16、S0 4.94e−17。
別workerの静的レビューでも式とAR(1)生成器の実装不具合は見つからなかった。
全seedの窓と設定は[ar1-results.json](wp04_validation_amend6/ar1-results.json)、
集計は[ar1_summary.json](wp04_validation_amend6/ar1_summary.json)。

## 仕様からの逸脱と理由

登録Amendment 7の式・定数は変更していないが、MCの1.5倍条件が真値50で未達。
この条件を満たしたという完了報告はできない。
ユーザーへ事実と選択肢を質問済みで、現行式の維持／受け入れ条件の見直しについて回答待ち。
回答は推測しない。acceptance testをfailのまま保持し、PARTIALとする。

OpenCode GoはCLIで現在モデル一覧を確認したが、3件の実行要求は全て
api_key_expired／HTTP401で処理開始前に停止し、Goの作業成果は得られなかった。
認証・global設定・追加課金は変更せずnative workersへfallback。
必読governing documentsは分担して全文確認した。worker結論は差分・実行結果・
独立の静的レビューで確認し、その回答だけを完了根拠にしていない。

## 未確認の仮定

幾何は今回の指示で再生成していない。以下は変更していないscene metadata／既存検証の値で、
今回新たな幾何・物理qualificationを行ったものではない。
主格子最大厚肉比はmain4.594745、E2 flap8.866711、E3半flap各17.733423。
確認格子はmain3.063211、flap5.911141。

| 格子 | Δx mm | c1 cells | flap cells | 半flap cells | 公称gap cells | t_min mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c1/120 | 1.861666667 | 120 | 89.006267 | 44.503133 | 6.445837 | 7.446666667 |
| c1/180 | 1.241111111 | 180 | 133.509400 | 66.754700 | 9.668756 | 4.964444444 |

![E1 E2 E3 geometry, unchanged](topo2d00_geometry.png)

*_sharpは公開有限TE原形でmathematically_sharp=false。E3は構成例で公開三要素の再現ではない。
E3半flap元最大厚6.701146189mm < 主格子t_min、鼻のpaired-normal-width crossingは
4Δx未満12.608231%、(2+√2)Δx未満6.846234%（登録概数12.9%／6.9%とは別項目）。
LE cap／鼻はbulk phase-core証明から除外される。このcaveatは未解消。
座標sourceはUNVERIFIED_OCRのままなのでformal freezeは引き続き拒否する。
PDF画像との照合・Cp二読取、TR-00適格化、RANS、GPU smoke／checkpoint／性能は未実行・未確認。
確認格子は4Δxで再厚肉化するためgrid-and-geometry contrastである。

## Claude／ユーザーへの提案する追記

phase_plan／STATE／registration本文は編集していない。
今回得たのはliteral Amendment 7実装とソフトウェア／CPU検証であること、
真値W50のMC条件が未達であることを判断材料として残す。
registered constantsをagent側で調整して解消したことにはしない。

## 次に要るもの

N2受け入れ条件の判断が必要。今回の変更をすべて受け入れ完了とは扱わない。
commit／pushのhost用完全一覧はwp04_pending_files.json。
後日のGPU smoke条件は[runbook](wp04_validation_amend6/README.md)にあり、
**force sampleあたりの同期付きwall milliseconds**、sample数、compile／warm-up分離を追加した。
GPU実行や追加課金を許可する文書ではない。今回の根拠から物理downforce、
grid independence、Re転写、FSAE適格性を主張しない。
