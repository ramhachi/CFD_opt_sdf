# WP3 GRAD-00 報告（Amendment 2）

## 状態

**PARTIAL。Amendment 2 の実装と個別検証は完了。元の受け入れ条件「A–D の全4腕の preflight PASS」は stock vanLeer の非有限により未達。**

開始 HEAD は `0b226184`（直下に `383e37e9`、`ae978d5d`）、branch は `feat/gen01-w1-03-grad00`、開始時の作業ツリーはクリーンだった。Claude が commit 済みの reference を変更せず、D′ `vanLeer_safe`、reference の実ファイルテスト、analyzer、builder の上書き経路を追加した。

A/B/C/D′、1.10 quick、Float64 A/B の20-step CPU preflight は通過した。D は plain が有限、Dual の値と partials が非有限となり、`INCOMPLETE`、exit 2 を保持した。D′ は plain の u/p が D の plain 対照と bit-equal、Dual は有限。quick は同じ型・経路の凍結 TA1 と通常 plain／Dual の値成分の両方で u/p が bit-equal だった。

結果側の全体 pytest は **3657 passed、74 skipped、7295 warnings、exit 0**、1428.66 s（23分48秒）で完走した。失敗 node 集合は **空 `[]`**。実行中の対象 source の SHA は不変。base は指示どおり取り直しておらず、Claude の host baseline との同一性は host 側で照合する。

今回の呼び出しでは commit/push、PR #86 の更新、Kaggle、GPU、本測定用 `analysis.json`、`infra/kaggle/kernel_grad00_*/` の変更を行っていない。実装後に Claude が host で commit/push し、その commit に pin して5 kernelを再生成する二段階の手順に従う。

## 作ったもの（今回 commit すべきファイルの完全な一覧）

以下は開始 HEAD からの今回の変更・追加のみ。既存の `quick_nobound.jl`、CPU launcher、WaterLily 1.10 project はそのまま再利用して検証した。既存4 kernelは古い UNCONFIGURED bytes のままで、今回の commit 対象には含めない。

今回の commit 対象は **92ファイル**。同じ一覧を `wp03_validation/amendment2/COMMIT_FILES.txt` に保存した。

```text
docs/codex/gen01_w1_2026_11_06/reports/wp03_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_report.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily110_quick_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_cds_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_Float64/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_quick_nobound_Float64/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/g2_run_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/grad00_index.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/CFDSDFWaterLily_vanLeer_safe_Float32/preflight.progress.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/COMMIT_FILES.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/README.md
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/SHA256SUMS
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/compileall.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/cpu_launcher.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/cpu_results.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/cpu_summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/focused.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/focused_checks.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/frozen_semantics_audit.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/instantiate110.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/protected_after.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/protected_before.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/pytest_focused.xml
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/pytest_full.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/pytest_full.xml
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/pytest_full_command.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/pytest_full_result.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/reference_audit.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/run_cpu_validation.py
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/selftest110.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/selftest180.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_bit_comparison.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_capture_execution/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_capture_execution/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_plain_capture_execution/execution.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_plain_capture_execution/output.txt
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_plain_reference/quick_plain_control.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_plain_reference_capture.jl
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_reference/quick_control.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/ta1_reference_capture.jl
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/validation_summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment2/waterlily_source_audit.json
scripts/analyze_grad00.py
scripts/build_grad00_kernels.py
scripts/grad00_selftest.jl
scripts/vanleer_safe.jl
scripts/waterlily_grad00_lambda_2026_11.diff
scripts/waterlily_grad00_lambda_2026_11.jl
tests/test_grad00.py
tests/test_grad00_kernels.py
tests/test_grad00_reference.py
```

`wp03_validation/amendment2/` は software/input-integrity/短時間CPU検証の記録である。各プロセスのコマンド、環境、exit、wall、source と artifact の SHA、失敗も含む index と raw log を保持する。過去の capped 試行は旧ディレクトリに残した。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

`quick_nobound` は元の単一式 `median((5c+2d-u)/6,c,d)` のまま。新しい `scripts/vanleer_safe.jl` は次の式を `Base.include(WaterLily, path)` で読み込む。

```julia
vanLeer_safe(u,c,d) = ForwardDiff.value(d) == ForwardDiff.value(u) ? c : vanLeer(u,c,d)
```

job は `GRAD00_ARM=quick|quick_nobound|cds|vanLeer|vanLeer_safe` を constructor の `λ` に渡し、`typeof(sim.flow.λ)` を検査する。D′ の型文字列は `typeof(WaterLily.vanLeer_safe)`。TA1 の11引数に D0/D1/D2/P1 の ε [m] を4個加えた15引数、Float32 は shared plain 1本＋4方向の Dual/plus/minus、計13 run。Float64 は CPU の A/B、D0/D1、計7 run。`g2_run_index.json` と `grad00_index.json` の名前と、run ごとの窓平均・SHA・watchdog・onset・wall・VRAM の記録方法を保持した。

