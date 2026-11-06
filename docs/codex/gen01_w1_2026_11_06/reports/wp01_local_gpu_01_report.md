# WP1：LOCAL-GPU-01 報告

## 状態

**DONE**。Amendment 2 に対応し、WSL2 用の道具・テスト・CPU 検証を完了した。GPU、Kaggle、実機 lock / gate の測定・生成は行っていない。環境 gate の合格と本 WP の実装完了は別である。

全体 pytest は base / 実装後とも指定の Metal 除外条件で完走：3482 passed / 74 skipped / 0 failed / 0 errors ／ 3570 passed / 74 skipped / 0 failed / 0 errors。失敗 node 集合は base = []、実装後 = [] で完全一致。新規テストは **88 passed**、CPU checkpoint は **BITWISE、最大相対差0**。

commit・push・PR は Amendment 2 指定の host Claude が担当するため未実施。Codex は git add / commit / push、clone 経由の代替 push を行っていない。

## 作ったもの（commit 対象の完全な一覧）

パスはこの worktree root からの相対パス。**変更3、新規25、計28ファイル**。

- 変更 `src/cfd_harness/campaign_build.py`：local opt-in の pin / render と Kaggle build / freeze の拒否。
- 変更 `src/cfd_harness/campaign_schema.py`：optional backend profile と local summary GPU identity。
- 変更 `src/cfd_harness/campaign_verify.py`：local identity / singleton / UUID を検査し、既存 verify --smoke で受理。
- 新規 `src/cfd_harness/backend_profiles.py`：既定 T4 と local RTX 4070 Ti の profile、派生 campaign、再 render。
- 新規 `infra/local_gpu/README.md`：WSL2 / Windows driver / Julia / lock / R0–R6 / gate のユーザー手順、KB5127936 保留。
- 新規 `infra/local_gpu/capture_lock.py`：canonical JSON / SHA、環境取得、必須欠測の理由付き JSON error。
- 新規 `infra/local_gpu/bind_dataset.sh`：必要な場合だけ使う read-only dataset bind helper。
- 新規 `julia/CFDSDFWaterLily/gen01/Checkpoint.jl`：保存・検査・新規 Simulation への復元。
- 新規 `julia/CFDSDFWaterLily/gen01/README.md`：registered src pin を保全する追加モジュールの配置規則。
- 新規 `scripts/local_gpu.py`：check-lock / render / run / repeat / watch / bench と計測・再開記録。
- 新規 `scripts/local_gpu_gate.py`：C1–C6、PASS / FAIL / INCOMPLETE、排他一回書き込み。
- 新規 `scripts/local_gpu_bench.jl`：128³ Float32 TGV と固定2D板、CPU 小格子自己テスト。
- 新規 `scripts/local_gpu_bench_windows.ps1`：native Windows 比較 benchmark の起動だけ。
- 新規 `scripts/waterlily_local_gpu_job.jl`：登録 flow32 job のコピーに checkpoint / resume と記録を追加。
- 新規 `scripts/waterlily_local_gpu_job.diff`：登録 job からコピーした job への正確な unified diff。
- 新規 `scripts/checkpoint_selftest.jl`：CPU64×32・100step・50step 保存後の新規 Simulation 再開比較。
- 新規 `tests/test_local_gpu.py`：lock / SHA / mismatch / fake runner / repeat / kill-resume / telemetry / runtime pins。
- 新規 `tests/test_local_gpu_backend.py`：T4 byte 不変、local identity、render / verify、gen01 pin / include closure。
- 新規 `tests/test_local_gpu_gate.py`：全 C1–C6、改変・欠測・非有限値・既存先拒否の合成テスト。
- 新規 `tests/test_local_gpu_julia.py`：登録 src hash 保全、checkpoint 配置、force writer と copied diff の検査。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_design.md`：Amendment 2 を反映した最終設計。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_report.md`：本報告。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_validation.json`：完走結果・失敗 node・コマンド・ログ・SHA・保全確認。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_checkpoint_selftest.json`：現在のソース SHA と CPU 再開結果。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_bench_cpu_selftest.json`：GPU を呼ばない bench 自己テスト結果。
- 新規・保全 `docs/codex/gen01_w1_2026_11_06/reports/wp01_attempt1_blocked/wp01_local_gpu_01_design.md`：1回目の設計記録。
- 新規・保全 `docs/codex/gen01_w1_2026_11_06/reports/wp01_attempt1_blocked/wp01_local_gpu_01_report.md`：1回目の BLOCKED 報告。
- 新規・保全 `docs/codex/gen01_w1_2026_11_06/reports/wp01_attempt1_blocked/wp01_local_gpu_01_validation.json`：1回目の検証記録。

戻したもの（HEAD と byte 一致し、commit の差分には含めない）：`julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl`、`tests/test_harness_replay.py`。前回の未追跡 `julia/CFDSDFWaterLily/src/Checkpoint.jl` は gen01 へ移動し、src 側には残していない。その他の保護テスト・conftest は変更していない。

## インターフェース（WP4 / ユーザー向け）

GPU project は登録済み `julia/CFDSDFWaterLilyT4`、CPU 自己テストは `julia/CFDSDFWaterLily`。両 Project / Manifest は不変。`src/` の directory SHA は登録値 `9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85` と一致する。

WP4 は既存の流儀で main module を include した後、次の API を使う。

```julia
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint
save_checkpoint(path, sim, step, rows; identity=geometry_sampling_sha)
state = load_checkpoint(path)
state.identity == geometry_sampling_sha || error("checkpoint identity mismatch")
restore_checkpoint!(fresh_sim, state)
# 同じ構成の fresh_sim で、state.step+1 / copy(state.rows) から続ける
```

`save_checkpoint -> path`、`load_checkpoint -> validated NamedTuple`、`restore_checkpoint! -> fresh_sim`。u / p / u⁰ / 全Δt履歴 / 時刻 / step / force sample rows / runtime-config identity を保存する。RNG・body closure・device pointer は保存しない。JLD2 は両 Manifest に weakdep extension 宣言のみで実依存がないため Serialization を採用。標準 Flow / MultiLevelPoisson、同一 body / configuration、既定 remeasure=true が検証範囲。信頼した自作 checkpoint だけを読む。local campaign の kernel pins に gen01/Checkpoint.jl を明示する。

CLI は `local_gpu.py check-lock`、`render CAMPAIGN --prepare-campaign NEW_CAMPAIGN`、host commit / push 後に `render NEW_CAMPAIGN --source-commit FULL_SHA --kernel KEY --smoke --out NEW_KERNEL`、`run NEW_KERNEL --out NEW_RUN [--repeat N]`、`watch`、`bench`。詳細コマンドは infra/local_gpu/README.md に記載。R3 / R5 の追加環境変数は `LOCAL_GPU_CHECKPOINT_EVERY`、`LOCAL_GPU_CHECKPOINT_PATH`、`LOCAL_GPU_RESUME_PATH`。

出力先は方式(a)、既存 CAMPAIGN_WORK_ROOT を使用する。通常の登録 harness は dataset を使わず bind 不要。local profile で再 render した runner は実行時に変更しない。CUDA_VISIBLE_DEVICES=0 と used_gpu_count=1 を固定し、GPU 名・可能なら NVML UUID・必須の CUDA UUID を検査する。lock / runtime Project / Manifest pin が違えば起動を拒否する。local_run.json は wall・10秒間隔 peak VRAM・exit・DONE・全出力 SHA、watchdog は60秒 cadence。R5 は旧 run を保存したまま checkpoint SHA と job restore event を結ぶ。

gate は C1 の同一機反復を byte→1e-6 で分類し、C2 で既存 harness verify --smoke を両 R2 へ呼ぶ。C3 の T4 窓平均差と C4 の throughput 比は記述、C5 は R3 / R5 の同一条件と窓統計、C6 は六時間 loop / clock / finite / reset を検査する。欠測は INCOMPLETE、既存出力は計算前に拒否。C1 合格後の local first-state SHA と級は lock SHA とともに gate に記録し、元 lock は変更しない。

## テスト

全体の base は `e3dcdf6188df6079e197eb28f7fcba1451ec512d`。指定された worktree 作成は shared .git への書き込みで拒否されたため、一度の失敗を記録し、同じパス `/private/tmp/wp01-base-e3dcdf61` へ read-only git archive で展開した。主リポジトリ .venv と読み取り専用 Git objects を参照。tracked source / test / script / Julia の914ファイルは base の Git blob と一致する。両実行で同じ interpreter / 環境を使用し、Metal 除外以外の skip / xfail / 保護テスト改訂は追加していない。

```bash
# base と実装後の双方で完走（記録用 --junitxml のみ追加）
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
# 新規テスト
.venv/bin/python -m pytest -q tests/test_local_gpu.py tests/test_local_gpu_backend.py tests/test_local_gpu_gate.py tests/test_local_gpu_julia.py -p no:cacheprovider
# 指定された単独ファイルの確認
.venv/bin/python -m pytest -q tests/test_local_gpu.py -p no:cacheprovider
# 重点回帰
.venv/bin/python -m pytest tests/test_unc01.py tests/fid01 tests/screen01 tests/test_harness_replay.py tests/test_harness_freeze.py tests/test_local_gpu_backend.py -q -rf -p no:cacheprovider
# CPU
JULIA_NUM_THREADS=1 julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/checkpoint_selftest.jl
JULIA_NUM_THREADS=1 julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/local_gpu_bench.jl --cpu-selftest --out NEW_CPU_RESULT.json
.venv/bin/python -m compileall src tests
git diff --check
```

- 全体：base 3482 passed / 74 skipped / 0 failed / 0 errors、実装後 3570 passed / 74 skipped / 0 failed / 0 errors。base = []、実装後 = [] で完全一致。失敗 node の完全な集合は validation JSON に記録。
- 新規88 passed（test_local_gpu.py 16、backend16、gate52、Julia契約4）。fake runner で DONE / local_run.json を作成。
- `tests/test_local_gpu.py` 単独も16 passed / exit0。
- 重点回帰486 passed / 1 skipped。既存 Sobol warning 1件。schema の opt-in は維持できた。
- CPU checkpoint：64×32 Float32 / 100step / 50step保存→新規sim復元で BITWISE、全サンプル最大相対差0。窓平均 / 最終 u,p,u⁰ も一致。
- bench CPU selftest：TGV16³ / 板64×32、used_gpu_count=0、finite。GPU 性能値ではない。
- GPU のない Mac の capture：exit2、必須 GPU 名 / driver 欠測の理由付き JSON、stderr 空、traceback 無し、成功 lock 無し。
- HARNESS-01 / UNC U01 の genuine historical source pin から既定 render を行い、commit 済み runner / metadata と byte 一致。include closure と gen01 pin 欠落拒否も成功。
- compileall、shell helper の sh -n、git diff --check 成功。最終検証中の実装 / テスト931ファイルは before-after SHA 一致。既存 evidence / campaign / kernel / job / src / Manifest / 保護テストは保全。

独立レビューで C1 の異なる runner SHA を受理する穴を再現し、R1 / R2 の paired runner / environment 一致を追加した。bind 解除エラー後の偽成功もテストで再現して修正した。これらを含む88件が通り、最終全体テストは base と同じ失敗集合だった。

## 仕様からの逸脱と理由

Amendment 1 / 2 に従い、backend opt-in に必要な既存 Python3ファイルを最小変更した。既定 template / grid01 selector / 登録 job は無改変。歴史テストを変更せず、src directory pin を復元し、checkpoint を gen01 に置くことで前回の10-node衝突を解消した。base worktree の代わりの archive は sandbox の .git 書き込み制限によるもので、source bytes と Git 履歴の読み取りを保持した。

OpenCode Go MCP はなく、CLI models discovery も既定 log の FileSystem.open で失敗したため native worker 分担と親の統合確認で実行した。global 設定・追加課金を変更していない。commit / push / gh draft PR は host 担当という Amendment 2 に従う。

README の WSL 設定と Windows driver / NVML 説明は [Microsoft WSL settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) と [NVIDIA CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) でも照合した。KB5127936 保留は提示資料の注意を保持し、この更新障害を独自に検証したとは主張していない。

## 未確認の仮定

WSL2 実機の Windows build / driver / kernel / distro、設定反映、Julia起動・JIT・小kernel launch 遅延、CUDA.functional、NVML の clock / power / VRAM / UUID、Display TDR event4101 の可視性、optional bind mount の要否・権限・解除、GPU の別プロセス checkpoint 再開、native Windows benchmark 比、六時間の温度・RAM / VRAM・clock は未確認。

C6 は cold-process loop の六時間で、GPU-active 六時間ではない。solver wall 合計と wrapper fraction を別記する。clock の最大 drawdown は idle を除外しないため正常 idle でも FAIL になり得る。VRAM range は仕様に閾値がないため記述する。CPU / 合成テストから WSL2 合格、T4 force 同値、物理・格子独立性・高Re / FSAE の資格へ主張を広げない。

## Claude／ユーザーへの提案する追記

仕様 rev0 の所有者が Amendment 1 / 2 の profile / GPU project / local job / gen01 配置と、C6 の clock / cadence / cold-loop / reset未観測時 INCOMPLETE の定義を実機実行前に反映する。on-disk rev0 には提示された§10が未収録。roadmap / STATE / exploratory_index / 仕様本文は本 WP では変更していない。

## 次に要るもの

host Claude が上記28ファイルを同じ worktree で commit / push し、`gh pr create --draft --base codex/kaggle-batch-migration --body-file docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_report.md` で PR を作る。自動 merge は行わない。戻した2ファイルは diff 無しとして扱う。

その後、ユーザーが WSL2 を準備し、環境 lock の review / commit、独立 source review、事前記録を経て R0–R6 と gate を実行する。これは本 WP の実装 DONE を妨げない後続の実機作業である。
