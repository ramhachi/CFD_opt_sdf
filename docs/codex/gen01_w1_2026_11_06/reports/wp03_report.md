# WP3 GRAD-00 報告（Amendment 3）

## 状態

**DONE（今回の実装・テスト・CPUドライラン・報告の範囲）。** Amendment 3の修正を実装し、関連203テストと指定の結果側全体pytestを完走した。登録窓／GPUでの測定は今回の範囲に含めない。

開始 HEAD は `e2dddf06`（直下 `05138c72`、`0b226184`）、branch は `feat/gen01-w1-03-grad00`、開始時は clean。今回の実行記録は2026-11-07 JST。ユーザーの Amendment 3 と、指定 review worktree の仕様 Amendment 1・2を適用した。WP3側の rev 0 本文は変更していない。外部仕様とreviewの SHA は `wp03_validation/amendment3/integrity_audit.json` に保存した。

Kaggleへのpush、GPU実行、full-window CPU測定、kernelの再生成、git add/commit/push、PR #86 の本文更新は行っていない。commit/pushと5 kernelの再生成は、指示どおりClaudeのhost作業である。既存5 kernelは旧 source `05138c72`／旧 analyzer `992c7073…` のままで、今回の修正を含まないため、この旧renderで測定を始められない。

## 作ったもの（パス、1行ずつ）

