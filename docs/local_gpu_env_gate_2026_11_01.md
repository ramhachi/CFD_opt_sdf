# LOCAL-GPU-01: environment gate for the user's RTX 4070 Ti (Windows 11 / WSL2) as a WaterLily backend — draft rev 0

要約（日本語）：ユーザーの手持ちの RTX 4070 Ti（Windows 機）を、WSL2 上の Linux で本リポジトリの WaterLily harness（Julia 1.12.6、WaterLily 1.8.0）の backend として使えるかを確かめる工学 gate です。LOCAL-OF-01（ローカル Docker の OpenFOAM）と同じ型で、物理の主張はせず、環境のロック、同一機での再実行の級（bitwise か許容差か）、GPU の identity、処理量（T4 との比）、長時間稼働とチェックポイント再開を記録します。合格すると、以後の登録 study は「backend = この GPU ＋ このロック」を固定して回せます。T4 の byte 参照は引き継げません（別 backend）。

Status: **draft rev 0 (2026-11-01), not frozen, no run made.** Plan context: GEN-01 rev 3.1 §5.3 and §7 interval I-b ([`gen_system_plan_2026_11_01.md`](gen_system_plan_2026_11_01.md)). Evidence class when run: engineering capability gate (like JOB-02 and LOCAL-OF-01), `EXPLORATORY_COMMITTED` rows in `docs/exploratory_index.md`, one independent source review before the first run. It changes no qualification flag.

## 1. Decision, question and scope

- **Question.** Can the registered WaterLily harness path (rendered Kaggle kernel runner → Julia job → `WaterLily.Simulation` on the GPU) run unchanged on the user's RTX 4070 Ti inside WSL2, with (a) a locked environment, (b) a declared reproducibility class on the same machine, (c) a recorded GPU identity, (d) a measured throughput relative to the Kaggle T4 anchors, and (e) checkpoint/resume and multi-hour stability?
- **Not asked.** Physics, grid independence, equivalence of forces with the T4 (a cross-GPU difference is recorded descriptively; it is expected because Float32 reductions and kernel schedules differ), or anything about the OpenFOAM verifier.
- **Why it exists.** GEN-01 rev 3.1 makes the 4070 Ti the default compute basis; AGENTS.md and the harness require a registered backend identity, and the T4 byte references (`job02_gate_2026_10_19`, UNC-01, SCREEN-01) do not carry over to another GPU architecture.

## 2. Environment lock (`infra/local_gpu/lock.json`, committed before the first run)

