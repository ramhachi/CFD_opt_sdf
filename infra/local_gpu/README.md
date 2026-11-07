# LOCAL-GPU-01 tools: RTX 4070 Ti / Windows 11 / WSL2

このディレクトリは環境 gate の道具です。実機の `lock.json` も GPU の測定値も同梱しません。
GPU 実行はユーザーが WSL2 内で行います。実行前に source review、環境 lock の commit、
LOCAL-GPU-01 の exploratory 行の事前記録が必要です。登録・凍結・gate 合格や物理の資格を与えるものではありません。
仕様は [LOCAL-GPU-01](../../docs/local_gpu_env_gate_2026_11_01.md) と WP1 のユーザー提示 Amendment 1 / 2 / 3、
設計は [WP1 design](../../docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_design.md) を参照してください。
この worktree の rev0 は amendment が未収録です。Amendment 3 が指定する review worktree の
LOCAL-GPU-01 §11 と本書の改訂契約に従います。既存 harness の schema/build/verify は変更しません。

## 1. Windows と WSL2 を準備する

Windows 11 側に NVIDIA の production Windows driver を導入します。WSL2 内には Linux display driver、
`cuda-drivers`、`nvidia-open` を入れません。Windows の driver が WSL2 に `libcuda.so` を提供します。
これは [NVIDIA CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) の手順です。
Julia CUDA.jl の runtime artifacts は既存 Manifest から取得します。

**プレビュー更新 KB5127936 は保留してください。** これは登録準備資料
[`facts_for_w1_drafts.md` §5](../../docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md)
と rev0 にある回帰回避の注意です。本実装でこの更新や障害報告を実機検証したものではありません。
driver、Windows build、WSL kernel の更新は lock 後の環境変更なので新しい gate が必要です。

PowerShell で現在の状態を確認し、Ubuntu 24.04 LTS を WSL **2** として用意します。

```powershell
wsl --version
wsl --list --verbose
# 未導入の場合のみ
wsl --install -d Ubuntu-24.04
```

`%USERPROFILE%\.wslconfig` の例（ホスト RAM が32 GBの場合。実機の余裕に合わせて明示設定）：

```ini
[wsl2]
memory=16GB
processors=8
swap=8GB
```

この memory は guest RAM の上限であり VRAM を増やしません。WSL2 内の `/etc/wsl.conf` は、
既存の設定を保ちながら次のキーを設定します。

```ini
[gpu]
enabled=true
appendLibPath=true
[automount]
ldconfig=true
[interop]
enabled=true
appendWindowsPath=true
```

`appendLibPath` は `/usr/lib/wsl/lib` を PATH に追加し、`ldconfig` は Windows 提供の GPU libraries を
linker の探索対象にします。設定は VM 再起動時に反映されます。他の WSL 作業が完了してから
PowerShell の `wsl --shutdown`、Ubuntu 再起動を行ってください。
[Microsoft WSL settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) に scope と反映条件があります。
Windows interop は build/version と driver-reset event の観測にも使います。

Ubuntu の Linux filesystem 側に checkout を置き、以下を確認します。

```bash
cat /etc/os-release
uname -r
cat /proc/version
wsl.exe --version
cmd.exe /c ver
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap,power.limit --format=csv,noheader
```