D′ の20-step preflight は `selected_dual`、`selected_plain`、stock の `vanLeer_plain`。`vanLeer_primal_u_bit_equal` / `vanLeer_primal_p_bit_equal` は selected plain と stock plain の SHA 比較を記録し、pass 条件にする。Dual と plain 同士の bit identity は追加の条件にしていない。すべての経路に有限性を要求する。

reference は `docs/evidence/grad00_lambda_2026_11/reference.json` を必須入力とする。ε は4方向共通 `0.003971641173621408 m`、spread は Model A の `se_g_n_per_m`（fx=drag、fz=downforce）。analyzer 内の fz は raw force on body、downforce は −fz。SE の大きさには符号反転を要しない。比較の主対象は各 λ の ±ε で求める中心差分で、旧 FD-08 Model A の方向微分は記述的参照として別に保持する。

```bash
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json --check
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json \
  --write OUTPUT_ROOT/analysis.json
```

各出力を `OUTPUT_ROOT/<arm>/` に置く。A–D は引き続き必須。D′ が無い場合は `NOT_RUN` とし、存在するが空・破損・未完了の場合は拒否する。D′ の実行条件は analyzer に入れていない。方向の `BOUNDED/BLOCKED`、`AGREE/DISAGREE/NOT_EVALUABLE`、腕の `BOUNDED_ALL/PARTIAL/BLOCKED_ALL`、Aとの差、F32/F64差、write-once を保持する。閾値は `0.1`、`3×spread`、strict `>1e30` のまま。

次段候補は仕様 §5 が明示する **B–D のまま**。D′ の追加だけを理由に候補集合を拡大しない。D′ は同じラベルを集計するが `next_step_eligible=false`。D′ を次段候補に含める意図なら、Claude／ユーザーが仕様の候補範囲を明記する必要がある。

builder は5腕を扱い、新 helper と reference generator を source pin に追加した。reference 付きなら既存ディレクトリ内の `runner.py`、`kernel-metadata.json`、`timeout` を上書きでき、UNCONFIGURED からの更新も許す。他のファイルは保持する。reference を再検証し、committed source bytes を照合し、全5腕の runner／metadata を生成してから書く。reference 無しの render は既存ディレクトリを拒否する。default は `infra/kaggle/`。今回のテストでは ROOT を tmp_path に差し替え、実 infra は変更していない。

## テスト（コマンドと結果、base との比較の扱い）

- `.venv/bin/python -m pytest -q tests/test_grad00.py tests/test_grad00_reference.py tests/test_grad00_kernels.py tests/test_grad00_cpu.py -p no:cacheprovider`：**175 passed**、9.36 s。`test_grad00.py` 104件、reference 5件、builder 37件、CPU wrapper 29件。実際の command/JUnit は `amendment2/focused_checks.json` / `pytest_focused.xml`。
- reference の実ファイル受理、generator `--check` exit 0、両出典それぞれ1 byte の改変拒否、全方向共通の正の ε ≤5 mm を検証した。凍結出典は変更せず、改変テストは tmp_path のコピーで行った。
- builder の default 出力先での configured／UNCONFIGURED 上書き、繰り返し、余分なファイルの保持、reference/source/5番目のrender/metadataの失敗前無書き込み、source commit 検証を合成データで確認した。
- `julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/grad00_selftest.jl` と 1.10 project の同じコマンド：ともに **120/120 PASS**。等値端点の Dual は c 本体と partial を返し、Float32/64 の seeded plain 入力でも stock vanLeer と bit identity を確認した。
- `julia --startup-file=no --project=julia/CFDSDFWaterLily110 -e 'using Pkg; Pkg.instantiate(;allow_autoprecomp=false)'`：**exit 0**、Project／Manifest の SHA 不変。wall は採取していない。
- `.venv/bin/python -m compileall src tests`：**exit 0**。`git diff --check`：**exit 0**。
- TA1 の `load_raw/sample_row/window_mean/summarize/tangent_max/history_header`、測定定数、CPU-only window hook、BLOCK_LIMIT の bytes を照合した。コピー元との差分ファイルは stable labels・zero-context unified diff の再生成と完全一致した（`frozen_semantics_audit.json`）。
- FD-08 の4 direction raw は Fortran-order SHA と、正式 criteria の C-order SHA の双方が一致した。選択 ε の plus/minus、計8個の生成 Float32 field も正式記録の SHA と一致した（`reference_audit.json`）。
- 保護対象24ファイルは開始時から SHA 不変。T4 の Project／Manifest と凍結 TA1 builder/template も HEAD と byte-equal。authority 本文、凍結 source/evidence、既存生成 infra は変更していない（`protected_before.json` / `protected_after.json`）。

