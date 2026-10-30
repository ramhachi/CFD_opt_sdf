# #46 FD-08 契約 v2 Stage 1

## 実行前に転記した受け入れ条件

- **A1**: シナリオ a・b（σ ≤ 3 µN）で、既定 tolerance の PASS 率 ≥ 95%。各シナリオ・各 ladder で確認する。
- **A4**: **全シナリオ**で、既定 tolerance での誤通過率 < 5%。ただし曲率比 100% 以上の d は**報告のみ**（検出の限界を測るための範囲外）。
- **A2（報告のみ、合否なし）**: d の曲率比ごとの PASS 率と、PASS 率が 20% を下回る曲率比を報告する。曲率比 25% の検出を要求しない。
- **A3（報告のみ）**: c・e の結果。
- A1 または A4 を満たさなければパラメータ・tolerance・シナリオを調整しない。他の成果物を完成させ、**Stage 1 FAILED** と記録して #46 に報告し、止まる。

この節は最初のシミュレーション実行より前に記録した。実行前のファイルの bytes/hash は `prerun_freeze.json` に保存する。

## 範囲・前提

証拠区分: `solver_free_design_and_simulation_unregistered`。
基準 HEAD: `82cb953`（integration を pull し、そこから `exp/issue46-fd08v2-stage1`）。
指示: [Stage 1 指示文 v2](../../issues/46_fd08_v2_stage1_instruction_2026_10_06.md)。背景: [B 計画 v2](../../issues/46_fd08_B_decision_plan_2026_10_06.md)。

暫定パラメータは未承認。sigma0=3 µN は仮定であり実測ノイズではない。
B-3〜B-7、ladder、被覆規則、予算の変更は未決。この実装・測定はそれらを承認・登録しない。
R5 は FAIL のまま。評価器を R5 に適用しない（dry-run も禁止）。既存の登録コード・criteria・証跡を変更しない。
新規 src/scripts/tests は `docs/evidence/fd08_candidate_c_calibration_*` を読まない。
評価器は `cfd_sdf.fd08_*` を import しない。
R6/formal 登録、criteria/dataset 作成、Kaggle 操作、solver 実行、#23 のスコープ変更、direction 登録、epsilon_m 意味の変更は実施しない。
全 qualification flag は false: shape_update_allowed=false, fd_oracle=false,
field_gradient=false, reverse=false, optimizer=false, topology=false
（登録コードの6 flagを照合、変更しない）。

## 実行前に固定する計算設計

- numpy `2.5.2`、Python `3.12.13`。乱数は `Generator(PCG64(seed_ij))`。
- base_seed=461006、seed_ij=base_seed+1000×scenario_number+ladder_point_count。scenario_number は 1 始まり、順番 a1,a2,b（a1→a2、σ=1.5,3,4 µN）,c（a1→a2、w=.04,.07）,d（g=-.104→-.17、曲率比=.10,.15,.25,.50,1,1.5,2）,e。
- 各点で絶対ノイズを先に、相対偏差を後に引く。ノイズなし・相対偏差なしでも二つの標準正規乱数を消費する。c の算式は S_true×(1+w×z)+絶対ノイズ。
- 各シナリオ・ladder 2000 試行。同一観測に既定 tolerance と同時 5/10/15/20% 感度を適用。sigma0,rho,nested_drop,k_mag は変えない。
- ladder は geomspace(.5,5,6)、geomspace(.3,5,8)。上端比較は d のみ geomspace(.5,15,7)。d の k は 5 mm 基準で固定し、15 mm 比較でも同じ真の係数を使う。
- 固定20合成入力は別 seed base_seed+900000+1000×scenario_number+ladder_point_count から生成し、a1,a2,b,c,d,e と6/8点へ配分する。対応表を保存する。既定値を添付する。
- JSON は sort_keys=True,allow_nan=False、floatは有効数字12桁。JSON hash は同一環境内の再現確認用で、機種間では参考値。図は作成を要求されていないため数値表で報告する。
- WLS は OLS pilot→重み→WLS の1回のみ。共分散は公称値を使い、chi²/dof のスケールを使わない。反復の2回目と1回目で g が約1e-4異なる例が仕様書に報告されており、この変更は採用しない（本成果物の測定値ではない）。
- 符号項目の部分集合は指示文の括弧 k=1,…,3、入れ子安定性は nested_drop=2。n<4 は UNRESOLVED。計算可能な項目1〜5の不合格は項目6より優先して FAIL。

## Git 運用

ユーザー指定の integration=`codex/kaggle-batch-migration` と `--no-ff` merge を使う。
これは `docs/git_branching_strategy.md` の trunk 運用とは異なる、今回の明示的な運用指示である。
意図した新規ファイルのみを commit/push し、#46 に報告して止まる。