- `scripts/analyze_grad00.py`：認証済みの失敗腕の終端分類、D′の次段候補、方向ラベル優先順位、D′実行条件の表示、CPU7-run対応。
- `tests/test_grad00.py`：本物のDのpreflightを使うfixture、primal blow-up／wall abort／部分D′／起動失敗、認証拒否、次段規則、checkとwrite-onceの回帰テスト。
- `scripts/waterlily_grad00_lambda_2026_11.jl`：CPU E/FのD0/D1制限、preflightのu/p最大tangentの符号付き値・cell・位置記録、自己比較の`determinism_*`改名。
- `scripts/waterlily_grad00_lambda_2026_11.diff`：凍結TA1からの正確な差分。適用後のbytesは現在のjobと一致。
- `scripts/run_grad00_cpu.py`：E/Fの7-run検証と、失敗時にもidentity／ERROR／manifestを保存するCPU launcher。
- `tests/test_grad00_cpu.py`：CPU7-run scopeと失敗出力の正確なmanifestを検証。
- `scripts/grad00_orchestration_selftest.jl`：実際のmain/save_run!/index/hash処理の7-run合成検証と、13件の位置記録のassertion。
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_design.md`：実装前のAmendment 3設計メモ。過去節は履歴として保持。
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_report.md`：本報告、実行手順、完全なcommit対象一覧。
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/`：コマンド、exit、wall、source/artifact SHA、preflight、TA1比較、テスト、保全監査、独立レビューの記録。末尾に個別ファイルを全件列挙する。

`quick_nobound.jl`、`vanleer_safe.jl`、reference／generator／reference tests、builder／builder tests、1.10 projectは既存の実装を再利用し、この回では変更していない。新しい依存は追加していない。

## インターフェース（他WPが使う関数・CLI・ファイル形式）

jobの15引数、`GRAD00_ARM`の5値、`GRAD00_T`、`G2_BACKEND`、`g2_run_index.json`と`grad00_index.json`の名前を保持した。CUDAは1 shared plain＋4方向×(Dual,plus,minus)の13 run。CPUはFloat32/Float64ともD0/D1の7 run。Eは1.10.0/quick/Float32、FとCPU Float32対照は1.8.0のA/B。新しいmode環境変数は設けていない。

analyzerはexact file inventory、全artifact SHA、source commit/tree/pinsとverifiedの一致、実行時consumerと現在のconsumerの一致、referenceと出典を検証する。`DONE`か`ERROR.txt`の一方だけを要求する。

| 出力 | 腕レベルの扱い | 次段候補 |
| --- | --- | --- |
| 完備した測定 | BOUNDED_ALL／PARTIAL／BLOCKED_ALL、方向ごとのBOUNDED/BLOCKEDと比較ラベル | B/C/D/D′のT4 Float32、4方向のみ |
| ERROR、有限なselected_plain、正しいλ routing、非有限なselected_dual tangent、preflight失敗 | PREFLIGHT_BLOCKED | 対象外 |
| その他の認証済み失敗（primal blow-up、wall abort、途中失敗、index前の起動失敗） | ARM_ERROR、理由を保存 | 対象外 |
| D′またはEの出力が存在しない | NOT_RUN | 対象外 |
| 欠損・改変・認証不足・矛盾・未終了 | 例外で解析を拒否 | 判定しない |

実際のDの保存済み記録は、`selected_plain.primal_finite=true`、`selected_dual.primal_finite=false`、Dualの両tangent finite flagがfalseである。上表の有限なprimalは独立した通常primalを指す。このpayloadをfixtureでそのまま使い、Dual値の非有限性も結果に残す。原因は推定しない。失敗した腕には方向ラベルや未測定のforceを作らない。indexがない場合は観測できなかったJulia/ForwardDiffをnull、`runtime_observed=false`、runtime一致比較もnullにする。

A–Dの各identityには認証済み終端状態が必要だが、全方向ラベルの完備は要求しない。存在するoptional出力も必ず検証する。空のD′ディレクトリをNOT_RUNへ置換しない。E/Fの失敗にもCPU launcherがmanifestを残すため、同じ失敗分類を使える。

方向の比較は、評価可能なfx/fzのいずれかがDISAGREEならDISAGREE、そうでなくいずれかがNOT_EVALUABLEならNOT_EVALUABLE、それ以外はAGREE。閾値は符号一致かつ比の誤差0.1以内、3×spread、strict `>1e30`のまま。NEXT_STEP_ARMSはB/C/D/D′で、少なくとも1腕がBOUNDED_ALLかつAGREE≥3/4なら`GRAD01_DRAFT_ALLOWED`。これは登録draftを許す記述的規則で、qualificationを与えない。

quickの自己比較は`determinism_primal_u_bit_equal`／`determinism_primal_p_bit_equal`とした。D′の`vanLeer_primal_*_bit_equal`はstock Dとの実際の別λ比較のまま。凍結TA1とのcross-script比較は別の`ta1_bit_comparison.json`で示す。

## テスト（コマンドと結果）

```bash
.venv/bin/python -m pytest -q tests/test_grad00.py tests/test_grad00_reference.py tests/test_grad00_kernels.py tests/test_grad00_cpu.py -p no:cacheprovider
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
```

- 関連テスト：203 passed（analyzer 132、reference 5、builder 37、CPU wrapper 29）、8.66 s。実コマンドはJUnitの出力引数だけを加えた。`focused_checks.json`にsourceの前後SHAとexit 0を保存した。
- 全体pytest：**3685 passed、74 skipped、7295 warnings、failures/errors=0、exit 0**。pytest表示1187.20 s、process wall 1188.31 s、timeout無し。失敗node集合は **`[]`**（期待された空集合と一致）、実装・テストのsource SHAは開始時から不変。baseは指示どおり取り直していない。host baselineとの比較用に失敗node集合をそのまま提示する。実コマンド／source前後SHA／exit／wallは`pytest_full_command.json`、全stdoutは`pytest_full.txt`、JUnitと集計は`pytest_full.xml`／`pytest_full_result.json`。
- compileall：exit 0。sourceのcompileallとpytestは別々の記録で、数値検証に読み替えていない。
- Julia scalar selftest：1.8と1.10の両方で120/120 PASS。D′のtieのDualはcとそのpartialを返し、plainのstock Dとのbit identity、quick_noboundの一致・不一致例、finite partialを確認した。
- 1.10 instantiate：exit 0、6.92 s。`allow_autoprecomp=false, update_registry=false`。1.10.0／ForwardDiff 1.4.5を確認し、両projectのProject/ManifestのSHA不変。`package_checks.json`と各txtに記録。
- 合成orchestration：1.8/B/Float32、1.8/A/Float64、1.10/A/Float32の各7 runがPASS。実main/save_run!/input hashesを使い、preflight/run_oneだけをstub化した。各13件の位置記録assertionもPASS。solver stepsは0と明記し、実CPU preflightとは区別した。
- 凍結TA1からの差分をstable labelsのPython unified diffで再生成して一致し、実際のpatch適用でもjob全bytesを再現した。測定定数、load_raw、sample_row、window_mean、summarize、tangent_max、history_header、CPU window hook、BLOCK_LIMITもbyte-equal（22項目、`frozen_semantics_audit.json`）。
- reference `--check`はexit 0。formal payload archiveの55メンバー、output archiveの137メンバーを全件再ハッシュして一致、baseline rawはformal payloadとbyte-equal。4方向rawはTA1 pinと一致し、Fortran→C orderでformal direction hashesにも一致。εは全方向`0.003971641173621408 m`、spreadは指定のModel A gradient SE。
- 保護対象228ファイルをHEADと照合し、開始後も全件SHA不変。authority本文、referenceと凍結evidence、TA1／DIAG／QuickTie、全Project/Manifest、共有src、既存GRAD00 infra 15ファイルを含む。
- 独立レビュー：`source_review.json`はPASS_SOURCE_REVIEW、blockerなし。追加11 probeで、全primaryが起動ARM_ERRORでもcampaignが完結すること、実際のDの分類、認証／終了marker／preflight／λの改変拒否、determinism gateを確認。source reviewはソフトウェアの証拠で、測定結果ではない。

### 20-step CPU preflight

再現driverは`amendment3/run_cpu_validation.py`で、既存のAmendment 2 driverを新しい出力先で再利用する。`julia --startup-file=no -O2 -t 10`、`G2_BACKEND=cpu G2_DRYRUN_T_END=0.4 TA1_PREFLIGHT_ONLY=1`、BLAS/OpenMP各1 thread、referenceのεを使用。preflightのseedはTA1と同じD0であり、D1や登録窓のrunは始めていない。各プロセスのsafety limitは480 s、実際の8組は58–123 s程度で逐次実行した。全体pytestにこのlimitは付けていない。

| 対象 | 精度 | 20-step preflight | exit | wall [s] | max abs tangent u | max abs tangent p | p argmax index |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| A / quick | Float32 | PASS | 0 | 67.54 | 25.052122 | 33.658356 | `59;38;21` |
| B / quick_nobound | Float32 | PASS | 0 | 57.85 | 25.085028 | 31.356611 | `59;38;21` |
| C / cds | Float32 | PASS | 0 | 59.33 | 25.60788 | 29.023865 | `59;38;21` |
| D / vanLeer | Float32 | FAIL（想定された非有限） | 2 | 59.26 | 非有限 | 非有限 | `1;1;1` |
| D′ / vanLeer_safe | Float32 | PASS | 0 | 86.35 | 24.481001 | 32.072643 | `59;38;21` |
| E / 1.10 quick | Float32 | PASS | 0 | 60.61 | 25.949617 | 36.058117 | `59;38;21` |
| F-A / quick | Float64 | PASS | 0 | 122.57 | 23.920934 | 3302206 | `75;49;27` |
| F-B / quick_nobound | Float64 | PASS | 0 | 68.97 | 23.86481 | 3296238.8 | `75;49;27` |

表のtangentはsolver fieldのα[m]に対するpartialで、forceのN/mではない。Dの`1;1;1`はfirst non-finite位置であり、有限値のargmaxではない。Dのexit 2をPASS／DONE／full-window BLOCKEDに読み替えていない。`PREFLIGHT_BLOCKED`というtransport後の分類は認証済みfixtureで検証したもので、このCPU driver単体はproduction runnerのterminal evidenceではない。

Float64 A/Bのp tangent最大は、それぞれ`−3,302,205.9611`／`−3,296,238.7963`、共通cell `[75,49,27]`。world位置は約`(−0.0500, 0.383333, −0.0500) m`、canonical SDFは約`−0.0500 m`、groundまで`0.85 m`、最も近いdomain boundaryまで約`0.8167 m`、haloではない。表現された候補物体の内部にあり、遠方場／外側境界のcellではない。

Float32 A/Bのp最大は`+33.6584`／`+31.3566`、共通cell `[59,38,21]`、world位置約`(−0.583333, 0.0166667, −0.250000) m`。canonical SDFは`−4.77e−8 m`で、保存表現の界面近傍の小さい負値であり、solid深部とは呼べない。u tangentはFloat64で約23.9、Float32で約25.1と同程度。これらは20-stepの局在情報であり、圧力tangent増大の機序やfull-windowでの挙動は未特定。Fのp-watchdogをlimiterだけの効果と解釈しない。

preflightにはu/p別にindex、符号付き値、abs、finite、pressure centerまたはstaggered faceの座標、world位置、canonical SDF、ground distance、solid符号、halo、domain clearanceを記録する。design box外のSDFは登録された正のfluid extensionであり、幾何距離ではないと明記した。

凍結TA1は編集せず、trailing CLI callだけをメモリ上で抑えた既存captureを別プロセスで実行した。quick Dualの値成分とFloat32 plainのそれぞれで、u/pの4 SHAがコピー側と一致。capture wallはDual32.66 s、plain26.59 s。`ta1_bit_comparison.json`にsource/runtime/hashを記録した。CPUのみのcross-script検証で、T4のTA1とのhash比較ではない。

## 仕様からの逸脱と理由

Amendment 3の指定範囲を実装し、元本文のD全PASS要求は、既知のD preflight失敗を保持する後続Amendmentの終端分類に従った。force符号、窓、sampling、watchdog、BLOCKED／wall abortの閾値とエラー伝播は変更していない。

今回のrenderとcommit/pushを行わないのはユーザーが明示した二段階手順による。結果側pytestだけをMetal除外・cacheprovider無効・cap無しで完走する方針とし、baseを再採取しない。既存builderを使い、必要のないbuilder変更は加えていない。

OpenCode Go MCPは公開ツールになく、CLIも通常ログのsandbox書き込み失敗後、一時XDG_DATA_HOMEで`Provider not found: opencode-go`。インフラ利用不可として、設定／認証／追加課金を変えずnative workerに分担し、親が差分と実記録を確認した。hostのprocess一覧取得もsandboxからoperation not permittedで拒否されたため、resource auditにこの境界を記録し、CPU preflightは逐次実行した。

## 未確認の仮定

T4上のcompile、20-step有限性、登録窓[80,120]のboundedness、同じλでの±ε FD一致、wall、VRAMは未測定。CPU preflight、合成ラベルテスト、独立source reviewはBOUNDED_ALL／AGREEの測定結果ではない。将来のBOUNDEDも指定sampling/watchdogでの記述的判定で、連続時間・全状態の数学的有界性の証明ではない。qualification flagsはすべてfalse。

Eは版全体の記述的比較である。jobはuλ/u0やmom_project!を直接呼ばないためadapterは不要だったが、sim_step!経由のprojection weights/source/BC、Poissonの既定tol（1e-4→2e-3）／停止条件、force reductionが異なる。両版のQUICKは内側boundを保持しており、Eでmedianだけの因果分離はできない。

CPU1.8のForwardDiffは1.4.6、T4と1.10は1.4.5。Fには同じCPUのFloat32対照を保持し、analyzerはbackend／runtimeの差を出力する。E/FとCPU対照全体の60 CPU hはoperatorが合計で管理するbudgetで、wrapperのtimeout上限は1呼び出しあたり60 h。今回full-window CPUを始めていない。

## Claude／ユーザーへの提案する追記

1. PR #86の本文をこの実装と検証に合わせる。authorityへ追記するなら、PREFLIGHT_BLOCKED／ARM_ERROR、D′を含む次段候補、方向ラベル優先順位、E/FのCPU7-run、write-onceのrunbookを、指定review worktreeのAmendment 1・2と整合させる。
2. CPU20-stepのPASS、Dの既知非有限、Float64圧力tangentの大きさと局在をsoftware evidenceとして記録する。GPU／登録窓の結果や勾配資格に読み替えない。
3. GEN-01のv18記述との相違はauthority側で整理する。本実装とreferenceはv17の登録bytesを使用し、phase_plan／STATE／仕様本文は変更していない。

## 次に要るもの（Claudeのhost作業、ユーザー向けrunbook）

まず完全なcommit対象一覧を確認し、実装と記録を通常commit/pushする。source commitは実装とreferenceを含む40桁SHAで、測定終了まで`origin/feat/gen01-w1-03-grad00`上で到達可能に保つ（squash／削除しない）。その後、hostで次を実行して5 kernelを再生成し、生成物を別commitにする。今回は下記を実行していない。

```bash
.venv/bin/python scripts/grad00_reference_from_fd08.py --check
GRAD00_SOURCE_COMMIT=$(git rev-parse HEAD)
.venv/bin/python scripts/build_grad00_kernels.py \
  --source-commit "$GRAD00_SOURCE_COMMIT" \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json
