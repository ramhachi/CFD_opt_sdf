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

## 10. Amendment 1 (2026-11-06, before any run): what WP1's first attempt found and how the gate changes

Codex's first implementation attempt (`docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_*`) stopped as BLOCKED on four real contradictions between this draft and the registered harness. The draft is amended as follows; this section overrides §2-§5 where they conflict.

1. **"Unchanged runner" is impossible: the registered runner and verifier are T4-only.** `scripts/grid01_gpu.py` rejects any visible GPU that is not a Tesla T4 before Julia starts; `src/cfd_harness/campaign_schema.py` (`GPU_EXPECTED`) and `campaign_verify.py` require it too. Resolution: the harness gains a **backend profile** (new module `src/cfd_harness/backend_profiles.py`): the default profile `kaggle_t4` reproduces today's behaviour byte for byte (every existing campaign, freeze and rendered kernel is unchanged; a test renders an existing campaign with the default profile and asserts byte identity with the committed kernel); a second profile `local_rtx4070ti` names the accepted GPU by `nvidia-smi` name (and, when present, UUID) and `used_gpu_count = 1`. Kernels for the local backend are **re-rendered with the profile** by `scripts/local_gpu.py render`, and `verify --smoke` accepts the profile recorded in the campaign. The runner's identity check therefore runs, with the local profile, instead of being bypassed.
2. **The T4 byte gate of the existing campaigns is not a local criterion.** On the local backend the comparison with T4 references is descriptive (C3), and the gate is the same-machine repeat (C1). `first_state_csv_sha256`-type gates in existing campaigns stay as they are for Kaggle; the local profile records the local first-state SHA as its own reference once C1 passes.
3. **Julia projects.** GPU runs use the registered GPU project `julia/CFDSDFWaterLilyT4` (WaterLily 1.8.0 + CUDA 6.3.1), exactly as the Kaggle runner does; the lock pins that project's `Manifest.toml` SHA-256. CPU self-tests (checkpoint, force tests) use `julia/CFDSDFWaterLily`. Neither Manifest is modified.
4. **Checkpoint/resume needs a job that calls it.** The registered jobs are not edited. WP1 creates `scripts/waterlily_local_gpu_job.jl` as a **copy** of `scripts/waterlily_lowdim02_flow32_job.jl` whose only additions are the `Checkpoint.jl` save/resume calls (period and path from environment variables) and an unchanged force CSV; the diff is committed as `scripts/waterlily_local_gpu_job.diff`. R3 and R5 use this job; R1/R2 use the existing jobs through the re-rendered kernels. C5 compares R5 with R3 within the C1 class.
5. **Tooling notes for Codex.** Commit through the shared Git directory (`/Users/sota/projects/FomulaTMU/CFD2026_09/.git`, made writable for the sandbox), use the `gh` CLI for the PR (not a GitHub connector), and keep the first attempt's three report files under `reports/wp01_attempt1_blocked/`.

Everything else (lock contents, runs R0-R6, criteria C1-C6, the procedure, the claim ceiling) stands.

## 11. Amendment 2 (2026-11-06, before any run): what the Opus source review of WP1 (PR #88) found and how the gate changes