CPU コマンドは `amendment2/run_cpu_validation.py` で再現可能。`julia --startup-file=no -O2 -t 10`、`G2_BACKEND=cpu G2_DRYRUN_T_END=0.4 TA1_PREFLIGHT_ONLY=1`、BLAS/OpenMP 各1 thread、全 ε は committed reference の値、各 phase 20 steps。各プロセスは480 s safety limit、実時間は62–145 sだった。全体 pytest にはこの limit を付けていない。

| 対象 | 20-step preflight | exit | wall |
| --- | --- | ---: | ---: |
| A / 1.8 quick / Float32 | PASS | 0 | 98.88 s |
| B / 1.8 quick_nobound / Float32 | PASS | 0 | 69.85 s |
| C / 1.8 cds / Float32 | PASS | 0 | 86.93 s |
| D / 1.8 vanLeer / Float32 | FAIL / INCOMPLETE | 2 | 96.44 s |
| D′ / 1.8 vanLeer_safe / Float32 | PASS | 0 | 121.05 s |
| E / 1.10 quick / Float32 | PASS | 0 | 62.20 s |
| F-A / 1.8 quick / Float64 | PASS | 0 | 145.26 s |
| F-B / 1.8 quick_nobound / Float64 | PASS | 0 | 75.37 s |

D′ の plain/control u SHA は `9f3bdc221029a4d0a0c9400458c772c3e15233e6753d3e0b310fe6184efc2783`、p SHA は `235a774656ec82a5d757256cacc5a47206ff1af20c95356d4150799df7a5f072`。Dual の最大 |tangent| は u=24.481000900268555、p=32.0726432800293。これらは20-step preflightの値であり、登録窓での有界性ではない。

凍結 TA1 を編集せず、既存 capture wrapper の出力先だけを今回の記録先へ替え、実際の build と20 stepsを別プロセスで走らせた。quick-Dual の値成分と通常 Float32 plain を、それぞれコピー側の同じ経路と比較し、u/p の全 SHA が一致した。capture wall は Dual 52.94 s、plain 43.14 s。wrapper/source/runtime と比較の SHA は `ta1_bit_comparison.json` に保存した。

全体 pytest は次のコマンドに JUnit 出力だけを加え、時間 cap 無しで実行した。

```bash
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
```

失敗 node 集合：`[]`（failures=0、errors=0）。結果は **3657 passed、74 skipped、7295 warnings**。`pytest_full.txt`、`pytest_full.xml`、`pytest_full_command.json`、`pytest_full_result.json` を保存した。base は実行していないため、失敗集合の host baseline との一致を今回の結果だけからは断定していない。

## 仕様からの逸脱と理由

- A–D 全腕の preflight PASS は未達。D の plain は有限でも Dual は非有限になる。式・閾値・失敗伝播を変更せず記録し、D′ の成功で D の結果を置換していない。D の preflight 失敗は登録窓の `BLOCKED` 測定ではなく、`INCOMPLETE`。
- 今回の既存実装ファイルへの変更は Amendment 2 が指定した追加・修正に限定した。新たな依存、既存 Manifest の変更、凍結 source の編集はない。
- Amendment 2 の指定により、base pytest は取り直さず、結果側だけを Metal test file 除外・cacheprovider 無効・cap 無しで完走させる。base との同一性は host baseline との照合を Claude に渡す。
- kernel の実 render と commit/push は今回の作業外。既存 UNCONFIGURED 生成物を変更せず、builder の機能とテストを完成させた。これは二段階手順への変更である。
- OpenCode Go MCP は公開ツールに無く、CLI のモデル照会も通常ログの sandbox 書き込み失敗後、一時 XDG_DATA_HOME で `Provider not found: opencode-go`。global 設定や追加課金は変更せず、native worker に調査・実装を分担し、親が差分と実検証を確認した。

## 未確認の仮定（本測定で初めて分かること）

GPU 上の compile・20-step有限性・登録窓の tangent・同じ λ の FD 一致・wall・VRAM は未測定。CPU preflight や合成ラベルテストは `BOUNDED_ALL/AGREE` の測定結果ではない。将来の `BOUNDED` も登録した sampling/watchdog に基づく記述的ラベルで、時間全域の数学的有界性の証明ではない。全 qualification flags は false のまま。

1.10 job は `uλ/u0`、Poisson tol、`mom_project!` を直接呼ばないため adapter は不要だった。ただし `sim_step!` 経由で Poisson の既定 tol（1e-4→2e-3）、停止条件、projection weight/BC/source、force reduction が変わる。1.10 の `ic_kwarg(u0,uλ)` には deprecated alias も残っている。両版の stock QUICK は `10c−9u` bound を保持する。E は median だけの因果分離にはならない（`waterlily_source_audit.json`）。

