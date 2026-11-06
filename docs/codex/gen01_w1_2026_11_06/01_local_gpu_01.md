# WP1：LOCAL-GPU-01 の道具立て（WSL2 上の RTX 4070 Ti を WaterLily の backend にする環境 gate の実装）

最初に `docs/codex/gen01_w1_2026_11_06/00_README.md` を読み、その規則に従うこと。仕様は `docs/local_gpu_env_gate_2026_11_01.md`（LOCAL-GPU-01、draft rev 0）。手本は `docs/local_openfoam_env_gate_2026_10_20.md`（LOCAL-OF-01）と、その実装 `scripts/local_openfoam.py`、`scripts/local_openfoam_gate.py`、`infra/local_openfoam/`（lock、dpkg list、requirements.lock）、`tests/test_local_openfoam*.py`。

## 目的

ユーザーの Windows 11 機（RTX 4070 Ti、WSL2 の Ubuntu 24.04）で、本リポジトリの **登録済み WaterLily harness の経路をそのまま**（rendered kernel `runner.py` → Julia job → `WaterLily.Simulation`）動かすための道具と、環境のロック、再現性の級、GPU identity、処理量、再開、安定性を計測して判定する gate スクリプトを作る。**Codex は GPU を回さない**。作るのは道具とテストで、実行はユーザーが WSL2 上で行う。

## 必ず読む（全文）

- `docs/local_gpu_env_gate_2026_11_01.md`（仕様）
- `docs/local_openfoam_env_gate_2026_10_20.md` §2〜§7（lock、runs、criteria、repeats の規則）
- `scripts/local_openfoam.py`、`scripts/local_openfoam_gate.py`、`infra/local_openfoam/*`、該当テスト
- `src/cfd_harness/campaign_runner_template.py`（Kaggle runner が前提にする環境：Julia 1.12.6 の SHA、`/kaggle/working`、`/kaggle/input/<slug>`、`CUDA_VISIBLE_DEVICES`、`GPU_EXPECTED`、`used_gpu_count`）、`src/cfd_harness/campaign_verify.py`、`docs/harness/README.md`
- `infra/kaggle/kernel_harness01_replay_a_smoke/`（最小の rendered kernel の実例）と `docs/harness/harness01_replay_campaign.json`
- `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md` §5（WSL2 の事実：Windows ドライバのみ、`/usr/lib/wsl/lib`、`.wslconfig`、KB5127936、NVML）

## 成果物（新規ファイル。既存は編集しない）

1. `infra/local_gpu/README.md`：WSL2 の準備手順（ユーザー向け。Windows 側ドライバ、`wsl --version`、`/etc/wsl.conf` の `[gpu] appendLibPath=true` と `[automount] ldconfig=true`、`.wslconfig` の memory、Ubuntu 24.04、Julia 1.12.6 の tarball を runner template と同じ SHA で検証して展開、`Pkg.instantiate()` を `julia/CFDSDFWaterLily` の Manifest で、`CUDA.functional()` の確認）。**プレビュー更新 KB5127936 を保留**する注意を書く。
2. `infra/local_gpu/capture_lock.py`：WSL2 内で実行し、`infra/local_gpu/lock.json` を生成する。内容：Windows build（`/proc/version` と `cmd.exe /c ver` が取れれば）、WSL version、kernel、distro、`.wslconfig`／`/etc/wsl.conf` の関連キー、`nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap,power.limit --format=csv,noheader`、Julia の版と実行ファイルの SHA-256、`Manifest.toml` の SHA-256、`CUDA.versioninfo()` の出力（Julia を起動して取る）、`CUDA_VISIBLE_DEVICES`、取得日時。欠けた項目は `null` ではなく **取得失敗の理由**を入れ、必須項目（GPU 名、driver、Julia SHA、Manifest SHA）が無ければ非 0 で終了。lock の正準 JSON（キー順固定、改行 1 つ）の SHA-256 を `lock.json.sha256` に書く。
3. `scripts/local_gpu.py`：`scripts/local_openfoam.py` と同じ使い勝手で、rendered kernel の `runner.py` を **無改変で**実行する。サブコマンド：
   - `check-lock`：現在の環境を `capture_lock.py` と同じ方法で取り直し、`lock.json` と一致しなければ非 0（driver や Manifest が変わっていたら走らせない）。
   - `run <kernel_dir> --out <dir> [--dataset <dir>] [--repeat N]`：`/kaggle/working` と `/kaggle/input/<slug>` に相当する場所を用意する。方法は 2 択で、設計メモで選んで理由を書く：(a) `runner.py` が環境変数で出力先を切り替えられるならそれを使う、(b) できないなら WSL2 の中で `/kaggle` を bind mount（`sudo mount --bind`）するスクリプトを添える。**runner.py は編集しない**。`CUDA_VISIBLE_DEVICES=0` を固定。各 run の `local_run.json`（lock SHA、GPU identity、開始・終了時刻、各段の wall、ピーク VRAM（`nvidia-smi --query-gpu=memory.used` の 10 秒ごとの最大）、exit code、`DONE` の有無、出力ファイルの SHA-256）を書く。
   - `watch`：`run` と並行して 60 秒ごとに `nvidia-smi` の clocks.sm、temperature.gpu、power.draw、memory.used を `watchdog.csv` に書く（R6 用）。
   - `bench`：WaterLily の Taylor–Green（`julia/CFDSDFWaterLily` の環境で、WaterLily 1.8.0 の TGV を 128³、Float32、固定 step 数）と 2D の板（仕様 R0）を回し、cell-step/s を出す Julia スクリプト `scripts/local_gpu_bench.jl` を呼ぶ。native Windows 比較は **スクリプトを用意するだけ**（実行はユーザー）。
