# WP1：LOCAL-GPU-01 報告（Amendment 3）

## 状態

**DONE**。PR #88 の開始 commit `e6c57e7b` に対する Opus review と Amendment 3 の修正を実装した。検証を完了した。GPU、Kaggle、実機 lock / gate は実行・生成していない。環境 gate の PASS と道具の実装完了は別である。

**前回報告の訂正：** 「T4 契約は byte 不変」という前回の主張は誤りだった。`campaign_schema.py` は BASE_PIN、schema/build/verify は TOOL_FILES であり、attempt 3 の編集により登録済み tool SHA を変え、UNC-01 smoke の再検証を失敗させていた。前回の pytest 通過と historical archive での render 一致では検出できなかった。今回は3ファイルを `e3dcdf61` と byte 一致に戻し、現在の tree で保存済み UNC-01 U01 smoke / formal table を再検証して byte 一致をテストした。

commit・push・PR 更新は Amendment 3 指定の host Claude が担当する。Codex は git add / commit / push や別 clone 経由の push を行っていない。

## 作ったもの（host が commit する完全な一覧）

この worktree の HEAD `e6c57e7b` に対する差分。`復元` は PR に入っていた tool 変更を `e3dcdf61` の bytes に戻したファイル。新しい検証記録も個別に列挙する。

- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/base-pytest.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/base-pytest.xml`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/base-result.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/bench-cpu-selftest.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/checkpoint-selftest.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/compileall-result.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/compileall.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/cpu-validation.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/focused-pytest-result.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/focused-pytest.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/focused-pytest.xml`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/full-pytest-result.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/full-pytest.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/full-pytest.xml`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/mac-capture.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/protected-paths.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/source-stability.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/standalone-local-gpu-result.json`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/standalone-local-gpu.txt`
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/standalone-local-gpu.xml`
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_bench_cpu_selftest.json`
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_checkpoint_selftest.json`
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_design.md`
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_report.md`
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_validation.json`
- 変更 `infra/local_gpu/README.md`
- 変更 `infra/local_gpu/capture_lock.py`
- 変更 `julia/CFDSDFWaterLily/gen01/Checkpoint.jl`
- 変更 `scripts/checkpoint_selftest.jl`
- 変更 `scripts/local_gpu.py`
- 変更 `scripts/local_gpu_bench.jl`
- 変更 `scripts/local_gpu_bench_windows.ps1`
- 変更 `scripts/local_gpu_gate.py`
- 変更 `scripts/waterlily_local_gpu_job.diff`
- 変更 `scripts/waterlily_local_gpu_job.jl`
- 変更 `src/cfd_harness/backend_profiles.py`
- 復元 `src/cfd_harness/campaign_build.py`
- 復元 `src/cfd_harness/campaign_schema.py`
- 復元 `src/cfd_harness/campaign_verify.py`
- 新規 `tests/test_harness_registered_reverify.py`
- 変更 `tests/test_local_gpu.py`
- 変更 `tests/test_local_gpu_backend.py`
- 変更 `tests/test_local_gpu_gate.py`

変更内容：backend module に local validate/render/verify を集約し、pinned checkout から明示 path import、top-level campaign pin、unchanged B.pin_block/B.pins を使う。local verify は private function bindings で unchanged harness の selector/probe/summary期待値を wrap し、SC/B/V の global state を変更しない。local campaign が JULIA_*/CUDA_*/NVIDIA_*/WSL*/LOCAL_GPU_* を env common、宣言 keys、per-run env、scrub で上書きする経路も拒否する。

lock は Julia installation root、専用 depot、Manifest-resolved package trees、HAGS を追加し、tarball 定数を expected SHA として明示した。run は実際に子へ渡す filtered environment を記録する。used_gpu_count の実証は independent CUDA probe.logical_device_count。NVML UUID fallback は LOCAL だけ、R1–R6 の CUDA UUID は一つに一致させる。

C3/C4 は FAIL/INCOMPLETE でも PASS を妨げず別に報告する。C6 は solver-active clock、成熟区間VRAM range≤device totalの5%、全10秒sampleのrepeat peak変動≤2%を実装した。optional/required telemetry取得不能は INCOMPLETE、非有限・不正値・reset・規則超過は FAIL。DONE と identity欠落の矛盾も FAIL。gate は完全な temporary file の後に exclusive hardlink で一度だけ公開する。

保全したもの：`reports/wp01_attempt1_blocked/` の3記録、`gen01/README.md`、bind helper、既存テスト（conftest・historical replay を含む）、登録job、既存evidence/campaign/freeze/rendered kernel、両Project/Manifest、登録済みJulia src directory。これらに今回のcommit対象として不要な差分はない。

## インターフェース（WP4 / ユーザー向け）

GPU project は `julia/CFDSDFWaterLilyT4`（WaterLily1.8.0/CUDA6.3.1）、CPU 自己テストは `julia/CFDSDFWaterLily`。どちらの Manifest も変更していない。追加 module は `julia/CFDSDFWaterLily/gen01/Checkpoint.jl` に置く。

```julia
# main module の読込後、scripts/ 内の job から
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint
save_checkpoint(path, sim, step, rows; identity=study_geometry_sampling_sha)
payload = load_checkpoint(path)
restore_checkpoint!(fresh_sim, payload; identity=study_geometry_sampling_sha)
# 同一構成の fresh_sim で payload.step+1 / copy(payload.rows) から続ける
```

save→path、load→validated NamedTuple、restore→fresh_sim。save/restore の identity は必須かつ非空で、restore 自身が照合してから field を変更する。`step` は個々の mom_step! の完了回数、`length(Δt)==step+1`。`sim_step!(sim,t_end)` は一度に複数stepを進めるため、呼出回数をこのstepにしてはいけない。u/p/u⁰/全Δt/時刻/step/force rows/runtime-config/caller identityを保存し、RNG/body closure/device pointerは保存しない。標準Flow/MultiLevelPoisson、同一body/config、default remeasure=true、信頼した自作Serialization fileに限る。JLD2はManifestのweakdep宣言だけで実依存ではない。

CLI は `local_gpu.py check-lock`、`render CAMPAIGN --prepare-campaign NEW`、host commit/push後の `render NEW --source-commit FULL_SHA --kernel KEY --smoke --out DIR`、`run`、`verify --campaign CAMPAIGN --kernel-output OUTPUT --smoke --source-commit SHA`、`watch`、`bench`。通常は既存 `CAMPAIGN_WORK_ROOT` を使用し bind 不要。将来datasetを使う場合だけ optional bind helper を使う。render後のrunnerは実行時に変更しない。

専用 `JULIA_DEPOT_PATH` を instantiate前から設定する。lock の追加項目は julia.root/root_sha256、julia.expected_archive_sha256、julia_depot.path/manifest_packages_sha256/packages。run は filtered_environment と同じdepotを子へ渡す。lockSHAとsampled peakVRAMをbenchにも残す。native Windows wrapperは `-Out RESULT -Lock LOCK` が必須で、SHAはWSL2 referenceへのbindingでありnative環境がlockと同じという意味ではない。TGVはcustom engineering fixtureでWaterLily benchmark suiteそのものではない。

C6は通常 `utilization.gpu>=50%` を用いる。明示的なsolver intervalにも対応するが、本wrapperのRUN段はJulia import/JITを含むprocess envelopeなのでそこからactive区間を推定しない。90秒gap/60秒first-sample allowanceはdevelopment defaultsとしてgate.jsonに記録する。per-repeat peakの2%は(max−min)/max、startupを含む全10秒sampleの値。R4欠測は記述に残し、取得されたR4のUUID矛盾はthroughputとは別の必須identity違反とする。

## テスト（コマンド、結果、失敗node集合）

- 重点：`.venv/bin/python -m pytest -q tests/test_local_gpu.py tests/test_local_gpu_backend.py tests/test_local_gpu_gate.py tests/test_local_gpu_julia.py tests/test_harness_registered_reverify.py -p no:cacheprovider` → **169 passed**。
- 指定単独：`.venv/bin/python -m pytest -q tests/test_local_gpu.py -p no:cacheprovider` → **25 passed**。偽runnerによるDONE/local_run.json生成を含む。
- 全体：`.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` → **3651 passed / 74 skipped / 0 failed / 0 errors**。記録用 `--junitxml=...` のみ追加。
- baseline：e3dcdf61の前回完走 **3482 passed / 74 skipped / 0 failed / 0 errors** を再利用。今回再実行したとは主張しない。ログ/JUnitを前回記録SHAで検証し、reports配下へ変更せず保全した。
- 失敗node集合：base = `[]`、今回 = `[]`。完全一致。new failed nodes = []。
- 現在のtreeのU01 smoke/formal再検証、local verify後のregistered再検証、保護tool bytes、include closure、reserved env override、C1–C6全合成基準、collector欠測、atomic publish例外/競合を検査した。
- CPU checkpoint：`JULIA_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/checkpoint_selftest.jl` → **25 assertions PASS、BITWISE、最大相対差0**。64×32/100step/50step保存→新規sim、全sample/最終u,p,u⁰/窓平均が一致。必須identity/foreign identityも拒否。
- CPU bench：同じCPU projectで `scripts/local_gpu_bench.jl --cpu-selftest --out NEW_RESULT` → used_gpu_count=0、TGV16³/板64×32のfinite field。GPU性能値ではない。
- GPUのないMacのcapture → **exit2、理由付きJSON、stderr空、tracebackなし、成功lock未作成**。
- `.venv/bin/python -m compileall src tests`、`sh -n infra/local_gpu/bind_dataset.sh`、`git diff --check` → PASS。
- `git diff e3dcdf61 --stat -- src/cfd_harness/campaign_schema.py src/cfd_harness/campaign_build.py src/cfd_harness/campaign_verify.py` → **出力空**。既存保護scopeと既存test変更集合も[]。9個の登録prerun freezeのtool SHAが現treeと一致。Julia src directory SHAは登録値 `9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85`。

重点/full/JUnit/CPU/stdout/コマンド/returncode/時刻/壁時計/SHAは `wp01_amendment3_validation/` と `wp01_local_gpu_01_validation.json` に保存した。全体検証の前後でsource/test/scriptのSHA集合も不変。

## 仕様からの逸脱と理由

Amendment3に従い既存schema/build/verifyのopt-inを撤回し、local専用module/CLIへ移した。既存 `harness.py` は変更せず、C2はlocal CLIからunchanged harness検査をwrapする。ユーザー指定の3file復元はgit indexを書けないsandboxのため`git show`のbytesを書き戻す等価手順を使った。`git checkout`、git add/commit/pushは実行していない。

C3/C4のT4錨は参照summaryのcells×steps/wallから導出する。現在の保存済み参照ではR3=54,771,184.79219463、R4=50,729,748.4492402 cell-step/s。SHAはevidenceのmanifestから読み、コードへcopyしない。全sample比較は同じsolver-step indexで行い、count/stepが異なる場合はsample subrecordをINCOMPLETEにして理由を残す。補間による同等性は作らない。

OpenCode Go MCPなし、CLI models確認も既定logのFileSystem.openで起動失敗。global設定/課金を変更せずnative workerの非重複実装と独立source review、親の統合/最終検証で対応した。これは実行資源のfallbackでありGPU gateの観測ではない。

## 未確認の仮定（WSL2実機で確認すること）

起動/JIT/小kernel launch遅延、installation-root/package-tree hashとPkg introspectionのoverhead、Windows build/driver/WSL kernel/distro/設定反映、HAGS registry、CUDA.functional、NVMLのclock/temp/power/memory/utilization/UUID、Windows Display TDR event4101可視性、optional bind mount要否/権限/解除、GPU別process checkpoint、native PowerShell/Windows比較、6時間loopのclock/温度/RAM/VRAMを実測していない。WSL2のpartial NVML supportでC6がINCOMPLETEになる可能性もユーザー実機で判明する。

KB5127936保留は提示資料の回帰回避注意を保持したもので、この更新障害を独自に検証した主張ではない。R6は6時間のcold-process wrapper loopで、GPU-active6時間ではない。resetなしもevent monitorの観測範囲に限る。CPU/合成テストからT4force同値、格子独立、対象物理、高Re/FSAE資格へ主張を広げない。

## Claude／ユーザーへの提案する追記

review worktreeのLOCAL-GPU-01 §11 Amendment2を統合し、current-tree登録再検証guard、immutable tool境界、C6のactive/VRAM/欠測/既定allowance、参照からの錨、必須identityの契約を所有者の本文へ反映する。このworktreeのroadmap/STATE/exploratory_index/仕様本文は変更していない。renderからgateまでpinned filesを変えない手順を維持する。

## 次に要るもの

host Claudeが上記の完全なfile一覧を同じworktreeでcommit/pushし、既存PR #88を更新する。必要なPR操作はgh CLI、auto-mergeは有効にしない。

その後、所有者のsource reviewと事前記録、WSL2準備・専用depotのinstantiate、実機lockのcapture/review/commitを経て、ユーザーがR0–R6とone-shot gateを実行する。後続GPU実行はこの道具の実装DONEを妨げない。