既存1.8 CPU の ForwardDiff は1.4.6、T4と1.10は1.4.5。CPU F32/F64 の対照でも runtimeを記録し、GPUとの比較を精度だけの効果として扱わない。Fの登録窓・Eの本測定は今回行っていない。既存 CPU launcher は source/reference を pin する A/B precision・E 用の interface として保持した。

## Claude／ユーザーへの提案する追記

1. 仕様実ファイルは現在 rev 0 で、今回の prompt が参照する Amendment 1 本文は未収録。reference の ε/spread と D′ の式・実行条件を authority 側へ反映する際、D′ を次段候補に含めるかも明記する。今回の analyzer は明示された §5 の B–D を維持する。
2. GEN-01 plan の GRAD-00 の v18 記述は、今回の v17/flow_24 仕様と不一致。今回の実装・入力は v17 の登録済み bytes に統一した。authority の修正は Claude／ユーザーが行う。
3. exploratory record へ書くなら「20-step CPU software preflight: A/B/C/D′/E/F pass、D nonfinite」と evidence class を付ける。GPU BOUNDED/AGREE として登録しない。GPU でも D が preflight 失敗した場合の扱いは実行・解析前に判断する（現在の analyzer は A–D の完備した terminal evidence を要求する）。

## 次に要るもの（Claude の host 作業、ユーザー向け実行手順）

Claude が上記の意図した全ファイルを確認し、reference と D′ の実装を含む commit を通常 push する。その後、同じ source bytes の checkout で以下を実行する。source commit は remote から取得可能な40桁 SHA。今回の未コミット実装を含まない `0b226184` での render は source pin 検証を通らない。

```bash
.venv/bin/python scripts/grad00_reference_from_fd08.py --check
GRAD00_SOURCE_COMMIT=$(git rev-parse HEAD)
.venv/bin/python scripts/build_grad00_kernels.py \
  --source-commit "$GRAD00_SOURCE_COMMIT" \
  --reference docs/evidence/grad00_lambda_2026_11/reference.json
```

Claude が `infra/kaggle/kernel_grad00_*/` の5 kernel の source/ref/pins/metadata/timeoutを確認し、生成物を別 commit にする。PR #86 の本文更新も Claude が行う。default 出力先の既存 UNCONFIGURED 3ファイルは、この configured render で上書きされる。

以降の Kaggle 操作はユーザー向けの手順であり、Codex は実行していない。必要な exploratory identity と実行判断を先に記録し、A/B/C/D を順に走らせる。D′ は指定の「B・C がともに全方向 BOUNDED かつ AGREE でない」という実行条件を人が判断する。

```bash
kaggle kernels push -p infra/kaggle/kernel_grad00_quick --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_quick_nobound --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_cds --timeout 10800
kaggle kernels push -p infra/kaggle/kernel_grad00_vanLeer --timeout 10800
# D′ は人が実行条件を判断した場合のみ
kaggle kernels push -p infra/kaggle/kernel_grad00_vanLeer_safe --timeout 10800
```

terminal 出力の実ディレクトリを `docs/evidence/grad00_lambda_2026_11/<arm>/` に回収し、source pin と同じ bytes の analyzer で `--check`、次に未作成の `analysis.json` へ `--write` を一度だけ行う。preflight INCOMPLETE/ERROR を BLOCKED/DONE に読み替えない。E は1.10 project、F は CPU 10 threads の別測定であり、上の5 primary kernelには含まない。

TA1 の実測 plain は `138.85797095298767 s`（loop `106.64248299598694 s`）。9 plain＋4 bounded Dual を plain の2–3倍と仮定すると39.3–48.6分＋setup/JITになる。これは予測であり、TA1の早期BLOCKED Dualをfull-windowの速度実績として使っていない。

| 腕 | GPU時間の予測 | 予算 |
| --- | --- | --- |
| A quick | 39–49分＋setup/JIT | 約1 T4 h |
| B quick_nobound | 39–49分＋setup/JIT | 約1 T4 h |
| C cds | 39–49分＋setup/JIT | 約1 T4 h |
| D vanLeer | full-windowなら39–49分＋setup/JIT。preflight失敗時は測定へ進まない | 約1 T4 h |
| D′ vanLeer_safe | 39–49分＋setup/JIT、条件付き実行 | 約1 T4 h |
| E 1.10 quick | 記述的な同じ予測。版差による実時間は未測定 | 約1 T4 h |
| F Float64 A/B | GPUを使わない | 元の60 CPU h cap |

A–D は約4 T4 h、D′ も実行すれば約5 h、Eも含めた最大構成は約6 hの予算で、元の10 GPU h capは延長しない。各kernelの `10800 s` はTA1と同じsetup/JIT込みの余裕上限で、目標実時間ではない。