4. `scripts/local_gpu_gate.py`：仕様 §5 の C1〜C6 を、`docs/evidence/local_gpu_gate_2026_11/` に置かれた出力から **1 回だけ**計算して `gate.json` を書く（書き込み先が存在すれば拒否）。
   - C1：R1a/R1b、R2a/R2b の力 CSV を byte 比較 → `BITWISE`；不一致なら全サンプルの最大相対差 ≤ 1e-6 → `TOLERANCE`；それ以外 `FAIL`。
   - C2：`scripts/harness.py verify --smoke`（既存）を R2 の出力に対して呼ぶ（subprocess）。
   - C3：T4 参照（harness01 smoke の力 CSV `97e7b43c…`、UNC-01 U01 smoke table、SCREEN f32a の親、f48k13）との窓平均の相対差。参照の SHA は `docs/evidence/**` から読む（コピーしない）。記述。
   - C4：R3／R4 の step 数と wall から cell-step/s、T4 錨（5.5e7、5.6e7）との比。記述。
   - C5：R5（kill→resume）の窓統計が R3 と C1 の級で一致。
   - C6：watchdog から clock 低下 < 15 %、非有限値なし、driver reset なし。
   - 判定 `PASS`／`FAIL`（失敗した基準名付き）。欠けた run は `INCOMPLETE`（例外で落とさない）。
5. `julia/CFDSDFWaterLily/src/Checkpoint.jl`（新規モジュール。`CFDSDFWaterLily.jl` に `include` を 1 行足すのは可）：`save_checkpoint(path, sim, step, rows)` と `load_checkpoint(path)`（`sim.flow.u`、`sim.flow.p`、`sim.flow.u⁰`、`Δt` 履歴、時刻、step、力のサンプル行、乱数状態は無し）。JLD2 は Manifest にある（`WaterLilyJLD2Ext`）か確認し、無ければ `Serialization` で。**WP4 の 2D job がこれを使う**ので、インターフェースを設計メモと報告に明記する。再開後の力の窓統計が、中断なしの run と C1 の級で一致することを、CPU の小さい格子（例 2D 64×32、100 step）のテストで確認する。
6. テスト：`tests/test_local_gpu.py`（lock の正準化と SHA、`check-lock` の不一致検出、`run` のスタブ runner（`DONE` を書くだけの偽 runner）での `local_run.json`、gate の全基準を合成データで、欠け run の `INCOMPLETE`、書き込み先の存在拒否）。Julia 側は `scripts/checkpoint_selftest.jl`（CPU、数秒）。