```

reference付きrenderは既存5ディレクトリのrunner/metadata/timeoutを上書きできる。source/pins/reference/runtime/timeoutを確認する。EのT4 kernelは作らない。探索のidentityと実行判断を記録した後、ユーザーがA–Dを実行するためのコマンドは次のとおり。

```bash
kaggle kernels push -p infra/kaggle/kernel_grad00_quick --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_quick_nobound --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_cds --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_vanLeer --timeout 10800
```

A–Dの出力を`OUTPUT_ROOT/<arm>/`に回収し、実行時pinと一致するbytesのanalyzerで、まずcheckだけを行う。ERROR出力にも`run_identity.json`と`output_manifest.json`をそのまま残す。凍結5-run verifierを13/7-run腕に流用しない。

```bash
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json --check
```

表示される`vanLeer_safe_run_condition.met`は「B・Cがともに全4方向BOUNDEDかつAGREEではない」の計算結果。これを見て人がD′の実行を決める。条件を満たして人が選んだ場合だけ、再生成済みD′ kernelをpushする。

```bash
kaggle kernels push -p infra/kaggle/kernel_grad00_vanLeer_safe --timeout 10800
```

Eは任意のCPU1.10/quick/Float32、FはCPU1.8のA/B×Float32/Float64。いずれもD0/D1の7 runで、`scripts/run_grad00_cpu.py`の`--project`／`--arm`／`--real-type`／`--source-commit`／`--reference`／`--output-dir`／`--timeout-s`で起動する。全体60 CPU hの残りから個別timeoutを割り当て、結果ディレクトリをcampaign直下に置く。Eは例えば`quick_110`、Fは`quick_cpu_f32`等で識別でき、analyzerは内部identityを検証する。未実行のD′とEはNOT_RUN、途中で終わった認証済み出力はARM_ERRORになる。

D′の判断と任意E/Fの実行・不実行の判断がすべて済み、宣言した全腕が終端になってから、最後に1回だけwriteする。途中の判断には何度でもcheckを使い、final analysisを先に書かない。

```bash
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json \
  --write OUTPUT_ROOT/analysis.json
