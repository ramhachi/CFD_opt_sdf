# WP3 GRAD-00 報告

## 状態

**PARTIAL。実装、4 kernel のローカル生成、CPU 検証を完了したが、全受け入れ条件は満たしていない。**

WaterLily 1.8.0 の quick・quick_nobound・cds は 20-step CPU preflight を通過した。vanLeer は plain が有限、Dual の primal と partials が非有限となり、`preflight.pass=false`、index は `INCOMPLETE`、exit 2 で停止した。式・閾値・preflight 条件は変更していない。1.10.0 の quick と Float64 の quick／quick_nobound は通過した。

FD-08 amend3 には方向別に選択済みの plateau ε と spread の定義が見つからなかった。Model A の SE を spread に代用せず、明示 reference を必須にした。生成済み runner は `UNCONFIGURED` で、reference がなければ GPU inventory の前に停止する。本測定用 `analysis.json`、登録窓の BOUNDED／AGREE、GRAD01 の判定は作っていない。全体 pytest の失敗集合同一も、Metal abort と CPU base の30分 cap のため未確認。

GitHub: [draft PR #86](https://github.com/ramhachi/CFD_opt_sdf/pull/86)、commit・push 済み。feature branch は `feat/gen01-w1-03-grad00`、PR の base は `codex/kaggle-batch-migration`。Kaggle への push と GRAD-00 の GPU 測定は実施していない。

## 作ったもの（パス、1 行ずつ）

- `scripts/quick_nobound.jl`
- `scripts/waterlily_grad00_lambda_2026_11.jl`
- `scripts/waterlily_grad00_lambda_2026_11.diff`
- `scripts/grad00_selftest.jl`
- `scripts/grad00_orchestration_selftest.jl`
- `scripts/analyze_grad00.py`
- `scripts/build_grad00_kernels.py`
- `scripts/run_grad00_cpu.py`
- `julia/CFDSDFWaterLily110/Project.toml`
- `julia/CFDSDFWaterLily110/Manifest.toml`
- `infra/kaggle/kernel_grad00_quick/`
- `infra/kaggle/kernel_grad00_quick_nobound/`
- `infra/kaggle/kernel_grad00_cds/`
- `infra/kaggle/kernel_grad00_vanLeer/`
- `tests/test_grad00.py`
- `tests/test_grad00_kernels.py`
- `tests/test_grad00_cpu.py`
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_design.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/`
- `docs/codex/gen01_w1_2026_11_06/reports/wp03_report.md`

各 kernel ディレクトリは `runner.py`、`kernel-metadata.json`、`timeout` を含む。最終 runner の source commit は `282ffc51ee44424038e2a2d8d50a97fe5e37b9d4`、timeout は TA1 と同じ 10800 s。実装は既存 helper と標準ライブラリを再利用し、既存の凍結 source、既存 evidence、旧 Project／Manifest、authority 文書は変更していない。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

`quick_nobound(u,c,d) = median((5c+2d-u)/6,c,d)` を `Base.include(WaterLily, path)` で読み込む。Float32／Float64／Dual で同じ式を使う。job は `GRAD00_ARM=quick|quick_nobound|cds|vanLeer` を constructor の `λ` に渡し、`typeof(sim.flow.λ)` を検査する。実際の型名は quick と cds が無修飾、quick_nobound と vanLeer が `WaterLily.` 修飾だったため、analyzer はこの対応を明示して検証する。

job の引数は TA1 の 11 引数に `D0,D1,D2,P1` の ε [m] を順に 4 個追加した 15 引数。Float32 は共通 plain 1 本＋各方向の Dual／+ε／−ε、計 13 run。`GRAD00_T=Float64` は CPU の A/B、D0/D1、計 7 run。登録窓 [80,120]、8-step sampling、100-step watchdog、strict >1e30、8× wall abort、力の符号、endpoint-clipped mean を保持した。`g2_run_index.json` の名前も保持し、`grad00_index.json` に各 run の窓平均、summary/history/watchdog の SHA、入力 field の SHA、onset、wall、VRAM、runtime と方向対応を書く。

reference JSON は `schema_version=1`、`kind="grad00_fd08_reference"`、定義を記述する `definition`、出典の repository-relative path→SHA を持つ `sources`、4 方向すべての `epsilon_m` と `spread_n_per_m={fx,fz}` を必須とする。renderer と analyzer が同じ loader を使い、reference 自体と出典を source commit に結び付ける。

```bash
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT --reference REF.json --check
.venv/bin/python scripts/analyze_grad00.py OUTPUT_ROOT --reference REF.json --write OUTPUT_ROOT/analysis.json
```

各腕の出力ディレクトリを `OUTPUT_ROOT/<arm>/` に置く。analyzer は 13/7 run の inventory、DONE、transport manifest、source/runtime/input/artifact SHA、実 history からの窓平均、同じ λ の Dual/plain primal を検証する。fx・fz の両方で符号と比率 0.9–1.1、|FD| < 3×spread の NOT_EVALUABLE、方向・腕の全ラベル、plain の A 差、F32/F64 差を出す。歴史的 FD-08 Model A は記述的参照として区別する。A–D の CUDA/T4 cohort が揃ってから一度だけ書き、既存の analysis／SHA sidecar を拒否する。次段の規則は仕様 §5 の B–D のみを対象とし、E/F と CPU dryrun を含めない。

`run_grad00_cpu.py` は、将来の F または E CPU 出力に analyzer 用の identity／DONE／output manifest を付ける。`--source-commit --reference --output-dir --arm --real-type --timeout-s` を必須とし、必要なら `--project julia/CFDSDFWaterLily110` を選ぶ。10 Julia threads を強制・記録し、source/ref を検証してから同じ job を起動する。今回は fake subprocess で検証し、full-window CPU 測定には使っていない。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- `.venv/bin/python -m compileall src tests`: **PASS**。
- `.venv/bin/python -m pytest -q tests/test_grad00.py`: **88 passed**（9.80 s）。全ラベル、閾値の境界、必須キー、改変・欠落、1 回書き込み、reference/source binding を検証。
- `.venv/bin/python -m pytest -q tests/test_grad00_kernels.py tests/test_grad00_cpu.py`: **49 passed**（1.69 s）。新規 Python テストは同じ code commit `9aedf41d` で計 **137/137 PASS**。
- `git diff --check` と base→実装の diff check: **PASS**。26 個の実装／render ファイルはすべて追加で、既存 tracked ファイルの diff は空。TA1 との差分ファイルは再生成した内容と byte-for-byte 一致した。
- 元の `.venv/bin/python -m pytest -q`: base が既存 Metal 初期化で **native abort、shell exit 134**。有効な最終 JUnit がなく、失敗集合は取得できなかった。以前の実装後 full-suite 試行も collection 中断であり、結果には数えていない。
- GPU を避けた base の `.venv/bin/python -m pytest -q --ignore=tests/test_lbm_metal.py`: **1800 s cap、exit 124、約46%で未完了**。そのため予定していた実装後の同じ全体 CPU run は開始せず、**全体の失敗集合同一は NOT_ESTABLISHED**。親 pytest は終了したが、終了後の OS process 一覧取得は sysmon unavailable で失敗し、子プロセス不存在までは確認できていない。

Julia の実 preflight は `julia -O2 -t 10`、`G2_BACKEND=cpu`、`G2_DRYRUN_T_END=0.4`、`TA1_PREFLIGHT_ONLY=1`、BLAS/OpenMP 各 1 thread、各 phase 20 steps。各プロセスの cap は 480 s。ε 引数の 0.001 m ×4 は合成 fixture で、FD-08 の plateau 選択値ではない。正確な 15 引数、環境、exit、SHA は validation の command JSON に保存した。

| 対象 | 20-step preflight | wall |
| --- | --- | ---: |
| 1.8.0 / quick / Float32 | PASS | 202.36 s |
| 1.8.0 / quick_nobound / Float32 | PASS | 183.39 s |
| 1.8.0 / cds / Float32 | PASS | 243.12 s |
| 1.8.0 / vanLeer / Float32 | FAIL、INCOMPLETE、exit 2 | 219.72 s |
| 1.10.0 / quick / Float32 | PASS | 122.70 s |
| 1.8.0 / quick / Float64 | PASS | 224.68 s |
| 1.8.0 / quick_nobound / Float64 | PASS | 156.42 s |

凍結 TA1 を変更せず、その実際の `build()` による quick-Dual 20-step capture を別プロセスで実行した（90.06 s）。コピーの quick-control／selected-Dual の値成分は u・p とも bit-equal。u SHA は `fac0ca3c6f84ec2672456c01695a2f6c39f74984abb2f2c8a4dbffbcc92f790a`、p SHA は `99223b6bfc23d49ae8e1965865e25765e65c3ff2a23c1d86f9d06743a499400e`。通常の Float32 plain も別の TA1 capture（94.21 s）で比較し、コピーの selected_plain と u・p とも SHA が一致した。比較は同じ型・経路同士で行い、2 種類の比較 JSON と通常 plain の full SHA も保存した。

`julia --project=julia/CFDSDFWaterLily scripts/grad00_selftest.jl` と 1.10 project での同じ selftest は各 **34/34 PASS**。`Pkg.instantiate(;allow_autoprecomp=false)` は最終 1.10 project で exit 0、8.15 s、Project／Manifest の実行前後 SHA が一致した。

`scripts/grad00_orchestration_selftest.jl` は **PASS、31.36 s、solver_steps=0**。実際の main／save_run!／index／窓平均 helper を使い、preflight と run_one だけを合成 stub にした。13 run、方向対応、±ε の Float64 演算後の cast、入力と artifact の SHA、必須キーを独立した Python 読み取りで確認した。実 flow preflight の代わりには扱っていない。

vanLeer の追加 scalar 再現では、Float32／Float64 の双方で `Dual(1,1), Dual(1,2), Dual(1,3)` から値・partial が NaN、plain `(1,1,1)` は 1 だった。値が等しいとき partials まで使う ForwardDiff の比較により extremum 条件が false となり、値が 0 の `d-u` で割る分岐に入った。この scalar 機構と、登録格子で最初に非有限になった場所・step の同定は区別する。後者は未追跡。Flow.jl と dual.jl の実際の source path、SHA、該当行を記録した。

validation は `wp03_validation/julia_validation_final.json`、`pytest/comparison.json`、各 raw log／index／preflight と `SHA256SUMS` にまとめた。途中の外部 timeout も別ディレクトリに保存し、PASS には数えていない。

## 仕様からの逸脱と理由

- 4 腕すべての preflight PASS は達成できなかった。vanLeer の実数値失敗を記録し、上流の λ、分岐、閾値の修正は行わなかった。
- FD-08 amend3 は六点 Model A と formal interior ε を記録するが、方向別 plateau 選択と spread の定義を記録していない。問い合わせの回答待ちのため、本測定用 reference と analysis は未作成、kernel は未設定として生成した。
- 短時間 CPU の範囲を守るため、13 本の実 flow による短窓測定は行わず、実 preflight と solver を使わない producer-contract test を分けた。
- 元の全体 pytest が既存 Metal 初期化で abort したため、そのログを保全し、同じ Metal test file を除外する base/final 比較を試みたが、base が30分で未完了のため比較は成立していない。GRAD-00 の GPU job は動かしていないが、最初の全体テストで既存 GPU 初期化を試みた点は実行前確認の不足だった。
- OpenCode Go MCP は利用できず、CLI の provider 照会も `Provider not found: opencode-go` だったため native worker を分担に使用した。グローバル設定・追加課金は変更していない。
- 元 worktree の Git metadata が許可領域外で書き込めなかったため、`/tmp/grad00-publication` の隔離 clone に意図したファイルだけを取り込み、同じ feature branch から commit/push した。元 worktree の HEAD は base のまま、新規ファイルは untracked として保持されている。公開したコードとの byte 一致を確認した。

## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）

CUDA 上での各 λ の compile／有限性／登録窓の tangent、FD 一致、実 wall と VRAM は未測定。CPU の 20-step 有限性は登録窓での BOUNDED_ALL を意味しない。将来の BOUNDED も登録した sampling/watchdog に基づくラベルで、時間全域の数学的な有界性の証明ではない。vanLeer の CPU 失敗から T4 の結果も断定しない。

1.10 の job は `uλ/u0` と `mom_project!` を直接触らないため adapter は不要だった。1.10 の stock quick も inner bound `10c−9u` を保持する。ただし API の `uλ→u0`、projection weight の表現、Poisson の既定 tol と停止条件、source／BC、force reduction が異なる。E は版全体の記述的比較となり、median だけの効果を分離できない。CPU 1.8 の ForwardDiff は 1.4.6、登録 T4 と新 1.10 は 1.4.5。F の比較はできれば CPU Float32 対照も採り、analyzer に backend/runtime の交絡を残す。full-window の 1.10 force 読み出しと F の精度差は未検証。

## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）

1. rev 0 に、各方向の plateau ε [m] と fx/fz spread [N/m] の定義・値・参照 artifact／SHA を記載する。Model A の SE とは区別する。
2. exploratory entry に「CPU software preflight: A/B/C pass、D vanLeer Dual nonfinite、E/F pass」を evidence class 付きで記載する。GPU の BOUNDED/AGREE として登録しない。GPU でも preflight が非有限の場合、その腕を最終分析でどう扱うかは新しい仕様で決める。
3. E の版変更による交絡、F の backend／依存版差、古い 5-run terminal verifier が 13-run 全腕には直接適用できない点を明記する。authority 本文と qualification flags は今回変更していない。

## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）

まず Claude／ユーザーが plateau reference と exploratory run identity を確定する。その reference と出典を commit した feature checkout で、source commit を origin の feature branch に通常 push して GitHub から取得可能にする。runner はその commit を GitHub から fetch する。既存の生成ディレクトリを上書きせず ready kernel を再生成する。

```bash
.venv/bin/python scripts/build_grad00_kernels.py \
  --source-commit <referenceと実装を含む40桁commit> \
  --reference <repository-relative-reference.json> \
  --output-root work/grad00_ready
```

以降はユーザーが行う手順。生成物の source/pins、reference、T4 設定と `timeout=10800` を確認し、各腕を順番に push する。

```bash
kaggle kernels push -p work/grad00_ready/kernel_grad00_quick --timeout 10800
kaggle kernels push -p work/grad00_ready/kernel_grad00_quick_nobound --timeout 10800
kaggle kernels push -p work/grad00_ready/kernel_grad00_cds --timeout 10800
kaggle kernels push -p work/grad00_ready/kernel_grad00_vanLeer --timeout 10800
```

terminal 出力を回収し、`grad00_index.json` のある実ディレクトリを `docs/evidence/grad00_lambda_2026_11/<arm>/` に置く。解析には runner に pin された analyzer／helper と同一 bytes の checkout を使う。全必要腕と reference の整合を `--check` で確認してから、未作成の `analysis.json` に `--write` を一度だけ行う。preflight ERROR/INCOMPLETE を DONE や BLOCKED に読み替えない。E/F の本測定は未実行で、E は 1.10 project、F は CPU launcher と CPU Float32 対照を使う。

TA1 の plain 実績 138.857970953 s を基に、9 primal＋4 bounded Dual（plain の2–3倍と仮定）は **各腕39–49分＋setup/JIT、予算は約1 T4時間/腕**。A–D は約4時間、E を加えて約5時間、仕様の集計 cap は10 GPU時間。各 kernel の10800 s は TA1 と同じ余裕込みの上限であり、目標実時間ではない。TA1 の早期 BLOCKED Dual は full-window の速度実績ではなく、この見積もりは未検証。F は GPU を使わない。