## 受け入れ条件

- `pytest -q tests/test_local_gpu.py` が通り、全体の失敗集合が base と同一。
- `scripts/local_gpu.py run` が、偽 runner で `local_run.json` と `DONE` を書く。
- `capture_lock.py` は GPU の無い Mac でも「必須項目が無い」理由で非 0 で終わる（例外のトレースではなく、整った JSON のエラー）。
- `Checkpoint.jl` の自己テストが CPU で通る。
- 設計メモと報告に、WSL2 でだけ分かる未確認点（起動遅延、NVML の挙動、bind mount の要否）を列挙する。

## やらないこと

- GPU の実行、Kaggle、既存の `runner.py` や Julia job の編集、`Manifest.toml` の変更、native Windows への harness の移植。

## Amendment 1（2026-11-06。1 回目の試みが BLOCKED で止まった 4 つの矛盾への回答。この節が上の本文より優先する。仕様 `docs/local_gpu_env_gate_2026_11_01.md` §10 と同じ内容）

1. **「runner を無改変で」は不可能**（`scripts/grid01_gpu.py` が T4 以外を拒否、`campaign_schema.py` の `GPU_EXPECTED` と `campaign_verify.py` も T4 要求）。→ harness に **backend profile** を足す：新規 `src/cfd_harness/backend_profiles.py`。既定 `kaggle_t4` は今の挙動を byte 単位で再現する（既存 campaign・freeze・rendered kernel は不変。テスト：既存 campaign を既定 profile で render し、commit 済み kernel と byte 一致）。`local_rtx4070ti` は `nvidia-smi` の名前（と、取れれば UUID）と `used_gpu_count = 1` を検査する。ローカル用 kernel は `scripts/local_gpu.py render` で **profile 付きに再 render** し、`verify --smoke` は campaign に記録された profile を受け入れる。runner の identity 検査は迂回せず、profile で通す。`grid01_gpu.py`・`campaign_schema.py`・`campaign_verify.py`・`campaign_runner_template.py` に手を入れる必要があるなら、**既定 profile での出力が byte 不変**であることをテストで示した上で最小限に変える（README の「既存ファイルを編集する場合」の規則に従い、理由を報告に書く）。
2. **既存 campaign の T4 byte gate はローカルの基準にしない。** ローカルでは T4 参照との比較は記述（C3）、gate は同一機の再実行（C1）。ローカル profile は C1 合格後に自分の first-state SHA を参照として記録する。
3. **Julia project。** GPU 実行は登録済みの GPU project `julia/CFDSDFWaterLilyT4`（WaterLily 1.8.0 ＋ CUDA 6.3.1。Kaggle runner と同じ）を使い、lock はその `Manifest.toml` の SHA-256 を pin する。CPU 自己テスト（checkpoint）は `julia/CFDSDFWaterLily`。どちらの Manifest も変えない。
4. **checkpoint／resume を呼ぶ job が要る。** 登録済み job は編集しない。`scripts/waterlily_local_gpu_job.jl` を `scripts/waterlily_lowdim02_flow32_job.jl` の **コピー**として作り、追加は `Checkpoint.jl` の save／resume の呼び出し（周期とパスは環境変数）だけ、force CSV は不変。差分を `scripts/waterlily_local_gpu_job.diff` として commit。R3／R5 はこの job、R1／R2 は既存 job を再 render した kernel で。C5 は R5 と R3 を C1 の級で比較。
5. **道具の注意。** commit は共有の Git dir（`/Users/sota/projects/FomulaTMU/CFD2026_09/.git`。今回の sandbox では書き込み可）に対して行う。PR は `gh pr create`（GitHub の MCP connector は使わない）。1 回目の試みの 3 つの記録（`reports/wp01_local_gpu_01_{design,report}.md`、`wp01_local_gpu_01_validation.json`）は `reports/wp01_attempt1_blocked/` に移して一緒に commit する。
6. 必読文書のうち、`docs/opencode_handoff_2026_09.md`、`docs/problem_register_2026_09.md`、`docs/problem_resolution_plan_2026_09.md` は **目次と該当節（harness、GPU、Kaggle、PROC-01）だけ**でよい。全文通読は不要。