profile は **NVIDIA GeForce RTX 4070 Ti** のみを受理します。4070 Ti SUPER、T4、複数 GPU は別 backend です。
WSL2 の NVML は部分対応なので、unsupported な query は成功とみなさず理由を記録します。
`nvidia-smi` の場所は `/usr/lib/wsl/lib/nvidia-smi` です。clock/power/memory query の取得可否は実機で確認します。
[NVIDIA の制限一覧](https://docs.nvidia.com/cuda/wsl-user-guide/index.html#features-not-yet-supported) も参照してください。

## 2. Python と Julia 1.12.6 の準備

fresh Ubuntu では Python/NumPy と同じ interpreter を先に用意します。ここからのコマンドは repository root です。
wrapper は自身の `sys.executable` で runner を起動するため、capture/run/gate のすべてで同じ venv を使用します。

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends python3-venv git curl ca-certificates
python3 -m venv .venv
.venv/bin/python -m pip install 'numpy>=1.26'
.venv/bin/python -c 'import sys,numpy; print(sys.executable, numpy.__version__)'
```

ここで必要なのは既存 runner の NumPy と標準ライブラリです。repository 全体の開発テストを行う場合だけ、
既存 `requirements.txt` も同じ venv へ導入してください。Python executable/版と NumPy 版は環境 lock に記録します。


次の URL と SHA-256 は `src/cfd_harness/campaign_runner_template.py` の pin と同一です。
tarball の検証に成功してから展開します。Linux x86_64 用であり、Mac / native Windows 用ではありません。

```bash
curl -fL -o /tmp/julia-1.12.6-linux-x86_64.tar.gz \
  https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz
printf '%s  %s\n' bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a \
  /tmp/julia-1.12.6-linux-x86_64.tar.gz | sha256sum --check -
mkdir -p "$HOME/.local/opt"
tar -xzf /tmp/julia-1.12.6-linux-x86_64.tar.gz -C "$HOME/.local/opt"
export PATH="$HOME/.local/opt/julia-1.12.6/bin:$PATH"
export JULIA_NUM_THREADS=1
export CUDA_VISIBLE_DEVICES=0
export CUDA_DEVICE_ORDER=PCI_BUS_ID
# この backend 専用 depot。capture / check-lock / run も同じ値で実行する
export JULIA_DEPOT_PATH="$HOME/.local/share/cfd-local-gpu/julia-depot"
mkdir -p "$JULIA_DEPOT_PATH"
julia --startup-file=no --version
```

repository root で以下を実行します。GPU project は **`julia/CFDSDFWaterLilyT4`**
（WaterLily 1.8.0 + CUDA 6.3.1）。CPU checkpoint 自己テストだけが `julia/CFDSDFWaterLily` を使います。
どちらの Manifest も更新・resolve しません。

```bash
sha256sum julia/CFDSDFWaterLilyT4/Manifest.toml > /tmp/local-gpu-manifest-before.sha256
julia --startup-file=no --project=julia/CFDSDFWaterLilyT4 -e 'using Pkg; Pkg.instantiate()'
sha256sum --check /tmp/local-gpu-manifest-before.sha256
julia --startup-file=no --project=julia/CFDSDFWaterLilyT4 -e \
  'using CUDA; CUDA.versioninfo(); @assert CUDA.functional(); @assert length(collect(CUDA.devices())) == 1'
```

## 3. 環境を capture し、変更を拒否する

```bash
.venv/bin/python infra/local_gpu/capture_lock.py
.venv/bin/python scripts/local_gpu.py check-lock
git add infra/local_gpu/lock.json infra/local_gpu/lock.json.sha256
git commit -m "Lock the WSL2 RTX 4070 Ti environment before LOCAL-GPU-01"
git push
```

capture は `lock.json` と `lock.json.sha256` があれば上書きを拒否します。
必須の GPU 名、driver、Julia executable SHA、GPU Manifest SHA が欠けた場合は JSON のエラーと exit 2 を返し、
成功 lock を作りません。Mac に GPU がない場合も同じ契約です。
未取得項目は `null` ではなく `{"error":"理由"}`。
canonical JSON は UTF-8、キーを sort、2-space indent、末尾 LF 一つ、nonfinite 数値なしです。
sidecar は日時を含む **全 lock bytes** の SHA-256 です。

`check-lock` は sidecar と canonical bytes を確認し、同じ方法で取り直した `environment` 全体を比較します。
日時・生の `CUDA.versioninfo()` の自由 VRAM 表示は `observations` にあり、比較対象から分離します。
Windows build、WSL kernel/設定、driver、GPU、Julia executable と installation root、Manifest、
CUDA runtime、専用 depot の Manifest-resolved package tree 等が変われば拒否します。
tarball SHA は template の期待値と実測済みの値を区別します。未取得 archive を検証済みとは記録しません。
Windows HAGS は registry が読める場合に状態を保存し、読めない場合は理由を保存します。
クラスと local first-state SHA は C1 後の `gate.json` に lock SHA と一緒に追加するので、元の lock は書き換えません。

## 4. ローカル campaign と kernel を render する

既存 campaign、kernel、登録 job は書き換えません。local campaign の準備 → commit/push → render の2段階です。
元の T4 first-state byte gate は派生 campaign から除き、C3 の記述参照として保全します。

```bash
.venv/bin/python scripts/local_gpu.py render docs/harness/harness01_replay_campaign.json \
  --prepare-campaign infra/local_gpu/r1.campaign.json
.venv/bin/python scripts/local_gpu.py render docs/harness/unc01_u01_campaign.json \
  --prepare-campaign infra/local_gpu/r2.campaign.json
.venv/bin/python scripts/local_gpu.py render docs/harness/screen01_f_campaign.json \
  --prepare-campaign infra/local_gpu/r3.campaign.json --job scripts/waterlily_local_gpu_job.jl
.venv/bin/python scripts/local_gpu.py render docs/harness/screen01_f48_campaign.json \
  --prepare-campaign infra/local_gpu/r4.campaign.json
```

生成 campaign をレビューして対象ファイルだけ commit/push します。その pushed full commit SHA を
`--source-commit` に指定します。renderer は全 pin の committed bytes と remote reachability を確認します。
`--kernel` は元 campaign の key（R1=`a`、R2=`f24`、R3=`f32a`、R4=`f48k13`）です。
この gate では **すべて `--smoke`** を指定し、各 kernel の最初の parent だけを full registered window で実行します。
`smoke` は流れの窓を短くするものではありません。
render から gate まで、campaign、backend module、job、GEN-01 module を含む pinned files を変更しないでください。
C2 は現在の tree で再 render して照合するため、途中で pin が変わると FAIL になります。
変更が必要なら source / campaign を再確認し、新しい環境 gate の手続きで扱います。

```bash
.venv/bin/python scripts/local_gpu.py render infra/local_gpu/r1.campaign.json \
  --source-commit FULL_PUSHED_SHA --kernel a --smoke --out work/local_gpu/kernel_r1
# R2/R3/R4 も同様に、それぞれ上記 key / campaign / 新規 out を指定
```

生成後の `runner.py` は wrapper が一切変更せず実行します。local profile だけが実機名・可能なら NVML UUID、
CUDA singleton/default UUID を検証し、lock 済み Julia executable / installation root / 専用 depot を再検査します。
singleton の実証は独立 CUDA probe の `logical_device_count=1` です。runner の
`used_gpu_count=1` はこの検査に対応する bookkeeping で、単独の測定値としては扱いません。
実際に子へ渡す `JULIA_*` / `CUDA_*` / `NVIDIA_*` / `WSL*` は `local_run.json` の run identity に記録します。
NVML UUID が取得不能でも CUDA driver の UUID は必須です。
既定 `kaggle_t4` の template と既存 rendered kernel は保全します。

出力は方式 **(a) `CAMPAIGN_WORK_ROOT`**。登録 harness は dataset を使わないので bind mount は不要です。
将来、`/kaggle/input/<slug>` を使う runner だけは `--dataset DIR` と1件の metadata dataset_sources が必要です。
その場合は `sudo -v` をユーザーが実行してから wrapper を起動すると、`bind_dataset.sh` が read-only bind し、
終了時に解除します。入力 namespace の排他 lease と既存 mount の拒否があります。
この optional bind は WSL2 で未検証です。

## 5. R0–R6 を実行する（ユーザーのみ）

```bash
.venv/bin/python scripts/local_gpu.py bench --out work/local_gpu/r0_wsl2.json
# native Windows は Windows 用 Julia 1.12.6 + 同じ既存 project を準備してから
# PowerShell: ./scripts/local_gpu_bench_windows.ps1 -Out work/local_gpu/r0_native_windows.json -Lock infra/local_gpu/lock.json
```

R0 は custom TGV 128³ Float32/Re1600、10 warmup step + 100 timed step、2D capsule 板256×128、chord32、
thickness4、10°、Re1000 を固定します。wall は CUDA synchronize で挟み、cells×steps/wall を出します。
TGV は WaterLily の benchmark suite そのものではなく、固定した初期場・境界の工程 fixture です。
公開 ns/DOF 錨との直接同等性は主張しません。板も rev0 に細部指定がないため固定した工程 fixture です。
結果には lock SHA と VRAM を記録します。CPU selftest では GPU を使用せず、その旨を明記します。
native Windows との WSL2 遅延比は記述し、25%超の場合の OS 判断はユーザーが行います。
native Windows wrapper は benchmark のみで、POSIX harness の移植ではありません。

以下の `EVIDENCE` は future evidence の保存先です。未登録の実測を勝手に始めないでください。

```bash
EVIDENCE=docs/evidence/local_gpu_gate_2026_11
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r1 --out "$EVIDENCE/R1a"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r1 --out "$EVIDENCE/R1b"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r2 --out "$EVIDENCE/R2a"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r2 --out "$EVIDENCE/R2b"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r3 --out "$EVIDENCE/R3"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r4 --out "$EVIDENCE/R4"
```

R5 は R3 と同一 kernel を使います。R3 の実測 wall から約半分になる秒数を実行前に決め、
`HALF_WALL_SECONDS` を設定してください。中断側の非0終了は意図したものです。

```bash
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r3 --out "$EVIDENCE/R5_interrupted" \
  --checkpoint-every 100 --interrupt-after "$HALF_WALL_SECONDS"
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r3 --out "$EVIDENCE/R5" \
  --checkpoint-every 100 --resume-from "$EVIDENCE/R5_interrupted/local_run.json" \
  --resume-checkpoint "$EVIDENCE/R5_interrupted/checkpoint.bin"
```

resume は旧 run/checkpoint/log を `R5/resume_input/` にコピーして SHA を記録し、旧 run を書き換えません。
保存先は R5 の新しい `checkpoint.bin`。job が restore した証拠 `local_gpu_resume.json` も出します。
checkpoint がまだ無い時点で kill した場合は再開できません。

R6 の N は R3 の wall を基に **合計6時間以上**になるよう実行前に決めます。
`--repeat N` は連続する新規 `repeat_001/` 等に cold process を起動し、全 repeat に並行する
`R6/watchdog.csv` / `watchdog_status.json` を自動で書きます。単発 run も自身の watchdog を書きます。

```bash
.venv/bin/python scripts/local_gpu.py run work/local_gpu/kernel_r3 --out "$EVIDENCE/R6" --repeat "$N"
# 別途観測する場合だけ。既存 watchdog は上書きできない
.venv/bin/python scripts/local_gpu.py watch --out work/local_gpu/extra_watch/watchdog.csv --duration 21600
```

VRAM peak は10秒ごとの最大、watch は60秒 cadenceでclock/temperature/power/memory/utilization/UUIDを採取します。
clock は `utilization.gpu >= 50%` の sample を評価します。明示した solver interval が別途あればその区間も採用できますが、
本 wrapper は RUN 段の process envelope に JIT が含まれるため active interval を推定しません。
各時刻までの solver-active 最大 clock からの低下が15%未満を要求します。cold start の idle は含めません。
clock 低下の原因を thermal throttling と断定しません。
VRAM は各 solver-active interval の最初60秒を除いた range が device total の5%以下、
repeat peak 間の相対変動が2%以下（startupを含む全10秒sampleのpeak、分母は最大peak）を要求します。
R6 は6時間の cold-process loop の wrapper wall、連続・非重複 run、監視が全 loop を覆うこと、sample/loop間隔90秒以内も確認します。
これは6時間の GPU-active 計算を意味せず、solver wall の合計と wrapper wall に対する比を別記します。
90秒sample-gapと60秒first-sample allowanceは development defaults として `gate.json` に記録します。
lock 再確認や Julia 起動が長く loop 間隔を超えた場合は INCOMPLETE です。

reset observer は Windows System log の Display TDR event 4101（開始以降）を PowerShell 経由で読みます。
取得不能を「resetなし」にせず INCOMPLETE。これはその event の観測範囲であり、全種類の GPU reset を物理的に排除しません。
optional clock/temperature/power の欠測、required memory/utilization/UUID の欠測は INCOMPLETE です。
10秒 memory query の取得不能も INCOMPLETE、非有限値や不正な値は FAIL として扱います。
NVML query の部分対応、event visibility、solver-active 区間の観測は WSL2 実機で確認が必要です。

## 6. gate を一度だけ計算する

```bash
.venv/bin/python scripts/local_gpu_gate.py --runs "$EVIDENCE" --out "$EVIDENCE/gate.json"
```

既存出力は計算・verifier 呼出し前に拒否します。temporary file に完全に書いてから exclusive hardlink で
公開するため、計算例外で空の `gate.json` を予約しません。欠けた run/file は INCOMPLETE、
不正な JSON/hash/schema/identity は FAIL、DONE があるのに identity files がない矛盾も FAIL です。
再試行の可否は LOCAL-OF-01 §6 / LOCAL-GPU-01 に従う所有者判断です。

C1 は R1/R2 の全 force sample を byte 比較し、不一致なら
`abs(a-b)/max(abs(a),abs(b),1e-300) <= 1e-6`。非有限値・step 不一致は拒否します。
C2 は両 R2 へ `local_gpu.py verify --smoke` を subprocess 実行し、unchanged harness 検査を local profile で wrap します。
C3 は既存 evidence の manifest/table から SHA を読み、T4 の窓平均・全sampleとの最大相対差と UNC sigma_d を記述。
C4 は total reported steps×prod(flow_dims)/solver wall と T4 錨の比を記述します。T4 錨も参照 summary の
同じ式から導出し、その SHA を記録します（rev0 の丸めた5.5e7/5.6e7を使いません）。
登録 job の steps は初回 warmup1stepを含み wall はそれを除くため、通常の厳密な timed-step 推定値
(steps−1)×cells/wall も別記します。
C5 は R3/R5 の同一 identity と中断・実 restore の証拠を確認し、endpoint-clipped time-weighted な
窓統計を C1 級で比較。C6 は上記 telemetry と連続稼働の規則です。
PASS は C1 が BITWISE/TOLERANCE、C2/C5/C6 が PASS の場合です。C3/C4 の FAIL/INCOMPLETE は
記述として報告し、PASS を妨げません。観測された R1–R6 の CUDA UUID は一つに一致する必要があります。
R4 欠測時は未観測のまま記録し、R4 を実行済みとは主張しません。
`PASS` はこの lock の環境能力に限り、T4 force 同値、格子独立性、高Re/FSAE性能を意味しません。

## 7. WP4 checkpoint API と CPU 検証

```julia
# scripts/ 内の job から。src/ は登録済み directory pin のため変更しない。
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint
save_checkpoint(path, sim, step, rows; identity=study_geometry_sampling_sha)
state = load_checkpoint(path)
sim = construct_identical_fresh_simulation()
restore_checkpoint!(sim, state; identity=study_geometry_sampling_sha)
step, rows = state.step, copy(state.rows)
```

戻り値は NamedTuple。保存するのは u/p/u⁰、全Δt履歴、時刻、step、force rows、runtime/config identity。
モジュールは `julia/CFDSDFWaterLily/gen01/Checkpoint.jl` に置き、local campaign の kernel `pins` に明示します。
今後の GEN-01 追加モジュールも `gen01/` に置き、登録済み `src/` と既存 Manifest の bytes を保ちます。
標準 Flow/MultiLevelPoisson、同一 body/config、default `remeasure=true`、乱数なしが検証範囲です。
body closure / RNG / device pointer は保存せず、caller が必須の非空 identity で geometry と sampling を結びます。
restore は module 内でも identity を比較し、異なれば field を変更する前に拒否します。
`step` は個々の `mom_step!` の完了回数で `length(Δt)==step+1` を満たす必要があります。
`sim_step!(sim,t_end)` は複数 step を進めるため、その呼出回数を `step` にしてはいけません。
Julia版・WaterLily版・Manifest SHA・格子・型等が異なる復元は拒否します。
`Serialization` は自分が作成し信頼する checkpoint のみに使ってください。

```bash
.venv/bin/python -m pytest -q tests/test_local_gpu.py tests/test_local_gpu_backend.py tests/test_local_gpu_gate.py tests/test_local_gpu_julia.py
JULIA_NUM_THREADS=1 julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/checkpoint_selftest.jl
```

CPU 自己テストは64×32、100 step、50 step保存→新規sim再開、全sample/最終field/窓統計を比較します。
この結果から GPU 上の再開を資格化せず、実機 R5 で確認します。
起動・JIT・WSL2 launch 遅延、CUDA functional、NVML、optional bind、reset 可視性、native Windows比較、
GPU checkpoint、6時間安定性は実機の未確認事項です。