## 実行結果と停止点

**実装・合成測定は完了。A1/A4 は PASS、独立検算の厳密な全数値一致は未達。**
`simulation_result.json` の `stage1_status=Stage 1 PASSED` は §3 の A1/A4 に限定した判定であり、
独立検算・実 target・契約登録まで含めた合格を意味しない。成果物全体を無条件の PASS としない。
パラメータ・tolerance・シナリオ・評価器の凍結後変更は 0。数値差を隠すための absolute tolerance を追加していない。

最初の実行前凍結は 2026-10-06 07:34:29 UTC（16:34:29 JST）。
params JSON（153 bytes）の SHA-256 は
`c5f3fe1a3875c44d5fd0b87d48fd0bd0c06bdf22fb74581cb399e382dbac95ba`。
**暫定案・未承認**のまま。実行前 note の原本は `prerun_note.md`、hash は `prerun_freeze.json`。
本 note のこの結果節は実行後の追記で、実行前原本は変更していない。

27 シナリオ ×6/8点 ×2,000試行の 108,000 系列、d の上端15mm比較は14条件 ×2,000=28,000系列を測定。
各観測に既定値＋4つの同時感度を適用し、主結果270条件＋上端比較70条件をJSONに保存した。
誤通過は PASS かつ真のgからの相対誤差>20%、誤棄却は対象a/bだけで FAIL かつ誤差≤5%とした。

- **A1**: 対象12条件の最小PASS率 **99.95%**（b07: g=-.104 N/m、c_q=-.00104、σ=3µN、8点、1999/2000）。要求95%以上を満たす。
- **A4**: 対象42条件の最大誤通過率 **0%**。要求5%未満を満たす。dの曲率比100%以上は報告のみ。
- 対象a/bの最大誤棄却率 **0.05%**（b07・8点の1/2000）。c/d/eに誤棄却ラベルは付けない。
- **A2**: 曲率比25%のdは全条件100%PASS、g誤差中央値4.25〜4.99%。モデル誤指定をこの域では検出していない。5mmでPASS率20%未満になる最初の試した比は、g=-.104/6点で100%、その他は150%。15mm/7点ではg=-.104で50%、g=-.17で50%。詳細と感度は `simulation_report.md`。
- **A3**: 4%波打ちのPASS率99.50〜99.85%、7%波打ちは87.00〜90.90%。弱いeは6点77.60%、8点91.15%PASS。UNRESOLVEDはこのシミュレーションでは0%だが、少数点・絶対量のみ不足の分岐はテストで検証した。

0/2000という実測は母集団の誤通過が厳密に0という保証ではない。モデルとノイズを固定した合成試験だけである。
同一環境で固定設計を全量再実行し、simulation_result.json・synthetic_inputs.json・primary_fixed20_results.jsonのbytes/hashが全て一致。
simulation JSON SHA-256: `0279d06556c488b9da598fdb86604434c2b42a45344293299afd631245ca84f2`。
JSON hashは同一環境内の再現確認用、機種間では参考値。

## blind 独立検算

別担当は §2/§3 の仕様だけを読み、独立実装を fixture 受領前に封印した。
封印時 checker SHA-256: `01c8ed3778c9de26e82ce8c85100b1ea9f02db035d23cd803b19ffed99d17824`、
一時独立repository commit=`929501f`。その後に固定20入力とparamsだけを渡した。
担当は primary のコード・出力、登録済みhelpers、R5を見ていない。比較と原因の検討は担当の完了後に親が行った。
配布入力のSHA-256: `870477620ea9cf23ce3069b4be785c2ceeee994e7d464ea4835cbc0f4b816897`。
対応表・seedは `synthetic_inputs.json` に保存。

比較は `compare_fixed20.py` が保存済みの2つの出力だけを読み、数値を
`abs(primary-independent)/max(abs(primary),abs(independent)) ≤ 1e-9`、両方0なら差0として評価する。
absolute tolerance は **0**。結果は `independent_comparison.json`。

- 20/20 の3値判定が一致: PASS18、FAIL2、UNRESOLVED0。FAILはd18の6/8点。
- 判定・点数・部分集合フラグなど580個の厳密比較: **不一致0**。
- 数値5,600個: **5,583適合、17未達**。g、SE、β、重み、pilot、共分散、holdoutはすべて1e-9以内。
- 17個はノイズなしa1/a2の入れ子相対ずれと、a1のモデル差。値は約3e-14〜4e-12、差の絶対量は最大 `9.99990156869e-17`、純粋な相対差の最大は `0.00280628272149`。