これで矛盾は解消しているはずなので、今回は BLOCKED にせず実装まで進めること。新たな矛盾が見つかった場合だけ、その箇所を具体的に示して止める。

## Amendment 2（2026-11-06。2 回目の試み（PARTIAL、未 commit の 29 ファイル）への回答。この節が本文と Amendment 1 より優先する）

1. **`julia/CFDSDFWaterLily/src` は登録済みの directory pin。** `campaign_build.BASE_PINS` がこのディレクトリの hash（全ファイルの `相対パス  sha256` 行の SHA）を取り、DIAG5／GRID01／GRID02／LOWDIM01／02a／03／STEP01 の freeze がその値を bind している（2 回目に失敗した 10 node はすべてこれ）。したがって **src/ にはファイルを 1 つも足さず、1 byte も変えない。** `CFDSDFWaterLily.jl` への `include("Checkpoint.jl")` は戻す（自分の未 commit 変更を `git checkout -- julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl` で戻すのは許可）。`Checkpoint.jl` は **`julia/CFDSDFWaterLily/gen01/Checkpoint.jl`** に移し、job・selftest・tests から `Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))` で読む（既存 job が `V16PhysicalProfile.jl` 等を `Base.include(CFDSDFWaterLily, …)` している流儀）。`julia/CFDSDFWaterLily/gen01/README.md` に「`src/` は registered directory pin なので GEN-01 の追加モジュールはここに置き、job から `Base.include` する」と 2〜3 行書く。local campaign の kernel `pins` にそのパスを明示し、`check_include_closure` が通ることをテストで示す。以後の WP（FORCE-00 の `Force00.jl` など）も同じ置き場所。
2. **歴史テストの例外は不要・不許可。** 保護テスト（DIAG5／GRID01／GRID02／GRIDRES01／LOWDIM／STEP01 の test file、`tests/conftest.py`）は 1 つも変えない。`tests/test_harness_replay.py` の変更も戻す（1 の後は元のまま通るはず。通らなければ理由を報告して止める）。
3. `campaign_schema.py`／`campaign_build.py`／`campaign_verify.py` の opt-in 変更は維持してよい。ただし `campaign_schema.py` は `BASE_PINS` の 1 つなので、harness v1.1 の登録 freeze（UNC-01／FID-01／SCREEN-01 の prerun_freeze・verify table・`harness_tool_sha256`）に関するテストが全体 pytest で base と同じ結果であることを確認する。失敗が出るなら schema の編集をやめ、`backend_profiles.py`／`scripts/local_gpu.py` 側で `backend_profile` キーを剥がしてから `validate_campaign` に渡し、`expected_summary` の `gpu_name` は local 側の wrapper で差し替える設計に変える（既存 schema のバイトは不変）。
4. **全体 pytest の取り方。** `tests/test_lbm_metal.py` は sandbox で `mlx.core` の import が abort するので、base と実装後の **両方**を `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で **完走**させる。base は `git worktree add --detach /private/tmp/wp01-base-e3dcdf61 e3dcdf61`（`.venv` は主リポジトリの `.venv` への symlink）。両者の失敗 node 集合を報告に載せる。途中で止めた記録は baseline にならない。
5. **commit／push は Claude が host で行う。** Codex の sandbox は `.git` 配下を書けない（`--add-dir` でも不可。2 回とも `index.lock: Operation not permitted`）。Codex は `git add`／`git commit`／`/tmp` の clone 経由の push を **しない**。代わりに報告の「作ったもの」に、commit すべきファイルの完全な一覧（変更・新規・戻したもの）を書く。Claude が同じ worktree から commit・push・`gh pr create --draft` を行う。
6. 1 回目の記録 `reports/wp01_attempt1_blocked/` は残す。報告 `wp01_local_gpu_01_report.md` と `wp01_local_gpu_01_validation.json` を更新し、受け入れ条件（GPU 実行は user が後で回すので DONE の妨げにならない）を満たせば状態を DONE にする。新たな矛盾が見つかった場合だけ、その箇所を具体的に示して止める。
