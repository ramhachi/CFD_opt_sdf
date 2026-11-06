# WP1：LOCAL-GPU-01 設計メモ（Amendment 2）

2026-11-06。base：`e3dcdf6188df6079e197eb28f7fcba1451ec512d`。ユーザー提示 Amendment 2 > Amendment 1 > 初期 WP1 / on-disk rev0。作るのは WSL2 上でユーザーが実行する道具・決定的なテスト・CPU 検証記録であり、GPU 実行・Kaggle・登録・凍結・roadmap 改定はしない。

## 読んだ契約と保全方針

`00_README.md`、`AGENTS.md`、docs README / STATE / branching / GEN plan、LOCAL-GPU-01 全文、LOCAL-OF-01 §§2–7 と runtime / comparator / infra / テスト、harness template / verify / README、HARNESS-01 campaign / rendered kernel、facts の全文を親と担当 worker で確認した。phase_plan は担当 worker が全文を確認。handoff / problem_register / problem_resolution は Amendment 1 指定どおり目次と harness・GPU・Kaggle・PROC-01 関連節を確認した。

phase_plan が状態・実行順の唯一の authority、problem_register は issue ledger。PROC-01 に従い CPU / 合成テストは capability / contract evidence、実機の環境 gate や対象物理の資格とは別。C3 / C4 は記述。T4 参照の byte gate を別 GPU の受け入れ条件に転用しない。既存 evidence / campaign / freeze / rendered kernel / 登録 job / Project / Manifest / 保護テスト / conftest は保全する。

`julia/CFDSDFWaterLily/src/` は directory pin なのでファイルを追加せず全 bytes を HEAD と一致させる。前回の main-module include と `tests/test_harness_replay.py` の変更は HEAD bytes に戻す。歴史テストの例外は作らない。前回の `src/Checkpoint.jl` は `gen01/Checkpoint.jl` へ移動する。

## backend と実行経路

新規 `backend_profiles.py` に `kaggle_t4` / `local_rtx4070ti` を定義。既定 profile は既存 selector・template・GPU probe の契約を保持し、local の場合だけ render 時に明示した hook を適用する。実名 RTX 4070 Ti、可能なら NVML UUID、CUDA singleton/default UUID、used_gpu_count=1 を要求する。未知 profile・他 GPU・SUPER・複数 GPU・identity 不一致は拒否する。

既存 Python helper の変更は `campaign_build.py` / `campaign_schema.py` / `campaign_verify.py` の opt-in のみ。schema は BASE_PIN のため、UNC / FID / SCREEN の freeze と tool-SHA を含む既存テストと全体 failure-set を検査する。回帰した場合は schema の変更を戻して local wrapper に移す方針。既定 render の byte 一致は、本物の historical source pin を `git archive` で読み、HARNESS-01 と UNC の commit 済み runner / metadata と比較する。過去 commit の pin と現行 source の hash を混同しない。

`local_gpu.py render --prepare-campaign` で派生 campaign を新規作成し、T4 first-state gate を除く。campaign を host 側で commit / push した後、その full source commit を `render` に渡す。renderer は committed source と remote reachability を確認する。checkpoint job を使う kernel の pins へ `julia/CFDSDFWaterLily/gen01/Checkpoint.jl` を明示し、include closure を検査する。生成後の runner は実行時に改変しない。

出力は方式 (a)：既存 `CAMPAIGN_WORK_ROOT` を使用。登録 harness は dataset を参照しないため `/kaggle` 全体の bind mount は不要。将来 dataset を参照する runner のみ read-only `/kaggle/input/<slug>` bind helper を使い、namespace lease と終了時解除を行う。WSL2 実機での optional bind 権限・挙動は未確認。

GPU project は登録済み `julia/CFDSDFWaterLilyT4`（WaterLily 1.8.0 / CUDA 6.3.1）。CPU checkpoint は `julia/CFDSDFWaterLily`。両 Manifest は変更しない。Julia tarball は template と同じ SHA、実行時は lock 済み executable を版 / SHA で確認する。

## lock と run 記録

`capture_lock.py` は標準ライブラリで canonical JSON（UTF-8 / sort_keys / indent=2 / nonfinite 拒否 / 末尾 LF 一つ）を作り、日時を含む全 bytes の SHA を sidecar に書く。欠測は null ではなく理由。必須 GPU 名・driver・Julia executable SHA・GPU Manifest SHA の欠測は JSON error / exit2、成功 lock は作らない。取得日時と生の CUDA.versioninfo は observations、環境比較は environment 全体。driver / Windows / WSL / 設定 / Julia / Manifest / CUDA runtime / Python / NumPy / depot の変化を拒否する。

`run` は新規 out だけを受理し CUDA_VISIBLE_DEVICES=0 / CUDA_DEVICE_ORDER=PCI_BUS_ID / JULIA_NUM_THREADS=1 を固定する。実際の runner 内 Project / Manifest pin を lock と起動前後に照合。各 run に lock / GPU / Julia / campaign / source / runner identity、開始終了、wrapper wall と RUN 境界の段別 wall、10 秒ごとの peak VRAM、exit code、DONE、全出力 SHA を保存。runner 成功後の bind 解除エラーも失敗として記録し、runner_returncode と wrapper returncode を区別する。