原因は単位換算の前後での浮動小数点の桁落ちである。
primaryは `abs(g_subset_mm-g_full_mm)/abs(g_full_mm)`、独立は同じgをN/mに換算してから差を取る。
数学的には同じ式だが、ほぼゼロの差に純粋相対許容を適用すると、換算の丸め差が大きな相対差になる。
親が同じprimary fit値からN/m側の算式を計算すると、ノイズなし4入力×4診断=16値すべてが
独立出力の12桁値を正確に再現した（`independent_roundoff_diagnosis.json`）。
各最大入れ子項目はこの診断値のmaxであり、重複を含め17未達になる。
これは異なるpilot・重み・モデルや判定の相違ではない。

**それでも指示された純粋相対差1e-9の全数値条件には未達である。**
仕様の許容を事後変更して数値一致PASSとはしない。評価器と独立実装を修正して一致させる操作もしていない。
3値判定の不一致は0なので、§6の「判定が違えば曖昧さとして記録」の条件は発生していない。
符号のdrop1..3/安定性drop1..2、n<4の優先、ゼロgの扱いは双方の実装前解釈に記録した。
近ゼロ診断量の数値許容・単位演算順序を契約上どう扱うかは、この停止点から先の判断事項として残す。

## 設計表・設計メモ

18の予算案、登録済みsourceの変更候補と実在file:line、epsilon_m影響関数は `design_tables.md/json`。
各方向2 jitter stateを含めると、4方向以上は全案solver上限超過。
4方向×6点+baseline1+jitter8は57state、solver6195.9秒、経過目安10413.9秒。
新directionの生成案・float32 gate・ノイズ推定の自由度とχ² CIは `design_note_new_direction.md`。
predict-then-runの24state、予測式、取り置き方向との比較、5/15mm上端のtradeoffは `design_note_predict_then_run.md` とシミュレーション表。
方向ごとの「自由度1」やpoolのCIは、独立・同分散・平均の扱いを仮定した条件付きの値であり、実測noiseを取得した主張ではない。
B-3〜B-7、ladder、ジッター定義、被覆規則、#23 scope、budgetは未決のまま。

## 検証・再現手順

使用したinterpreterは `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python`。
新規worktreeに依存関係をインストールせず、既存Python3.12.13/NumPy2.5.2環境を使った。

1. `git pull --ff-only origin codex/kaggle-batch-migration` をintegrationで実行、HEAD82cb953を確認。
2. clean baseline worktree `/tmp/fd08-v2-baseline-20261006`、commit4eef582で `python -m pytest -q --junitxml=<evidence>/baseline_junit.xml`。
3. `python -m pytest -q tests/test_fd08_v2_gate.py`: **18 passed**。
4. `python scripts/simulate_fd08_v2_gate.py --freeze` → `python scripts/simulate_fd08_v2_gate.py`。
5. blind担当: `python independent_checker.py synthetic_inputs.json --output independent_fixed20_results.json`（元の封印名はchecker.py）。親: `python <evidence>/compare_fixed20.py`。
6. `python scripts/design_fd08_v2_tables.py`: 18案、source anchorの存在を実行で検証。再生成bytes一致。
7. `python scripts/simulate_fd08_v2_gate.py --replay-output /tmp/fd08-v2-stage1-exact-replay`: 全量の再現hash一致。
8. `python -m compileall -q src tests scripts/simulate_fd08_v2_gate.py scripts/design_fd08_v2_tables.py <evidence>/independent_checker.py <evidence>/compare_fixed20.py`: exit0。
9. 変更後 `python -m pytest -q --junitxml=<evidence>/postchange_junit.xml`: **37 failed,1463 passed,9 skipped**。

baselineは **37 failed,1445 passed,9 skipped**。両failure ID一覧は既知37件と完全一致、新規0・解消0。
full pytestは37件の既存failureのためexit1であり、全suite PASSとは報告しない。
baseline前後のtracked/untracked状態はclean。
ignoredのcanonical fixtureは双方のtest worktreeから既存の同一bytesを参照した（SHA `7a972b33…`、詳細 `validation.json`）。
R5 calibration artifactを新評価器に渡したものではない。
JUnitのexact raw XMLは `.xml.gz` にbytes同一で保存し、`.xml` はtracebackの行末空白だけを除いた閲覧版。
テスト数・failure IDsが両版で同一であることを確認し、両hashをvalidation.jsonに記録した。
git diff --checkの対象外としてrawを隠すのではなく、gzipでrawを保護し、閲覧版の空白を整えた。

成果物と新規コードのhashを `SHA256SUMS` に列挙する（自身のhashは含めない）。
意図した新規ファイルのみをcommitし、integrationへ `--no-ff` merge/pushし、#46に結果を報告して停止する。
R5 FAIL、全6 flag=false、保護コード・criteria・既存証跡は維持する。R6/formal/Kaggle/solverには進まない。