1. **The harness v1.1 tool files are not edited.** `src/cfd_harness/campaign_schema.py` is a `BASE_PIN` and, with `campaign_build.py` and `campaign_verify.py`, a `TOOL_FILE` whose SHA-256 every registered prerun freeze and the UNC-01/FID-01/SCREEN-01 `freeze1.json` record. WP1 attempt 3 edited all three; re-verifying the committed UNC-01 U01 outputs at that tree changed `harness_tool_sha256` and failed the smoke re-verification (the new schema SHA entered the runner PIN block). The three files are restored byte for byte. The local backend lives entirely in `src/cfd_harness/backend_profiles.py` and `scripts/local_gpu.py`: the local renderer builds on `campaign_build.pin_block`/`pins` without modifying them, the adapted runner strips `backend_profile` before calling the unchanged `validate_campaign` and loads `backend_profiles.py` by path from the pinned checkout, the module is a top-level pin of the local campaign, and a local verifier wraps the unchanged harness checks with the local GPU selector, probe and `gpu_name`. A regression test re-verifies the committed UNC-01 U01 smoke and formal outputs from the current tree and asserts byte-equal tables; this test is the guard for every later change under `src/cfd_harness/`.
2. **PASS rule (§5) stands as written**: PASS = C1 ∈ {BITWISE, TOLERANCE} and C2, C5, C6 pass; C3 and C4 are descriptive and are reported, never block. The gate script is corrected to this.
3. **C6 is re-specified.** (a) The clock-drawdown rule is evaluated over solver-active samples only (samples whose `utilization.gpu` ≥ 50 %, or that fall inside the solver intervals the runner records), not over the idle cold start of each repeat. (b) VRAM stable: after the first 60 s of each solver-active interval, `memory.used` varies by ≤ 5 % of the device total within the interval, and the per-repeat peak varies by ≤ 2 % across repeats. (c) A missing optional telemetry field (`power.draw`, `temperature.gpu`, `clocks.sm`) makes C6 INCOMPLETE, not FAIL; a missing required field (`memory.used`, `utilization.gpu`, the UUID) makes the run INCOMPLETE. (d) The 90 s sample-gap and 60 s first-sample allowances are development defaults recorded in `gate.json`.
4. **C3 anchors** are derived from the C3 reference summaries by the gate's own formula (cells × steps / solver wall) and recorded with the reference's SHA; the literal 5.5e7/5.6e7 anchors of rev 0 are replaced by those derived values (the f48k13 reference gives 5.07e7, f32a 5.48e7 by that formula). C3 also records the per-sample maximum relative difference against the T4 reference (§4).
5. **Identity, before the first run.** The lock hashes the Julia installation root (`campaign_schema.sha256_path`) and pins a dedicated `JULIA_DEPOT_PATH` whose Manifest-resolved package tree SHA is recorded; the runner records a filtered environment snapshot (`JULIA_*`, `CUDA_*`, `NVIDIA_*`, `WSL*`) in `local_run.json` and in the run identity; one CUDA UUID is required across R1–R6 and recorded in `gate.json`; `used_gpu_count` evidence is the probe's `logical_device_count` (the literal written by the runner is bookkeeping); the checkpoint identity is mandatory on save and compared on restore; `gate.json` is written to a temporary file and linked with exclusive create; a run marked DONE without its identity files is FAIL, not INCOMPLETE. HAGS state is recorded when readable.
6. Evidence class unchanged: nothing in this amendment is a measurement.

### 11.7 Amendment 3 (2026-11-07, after the second Opus review of WP1, PR #88): telemetry requirements and identity comparison

1. **C6 telemetry.** Required for C6: `memory.used` and `utilization.gpu` (and `clocks.sm` for the clock rule); `power.draw` and `temperature.gpu` are recorded only and never affect the status. The GPU identity for R6 telemetry is the NVML UUID when NVML reports one, otherwise the CUDA-probe UUID of the same run, recorded as such; neither case makes C6 INCOMPLETE by itself. (§11.3(c) is narrowed accordingly: PASS must be reachable on WSL2 with partial NVML, which is the case the LOCAL UUID fallback exists for.)
2. **C6 active groups.** The VRAM rule applies to solver-active intervals with at least two samples after their first 60 s; a repeat needs at least one such interval; shorter groups (a probe, JIT, a single dip that splits an interval) are recorded and skipped, not INCOMPLETE.
3. **Identity comparison.** The filtered environment snapshot is still recorded in full, but a named volatile set of per-session socket/pid paths (`WSL_INTEROP`) is excluded from the C1/C5 identity comparison; the excluded names are listed in `gate.json`. The watchdog CSV schema check is set equality, not subset.
4. **Record field.** The `finished_utc` of the full-pytest and source-stability records is the write time and is renamed `written_utc`.