repeat は cold process を新規ディレクトリへ起動し、全体 watchdog を並行採取する。watch は 60 秒、VRAM は 10 秒。Windows System Display TDR event4101 を reset observer とし、観測不能を reset なしとしない。R5 は旧 record / log / checkpoint を新規 resume_input へコピーし SHA で結び、job の restore event も検査する。

## gate と数値契約

C1 は paired campaign / source / runner / environment と geometry / placement / scaling / step alignment を要求し、全 sample の byte 一致 → BITWISE、不一致なら abs(a-b)/max(abs(a),abs(b),1e-300) ≤ 1e-6 → TOLERANCE、それ以外 FAIL。local first-state SHA と級は gate に lock SHA と結んで記録し、元 lock は書き換えない。

C2 は両 R2 に既存 `harness.py verify --smoke` を subprocess。C3 は evidence の manifest / UNC table / gate / SHA256SUMS から参照 SHA を読み、窓平均の T4 相対差と UNC phase sigma を記述する。C4 は summary steps × cells / wall と T4 錨5.5e7 / 5.6e7 の比を記述。登録 job の warmup1step は steps に含み wall から除かれるので、(steps-1) の timed estimate も併記する。C5 は R3 / R5 の同一条件と kill → checkpoint SHA → 実 restore の provenance、endpoint-clipped time-weighted 窓統計を C1 級で比較する。力 writer / 符号 / 単位は登録 job と不変。

C6 は clock の時系列最大 drawdown <15%、全取得値 finite、観測した reset 無し、六時間の連続 cold-process loop を要求する。60 秒 cadence、sample / loop 間隔90秒までの scheduling 余裕、非重複 run の wrapper wall 合計6h以上、監視が workload 全体を覆うことを検査する。VRAM range は記述（仕様に数値閾値がない）。GPU-active 六時間とは主張せず solver wall / wrapper fraction を別記。idle clock も除外しないため正常 idle が FAIL になる可能性がある。欠測は INCOMPLETE、不正 input / mismatch は FAIL、既存 gate 出力は計算前に拒否し、排他新規作成で一回だけ書く。

## WP4 が使う checkpoint API

モジュールは `julia/CFDSDFWaterLily/gen01/Checkpoint.jl`。`src/CFDSDFWaterLily.jl` を既存流儀で include してから、scripts 内の job で `Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))` とする。GEN-01 の追加モジュールは今後も gen01 に置く。

- `CFDSDFWaterLily.Checkpoint.save_checkpoint(path, sim, step, rows; identity="") -> path`
- `load_checkpoint(path) -> validated NamedTuple`
- `restore_checkpoint!(fresh_sim, payload) -> fresh_sim`

両 Manifest の実依存に JLD2 はない（WaterLilyJLD2Ext の weakdep 宣言は実インストールではない）ため Serialization を使う。保存項目は u / p / u⁰ / 全Δt履歴 / 時刻 / step / force rows / runtime-config identity / caller identity。RNG・body closure・device pointer は保存しない。同一 body / solver / precision / boundary / sampling の新規 sim を作り、caller が identity を照合して復元し、payload.step+1 と payload.rows から続ける。標準 Flow / MultiLevelPoisson / default remeasure=true の範囲。信頼する自作 checkpoint だけを読む。local job は登録 flow32 job のコピーで、差分は保存 / 再開とその記録だけ、完全 diff を commit 対象にする。

## 検証と作業資源

lock / stub runner / repeat / interruption / telemetry / C1–C6 / hash 改変 / 非有限値 / 欠測 / 既存先拒否 / local identity / default byte / include closure を合成データで検証する。CPU64×32・100step、50step checkpoint の新規 sim 復元と連続 run の全 sample / field / 窓平均を比較。R0 bench は128³ TGV Float32・10warmup+100timed stepと固定2D capsule板、native Windows は benchmark wrapper のみ。小格子 CPU bench selftest を別に検証する。

base と最終 tree は両方 `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` を完走し exact failed-node set を比較する。base worktree 作成を一度試したが shared .git で拒否されたため、read-only `git archive e3dcdf61` の snapshot を `/private/tmp/wp01-base-e3dcdf61` に展開し、.venv / Git objects を symlink で参照する。clone / alternate Git history / test 改変は行わない。最終 production / test bytes の before-after SHA も記録する。compileall src tests、diff --check と immutable bytes を確認する。

OpenCode Go MCP は公開されず、CLI `opencode models opencode-go` も既定 log の FileSystem.open で起動失敗した。global 設定変更・追加課金なしで、ユーザーが求めた分担を native workers で実施。Codex は統合・最終検証を担当。Amendment 2 に従い git add / commit / push は行わず、host の Claude が同じ worktree で commit / push / gh draft PR を行うため完全な file list を報告する。1回目の記録は wp01_attempt1_blocked/ に保全する。

## WSL2 でだけ分かる未確認点

Windows build / driver / WSL kernel / distro と設定反映、Julia起動・JIT・小kernel launch 遅延、CUDA.functional、NVML の clock / power / VRAM / UUID query、Display TDR event の可視性、optional bind の要否・権限・解除、GPU checkpoint、native Windows benchmark 比、六時間 loop の温度・clock・RAM / VRAM 挙動はユーザー実機で確認する。KB5127936 保留は提示資料の回帰回避注意を保存したもので、ここで更新障害を検証した主張ではない。実装 DONE は LOCAL-GPU-01 PASS と別であり、物理・格子独立性・高Re / FSAE の資格を与えない。