```

TA1の実測plainは138.857970953 s（loop106.642483 s）。9 plain＋4 bounded Dualをplainの2–3倍と仮定すると39.3–48.6分＋setup/JIT。早期BLOCKEDのDualをfull-windowの速度実績に読み替えていない。

| 腕 | 予想GPU時間 | 予算上の扱い |
| --- | --- | --- |
| A quick | 39–49分＋setup/JIT | 約1 T4 h |
| B quick_nobound | 39–49分＋setup/JIT | 約1 T4 h |
| C cds | 39–49分＋setup/JIT | 約1 T4 h |
| D vanLeer | full-windowなら同じ予測。CPUと同じpreflight失敗なら測定に進まない | 約1 T4 hの枠 |
| D′ vanLeer_safe | 39–49分＋setup/JIT、条件付き | 約1 T4 h |
| E 1.10 quick | GPUを使わない | F／対照と合わせて60 CPU h |
| F A/B Float32/Float64 | GPUを使わない | Eと合わせて60 CPU h |

A–D′合計は標準予算約5 T4 h、8×wall abortを踏むworst caseは約8–10 h、10 GPU h capを延長しない。timeout10800 sはTA1と同じsetup/JITを含む余裕上限で、目標実時間ではない。

## commitすべきファイルの完全な一覧

今回のdeltaは計164ファイル（既存9ファイルの修正と新規validation記録）。同じ一覧を`wp03_validation/amendment3/COMMIT_FILES.txt`に保存した。既存kernelや既存Manifestは含まない。

```text
docs/codex/gen01_w1_2026_11_06/reports/wp03_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_report.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily110_quick_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_cds_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_Float64/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_quick_nobound_Float64/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/CFDSDFWaterLily_vanLeer_safe_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/COMMIT_FILES.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/README.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/SHA256SUMS
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/compileall.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/compileall_result.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/cpu_launcher.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/cpu_results.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/cpu_summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/focused.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/focused_checks.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/frozen_semantics_audit.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/instantiate110.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/integrity_audit.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/integrity_audit.py
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/package_checks.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/protected_after.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/protected_before.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/pytest_focused.xml
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/pytest_full.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/pytest_full.xml
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/pytest_full_command.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/pytest_full_result.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/run_cpu_validation.py
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/run_full_pytest.py
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/selftest110.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/selftest180.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/source_review.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/summarize_cpu.py
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D0_interface_offset__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/D1_filtered_seed11__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/SYNTHETIC_NO_FLOW
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/plain.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/plain.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily110_quick_Float32/synthetic_manifest.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D0_interface_offset__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/D1_filtered_seed11__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/SYNTHETIC_NO_FLOW
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/plain.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/plain.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_Float64/synthetic_manifest.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D0_interface_offset__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11.watchdog.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11__minus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11__minus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11__plus.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/D1_filtered_seed11__plus.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/SYNTHETIC_NO_FLOW
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/plain.history.csv
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/plain.summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/synthetic/CFDSDFWaterLily_quick_nobound_Float32/synthetic_manifest.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_bit_comparison.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_capture_execution/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_capture_execution/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_plain_capture_execution/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_plain_capture_execution/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_plain_reference/quick_plain_control.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_plain_reference_capture.jl
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_reference/quick_control.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_reference_capture.jl
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/validation_result.json
scripts/analyze_grad00.py
scripts/grad00_orchestration_selftest.jl
scripts/run_grad00_cpu.py
scripts/waterlily_grad00_lambda_2026_11.diff
scripts/waterlily_grad00_lambda_2026_11.jl
tests/test_grad00.py
tests/test_grad00_cpu.py
```