| item | how it is recorded |
| --- | --- |
| Host | Windows 11 build (`winver`; **hold Windows preview updates**: microsoft/WSL#42107, open 2026-10-29, reports `cuInit(0)` segfaulting in WSL2 after preview update KB5127936 on an RTX 5090), NVIDIA Windows driver version (r535+ required for CUDA on WSL2; `nvidia-smi` on Windows). The WSL2 guest uses the host driver through the stub `/usr/lib/wsl/lib/libcuda.so`; **no Linux display driver is installed** (NVIDIA CUDA-on-WSL user guide). Hardware-accelerated GPU scheduling on (NVIDIA's recommendation for launch-latency-bound workloads) |
| WSL2 | WSL version (`wsl --version`), kernel (`uname -r`), distribution (Ubuntu 24.04 LTS expected), `/etc/wsl.conf` with `[gpu] appendLibPath=true` and `[automount] ldconfig=true` (so `/usr/lib/wsl/lib` is on the library path without `LD_LIBRARY_PATH` hacks), `.wslconfig` `memory`/`processors`/`swap` (defaults: 50 % of host RAM, 25 % swap; these cap guest RAM, not VRAM) |
| GPU identity | `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap,power.limit --format=csv` inside WSL2 (NVML is only partially supported on WSL2; CUDA.jl's NVML assertion failing is known and harmless); `CUDA.versioninfo()` and `CUDA.functional()` from Julia (CUDA.jl downloads its own runtime artifacts; only the driver is host-provided); whether the card is the 4070 Ti (12 GB, 192-bit, 504 GB/s, 285 W, 7680 cores) or the 4070 Ti SUPER (16 GB, 256-bit, 672 GB/s, 285 W, 8448 cores); FP64 is 1/64 of FP32 on this architecture (Float64 work belongs on the CPU) |
| Power limit | `nvidia-smi -pl` value if set (Windows side); recorded because WaterLily is bandwidth-bound and a power cap costs little |
| Julia | 1.12.6 by the same SHA-256 the Kaggle runner template pins (`src/cfd_harness/campaign_runner_template.py`); installed from the official tarball into WSL2 |
| Packages | `julia/CFDSDFWaterLily/Project.toml` + `Manifest.toml` as committed (WaterLily 1.8.0, CUDA.jl version from the Manifest); `Pkg.instantiate()` with the depot path recorded; the Manifest SHA-256 |
| Harness | `scripts/local_gpu.py` (new, modelled on `scripts/local_openfoam.py`): runs a rendered kernel `runner.py` unchanged with `/kaggle/working` and `/kaggle/input/<slug>` provided as bind-equivalent directories (a WSL2 path mapped to the same absolute paths through a chroot-free prefix: the runner's paths are rewritten only through environment variables already honoured by the runner, or the kernel is run inside the same Docker image the project uses for Kaggle emulation if one exists; the chosen mechanism is part of the lock) |
| GPU pinning | `CUDA_VISIBLE_DEVICES=0`; `used_gpu_count = 1` as in the registered kernels |
| Reproducibility class | declared in advance (section 5): `BITWISE` or `TOLERANCE(1e-6)` |

The lock is frozen by SHA-256 before run R1. Any change (driver update, Windows update that changes the WSL kernel, Julia or Manifest change) makes a new environment and a new gate (as LOCAL-OF-01 C3).

## 3. Runs (all `EXPLORATORY_COMMITTED`, rows written before each run)

| run | what | reference | purpose |
| --- | --- | --- | --- |
| R0 | WaterLily's own Taylor-Green benchmark (128³, Float32) and a 2D plate case, in WSL2 and, as a comparison arm, in native Windows Julia + CUDA.jl (also supported; WaterLily v1.10.0's release benchmarks ran on a Windows laptop RTX A2000 at ≈ 19.8 ns/DOF/step) | published anchors: H100 1.57 ns/DOF/step; T4 ≈ 18 ns/cell-step in this repository | launch-latency overhead of WSL2 (WaterLily launches many small multigrid kernels); if WSL2 is > 25 % slower than native Windows, the gate records it and the user decides the host OS for the harness (the harness itself is POSIX-only, so native Windows would need a port) |
| R1a, R1b | HARNESS-01 smoke v1.1 (1 state, GRID-02 f16 parent, flow_16) twice from a cold Julia process | its T4 force CSV `97e7b43c…` | same-machine reproducibility class; cross-GPU difference (descriptive) |
| R2a, R2b | UNC-01 U01 smoke (v18 parent, native phase, flow_24) twice | T4 `smoke_verify_table.json 409552a1…` | same on the current parent and grid; `verify --smoke` must pass on the local output |
| R3 | flow_32 parent, one phase, full window (the SCREEN f32a parent at phase 13) | T4 force CSV of f32a | throughput anchor (steps, wall, cell-steps/s), VRAM, cross-GPU force difference (descriptive) |
| R4 | flow_48 parent, one phase | T4 f48k13 | throughput at the confirmation grid; VRAM |
| R5 | R3 repeated with a kill at ~50 % and a resume from the job's checkpoint (to be added to the job if absent) | R3 | checkpoint/resume: the force window statistics must equal R3 within the declared class |
| R6 | 6 h continuous loop of R3-sized runs | — | thermal throttling (`nvidia-smi` clocks and temperature every minute), driver resets, WSL2 memory pressure |

## 4. Readouts

Per run: `local_run.json` (lock SHA, GPU identity, `CUDA_VISIBLE_DEVICES`, Julia version, Manifest SHA, wall per stage, peak VRAM, steps, force CSV SHA-256, exit code, `DONE`), the force CSV, the watchdog CSV (clocks, temperature, power every 60 s for R6), and the comparison against the T4 reference: max relative difference of the force window means and of every sample.

## 5. Criteria (computed once by a frozen `scripts/local_gpu_gate.py`)

| criterion | rule | result class |
| --- | --- | --- |
| C1 same-machine reproducibility | R1a = R1b and R2a = R2b byte for byte on the force CSVs → `BITWISE`; else max relative difference ≤ 1e-6 on every force sample → `TOLERANCE`; else `FAIL` | the class is recorded in the lock and inherited by every registration on this backend |
| C2 harness verification | `verify --smoke` passes on R2 outputs (identity SHAs, schema, window) | pass / fail |
| C3 cross-GPU difference | relative difference of window means vs the T4 reference, descriptive; reported with the T4 phase SD (UNC-01 σ_d) for scale | descriptive only (no pass/fail) |
| C4 throughput | cell-steps/s on R3 and R4; ratio to the T4 anchors 5.5e7 (f32) and 5.6e7 (f48) | descriptive; feeds `gen_cost_wl.py` by the pre-written formula (engineering parameter only) |
| C5 resume | R5 window statistics equal R3 within the class of C1 | pass / fail |
| C6 stability | no driver reset, no non-finite value, clock drop < 15 % over R6, VRAM stable | pass / fail (a fail is reported with the cause; a power limit may be applied once and R6 repeated, recorded) |

**PASS** = C1 ∈ {BITWISE, TOLERANCE} and C2, C5, C6 pass. Anything else is `FAIL` with the failing criterion; one repeat of the failing run is allowed after a recorded infrastructure fix limited to paths, mounts, environment variables or the power limit (LOCAL-OF-01 §6 rule).

## 6. Consequences of a PASS

- Registrations may name `backend = {gpu: "NVIDIA GeForce RTX 4070 Ti", lock: <sha256>}` and must pin it; a study never mixes GPUs; a GPU change requalifies through a new gate.
- T4 byte references are not reused on this backend; the first registered study on it (RES-00) measures its own σ_d and references.
- Kaggle T4×2 remains a second backend for parallel small jobs, with its own identity (both GPUs used only after a one-line harness change that is itself gated).

## 7. Scope of a pass, and what is not claimed

A pass says the harness runs, reproduces itself to the declared class, and how fast. It does not say the forces equal the T4's, that WaterLily is correct at any Re, or anything about the OpenFOAM verifier (which stays on LOCAL-OF-01's Docker image on the Mac or a CPU machine).

## 8. Procedure

1. Commit `infra/local_gpu/lock.json` and `scripts/local_gpu.py` with tests (stub runner, lock refusal on mismatch); one independent source review (blockers fixed before any run).
2. Write the exploratory_index rows; run R1-R6 in order; archive outputs under `docs/evidence/local_gpu_gate_2026_11/` with `SHA256SUMS`.
3. Run `scripts/local_gpu_gate.py` once; commit `gate.json` and this document's section 9 (results), append-only.

## 9. Results (to be filled once; append-only)

(not run)
