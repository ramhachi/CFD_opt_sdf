# Kaggle background GPU runbook (K0, W1g, W2-T4b, W2b, and W3)

This is the execution path for the SDF-native WaterLily GPU line. The
authoritative order and gate status are in [`phase_plan.md`](phase_plan.md),
and the numeric K0 contract is
[`evidence/kaggle_k0_criteria_2026_09.json`](evidence/kaggle_k0_criteria_2026_09.json).
The existing Colab evidence remains a reference. No sampled-sphere, v16, or
optimizer result follows from K0 or W1g alone.

Kaggle is an execution substrate for reproducible GPU batches, exact
source/runtime binding, and evidence capture. It is not a solver or optimizer
component in the SDF-native architecture. This runbook records operational
procedures and result history; `phase_plan.md` alone sets the current
architecture, gate status, and execution order.

K0-A–F passed on 2026-09-27. Version 1 was the GPU inventory smoke; version 2
ran the Julia environment, analytic sphere and dual-process checks. W1g
version 3 completed as a diagnostic, but was not accepted because the fixture
at its pinned source checked only the x components for finiteness. The
round-2 source checks every CPU/GPU normal component and was registered before
the next GPU run. The append-only K0 result is
[`evidence/kaggle_k0_result_2026_09.json`](evidence/kaggle_k0_result_2026_09.json).

## Audit corrections to the migration draft

- The current repository has no `ColabBackend` to swap out. Its
  `src/cfd_sdf/execution.py` runs OpenFOAM cases. K0 uses a standalone script
  kernel and the existing Julia job; no solver or OpenFOAM abstraction changes.
- The machine's installed Kaggle CLI 1.7.4.5 lacks `--accelerator` and
  `kernels logs`. The commands below use the checked 2.2.4 CLI through `uvx`.
- Cross-backend acceptance is registered **before** Kaggle measurements:
  relative window-mean-drag difference at most `1e-4` versus the Colab
  W2-T4a fixture, and each concurrent GPU process at most `1e-6` versus the
  single-GPU Kaggle run. A result cannot be used to relax these values.
- The K0 source fetched by version 2 is the exact public commit
  `d81d0ccd13379fc86de48d52a797e6e7612658bd`. W1g versions pin their own
  registered source commits. The Julia binary and Project/Manifest are
  SHA-256 checked. Internet is enabled on the **private** Kaggle kernel for
  those downloads. No credential is in the repository or upload folder.
- GPU UUIDs and driver versions from Colab are machine identities, not
  portable acceptance criteria. Kaggle records its own identities and
  requires two Tesla T4 GPUs plus pinned Julia package versions.

Kaggle's official [CLI reference](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
documents `push`, `status`, `logs`, and version-specific `output`; its
[metadata reference](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
defines private script kernels and `NvidiaTeslaT4`. The Julia 1.12.6 Linux
binary digest is from the [Julia release archive](https://julialang.org/downloads/oldreleases/).

## K0 historical collection

K0 version 2 has completed. The commands below retrieve that historical run;
they do not submit another K0 campaign. The kernel directory now carries the
W1g runner described in the next section. Kaggle credentials stay in the
user's normal CLI configuration; do not print or upload them.

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-k0/2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-k0/2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-k0/2 -p work/kaggle_k0_version2
python3 scripts/verify_kaggle_k0.py work/kaggle_k0_version2
```

Replace `2` and the output directory together for a later version. The
verifier checks all files in the SHA-256 manifest, the immutable local
criteria and Colab reference, completion/finite/force gates, cross-backend
drag bound, and distinct overlapping GPU 0/1 process intervals. `DONE` is
written only after the remote K0-A–E gates pass. Treat `ERROR.txt` or a
missing `DONE` as a failed diagnostic run, even if the kernel worker finished.

The remote script writes outputs only under `/kaggle/working/k0`; Julia,
packages, and the fetched source live in temporary storage. Re-submission
starts a clean Kaggle version. The result folder in `work/` is host-local and
ignored by Git; any accepted small evidence record must point to its exact
version and include file hashes.

## K0 to W1g boundary

Once all K0-A–F gates pass, record the outcome in the phase plan and a new
append-only evidence file. W1g requires a new Kaggle backend identity and its
own registered criteria; the Colab W0b GPU UUID cannot be reused. Keep
`shape_update_allowed=false`, `sdf_gradient_qualified=false`, and all
optimizer work blocked. The existing `scripts/waterlily_w2t4_job.jl`
supports only `analytic` at this boundary; `gridsdf` is still reserved for
the later sampled-sphere step.

## W1g: GPU GridSDF contract check

W1g round 2 pins source commit `f01462a44bf8b8cbefb0f5f7977916be94687b6c`
and criteria SHA-256
`717053a2e4cb32d16cbbc2e3de2007371c1046f365f76a404cb166322adaadcb`.
It checks 200,012 registered probes on one selected Tesla T4, while recording
both T4 UUIDs in the run output. G3 requires every CPU/GPU distance and all
three components of each CPU/GPU normal to be finite. This is geometry
contract and numerical agreement evidence only; it does not qualify a solver
step, force, gradient, topology update, or optimizer.

Submit and collect each round by explicit Kaggle version. For the currently
registered round, the expected version is 4:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-k0/4
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-k0/4
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-k0/4 -p work/kaggle_w1g_version4
python3 scripts/verify_kaggle_w1g.py work/kaggle_w1g_version4
```

Version 4 completed on 2026-09-27. The verifier checked all 11 files against
the remote SHA-256 manifest and independently recomputed G1–G9. Maximum
world-distance error was `3.5762787e-7 m` against `1e-5 m`; maximum unit-normal
error was `2.4211522e-7` against `1e-3`; sign violations were zero over 199,321
gated probes. The two-T4 inventory, selected UUID, driver/runtime cohort,
source commit, runner hash, and Project/Manifest hashes matched. The
append-only outcome is
[`evidence/kaggle_w1g_round2_result_2026_09.json`](evidence/kaggle_w1g_round2_result_2026_09.json).

Use the version printed by `push` if it is not 4, and change both the output
reference and directory to match. The verifier checks the output file
manifest, registered criteria and prerequisite hashes, uploaded runner hash,
source commit, fixture parameters, runtime/GPU identity, and recomputed G1–G9
gates. A failed run is retained as diagnostic evidence. Only a fully verified
round-2 pass opens the next planned slice, W2-T4b.

## W2-T4b: sampled-sphere CUDA primal

W2-T4b is registered in
[`evidence/kaggle_w2t4b_criteria_2026_09.json`](evidence/kaggle_w2t4b_criteria_2026_09.json)
(SHA-256 `4617f98ca2cd95e60baba4c86d78f66aa8dff2261ff688e17f06a00ab06fc444`)
against implementation commit `99c013a089b196975c190d413e4b4103ccbe755e`.
It runs the canonical sampled sphere on one visible T4 (`CUDA_VISIBLE_DEVICES=0`)
and records the complete two-T4 inventory. The CPU-to-Kaggle sampled drag
bound is 1%; the sampled-to-analytic T4 Cd bound is the existing 10% W2a
cross-geometry bound. The other preregistered checks cover finite fields and
forces, sign, stationarity, canonical phi/margin and round-trip hash, runtime,
VRAM, backend identity, and artifact transport. No gradient, reverse mode,
topology, grid convergence, or optimizer claim follows from this run.

At W2-T4b round 1, after W1g version 4, the expected Kaggle version was 5.
The commands below collect that now-historical diagnostic:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-k0/5
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-k0/5
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-k0/5 -p work/kaggle_w2t4b_version5
python3 scripts/verify_kaggle_w2t4b.py work/kaggle_w2t4b_version5
```

Use the actual version printed by `push` if it differs. The verifier requires
the exact registered criteria hash, runner/source/Julia environment identity,
version-specific output manifest, force CSV hash/schema/count, and independently
recomputed T0–T12 gates. A missing `DONE`, `ERROR.txt`, or a failed gate remains
diagnostic and does not qualify W2-T4b.

Version 5 completed the sampled-sphere primal, but the Kaggle worker returned
`ERROR` because only T9 failed. The force, stationarity, CPU agreement,
sampled-to-analytic Cd, runtime, VRAM, backend and prerequisite gates passed.
All 14 files in its SHA-256 manifest match the local download under
`work/kaggle_w2t4b_version5/w2t4b`; there is no `DONE` marker, so the output is
diagnostic only. See
[`evidence/kaggle_w2t4b_round1_diagnostic_2026_09.json`](evidence/kaggle_w2t4b_round1_diagnostic_2026_09.json)
for the version, source, criteria, metrics, gate results, and artifact hashes.

## W2-T4b round 2 retry

The append-only round-2 criteria were
[`evidence/kaggle_w2t4b_criteria_2026_09_round2.json`](evidence/kaggle_w2t4b_criteria_2026_09_round2.json)
(SHA-256 `85bd5ba4f6ff0a13c7f0509b1ba86b74cfeb7bc346fc590b27a819ce3f228e66`).
All numerical thresholds are identical to round 1. The only correction is
telemetry semantics: `phi_margin_m` is recomputed with
`zero_level_margin_m(phi, origin, h)`, and `phi_margin_gate_m` separately
records the constructor's registered `0.15 m` gate. The repaired job is pinned
to source commit `2da94a92ffb9af55dfc159068ace8f25c55c0e6c`. The retry used
Kaggle version 6:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-k0/6
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-k0/6
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-k0/6 -p work/kaggle_w2t4b_version6
python3 scripts/verify_kaggle_w2t4b.py work/kaggle_w2t4b_version6
```

Use the version actually returned by `push` and keep it matched across
`status`, `logs`, `output`, and the output directory. A missing `DONE`, an
`ERROR.txt`, any hash mismatch, or any failed independent gate is diagnostic;
do not alter round-2 thresholds after seeing the result.

Version 6 completed and passed the round-2 criteria. Host verification checked
13 manifested files and independently recomputed all gates. Measured margin
was `0.19999998807907104 m`, distinct from the recorded `0.15 m` gate;
window-mean drag was `88.2360589943` (relative difference `2.86e-5` from the
CPU sampled fixture), and `Cd=0.8777003092` (relative difference `0.00215`
from analytic T4). The append-only result is
[`evidence/kaggle_w2t4b_round2_result_2026_09.json`](evidence/kaggle_w2t4b_round2_result_2026_09.json).
It qualifies only the registered sampled-sphere CUDA primal capability and
agreement gates at 16 cells/D. The next slice is W2b; its separate
16/24/32 cells/D flow-grid matrix and gates are registered below before the
first ladder measurement.

## W2b: registered three-resolution flow-grid ladder

The six-case matrix and numerical bounds remain those registered in
[`evidence/kaggle_w2b_criteria_2026_09_round1.json`](evidence/kaggle_w2b_criteria_2026_09_round1.json)
(SHA-256 `eab8213461d95a714910a2055a957d3614f1e257dcc79197f6068cd35a04b1bd`).
Version 7 exposed that round 1's source commit was a mistyped, nonexistent SHA;
that attempt failed at T0 before any solver case. The immutable diagnostic is
[`evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json`](evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json)
(SHA-256 `5df35a54ea1755ea12cf70b180618fdfc99700c6958334312a2b43e48f38ec91`).
Round 2 is registered at
[`evidence/kaggle_w2b_criteria_2026_09_round2.json`](evidence/kaggle_w2b_criteria_2026_09_round2.json)
(SHA-256 `36c4cc138af4c30e022ddad9993798dfea6c8432cc72c4d216fb4cc569ce4cb5`).
It corrects only the source commit pin to the actual job commit
`548231050fc6ca22bc1c0394272564f81571dbbc`; the fixture, input hashes, and
all numeric bounds equal round 1. Its version 8 run passed source fetch, all
20 pinned input hashes, and Julia Project/Manifest instantiation. The T4 smoke
passed `CUDA_FUNCTIONAL`, CuArray, and KernelAbstractions checks, but the
observed CUDA runtime was 12.8.0 rather than round 2's registered 13.3.0. The
CUDA driver API value was 13.3.0; the NVIDIA driver from `nvidia-smi` remained
580.159.04. The no-solver diagnostic is
[`evidence/kaggle_w2b_version8_runtime_diagnostic_2026_09.json`](evidence/kaggle_w2b_version8_runtime_diagnostic_2026_09.json)
(SHA-256 `08385ba971be70ad08fa73fa6d5f6587fa89b4137d3fded4c922ab15d6fc000d`).

Round 3 is registered at
[`evidence/kaggle_w2b_criteria_2026_09_round3.json`](evidence/kaggle_w2b_criteria_2026_09_round3.json)
(SHA-256 `3573b903c2ff025db62cb184ba328f81c48da70f72d4393e3623bd3bbb58bf1c`).
It registers the observed CUDA runtime 12.8.0 and records the CUDA driver API
version separately as 13.3.0. The source pin, fixture, input hashes, Project,
Manifest, and every numerical bound equal rounds 1 and 2. It compares analytic and canonical GridSDF
spheres at 16, 24, and 32 cells/D on identical dimensionless domains at
Re_D=100. The registered bounds require
each per-rung geometry Cd pair within 1%, the 16-cells/D drag values within 1%
of the W2-T4a/W2-T4b references, and the 24-to-32 cells/D Cd change within 3%
for each geometry. The 3% value is a PoC candidate bound, not formal GCI or
absolute-accuracy evidence; all six cases must also pass the registered
finiteness, force, stationarity, phi, runtime/VRAM and T4 identity gates.

Rounds 2 and 3 pinned the solver job to
`548231050fc6ca22bc1c0394272564f81571dbbc`. Version 9 fetched that source,
verified its inputs, passed T4 smoke, and completed `analytic_16` through
`t_end=60`. Host recomputation matched its 561-sample force CSV and reported
time-weighted Cd `0.879587436031`. The Julia script then stopped before case 2:
top-level `case_count += 1` raised a soft-scope `UndefVarError`, and the
`W2B_JOB_DONE` marker was absent. The six-case matrix is incomplete; the single
case is diagnostic only and is not reused for round 4. All 12 retrieved output
hashes and the kernel-log hash verify. The immutable failure diagnostic is
[`evidence/kaggle_w2b_version9_partial_failure_diagnostic_2026_09.json`](evidence/kaggle_w2b_version9_partial_failure_diagnostic_2026_09.json)
(SHA-256 `43ffa63058606638cd70f2bfbd18c68c8521a3fa67c81ad9bf03ebd8f7b3f35e`);
the kernel log SHA-256 is
`d12a2e07f65bdfe5c7a8811fa8fd5fbd4d29239a5790014abe045b7322a21ee3`.

The counter-only fix is source commit
`a29e282982a923e0a93ed31d3643e59c7ec6e42e`; the job hash is
`cc351f6eb5f8ca8f2bc210100f82b46481335003a818d45466757f588ffd0440`. It removes
the mutable top-level counter and prints the registered tuple length only
after all six cases return. Round 4 is registered at
[`evidence/kaggle_w2b_criteria_2026_09_round4.json`](evidence/kaggle_w2b_criteria_2026_09_round4.json)
(SHA-256 `4b5789d4dcf2e9b79b10eb5e388d5a56951df5c835f0c993903527463b6a82d0`).
It updates the source/job pin for the counter fix; runtime identity, fixture,
all other inputs, and every numerical threshold equal round 3. The round-9
partial measurement remains diagnostic and the round-4 solver has not started.

Kaggle version 10 fetched the round-4 source, passed the registered T4 smoke,
and completed `analytic_16` through `t_end=60.0000228882`; host recomputation
matched its 561-sample force CSV (time-weighted Cd `0.8795874360307699`). The
next case, `gridsdf_16`, stopped in `build_body` before solver integration:
`zero_level_margin_m` was defined in `CFDSDFWaterLily.GridSDFBody` but called
unqualified from `Main`. The exact 12 retrieved output hashes and kernel log
verify. The immutable partial diagnostic is
[`evidence/kaggle_w2b_version10_partial_failure_diagnostic_2026_09.json`](evidence/kaggle_w2b_version10_partial_failure_diagnostic_2026_09.json)
(SHA-256 `b2df282a40d776abeaf3ec63b086c4e297e6ffe1bafdd1de3b44d17a415f7cec`);
the kernel-log SHA-256 is
`1ce4d69aec373c4d20e86937b2868b771f8a58390f1209289e2579481ba2ed97`. The
single analytic case remains diagnostic and is not reused for acceptance.

The source fix qualifies the existing helper as
`CFDSDFWaterLily.GridSDFBody.zero_level_margin_m`, without changing its
implementation or any solver parameter. It is committed as
`65dbb015994e34669ec5d22f671b97128eaf87d2`; the new registered job SHA-256 is
`eaedc02478ee1b966dce3ecb24bc9b8bb2b41223706f9ea1a71c070619c53e15`. Round 5
is registered before its first measurement at
[`evidence/kaggle_w2b_criteria_2026_09_round5.json`](evidence/kaggle_w2b_criteria_2026_09_round5.json)
(SHA-256 `32c1fb8a80658a9ea37713c477c6ededcc0808d5cbb8bbd07d91a2b83ed1eb47`).
It changes only the pinned source commit/job hash from round 4; backend, fixture,
other input hashes, and all numerical thresholds are identical. The round-5
solver has not started. Before version 11, all 6 focused W2b tests, Python
`compileall`, diagnostic output/kernel-log hashes, and `git diff --check` pass.
Full pytest reports 1049 passed, 37 failed, and 4 skipped. Re-running the 37
failures alone reproduces only `FileNotFoundError` for ignored `work/` evidence
files absent from this managed worktree; none is a W2b test.

Kaggle version 11 completed the round-5 six-case ladder. The exact-version
download contains 23 files; the host verifier checked every manifest hash,
recomputed all force-window metrics from the six raw CSVs, and passed T0-T13.
The immutable result record is
[`evidence/kaggle_w2b_round5_result_2026_09.json`](evidence/kaggle_w2b_round5_result_2026_09.json)
(SHA-256 `8edf0d36cb706e9f6862faf7ea44845b100c3213433e94ae334251c16c94cccc`);
the downloaded manifest SHA-256 is
`6c6c940605c76007f171bb8b5ffcf21b50d060ef9ec6b8cfd2514d258fd3bb87`, and
the Kaggle log SHA-256 is
`cc65a38d805b74bf920f41371b542cc674ad919c3be9a7d413757796573cc44d`. At each
resolution, analytic-versus-GridSDF time-weighted Cd differs by 0.209-0.243%.
The 24-to-32 cells/D response is 1.903% analytic and 1.869% GridSDF, below
the registered 3% PoC candidate bound; both changes are smaller than their
16-to-24 changes. This closes only the registered sphere-fixture W2b gates;
it does not establish formal GCI, asymptotic order, absolute Cd accuracy, or
target-vehicle physics. The grid-response and shape-update qualification flags
remain false.

W2b uses its own private Kaggle kernel,
`ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder`. Version 7 failed at source
fetch before any solver case began because the round-1 source SHA was mistyped.
Its exact error and retrieval hashes are recorded in
[`evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json`](evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json)
(SHA-256 `5df35a54ea1755ea12cf70b180618fdfc99700c6958334312a2b43e48f38ec91`).
The runner fetches the advertised feature branch shallowly, then checks out the
exact registered source commit and verifies it. This fetch-and-checkout path
was locally tested against the pinned commit and all 20 registered source,
Project, and Manifest hashes. The Kaggle CLI
resolves the kernel slug from the title, so the metadata ID uses that same
slug. Before version 7, the focused W2b contract test passed (4 tests), the Julia
parser, Python compilation, criteria/input hashes, and `git diff --check` passed.
After registering round 2, the focused tests and corrected branch-fetch probe
passed. Before version 9, round-3 focused tests passed (4 tests); Python
`compileall`/syntax checks, metadata and criteria JSON parsing, criteria-chain
and sidecar hashes, all 8 version-8 output hashes, the kernel-log hash, CUDA
identity binding, the Julia parser, and `git diff --check` also passed. The
full suite reported 1047 passed, 37 failed, and 4 skipped. Re-running only the
37 failures confirmed they all depend on ignored `work/` evidence artifacts
absent from the fresh managed worktree (including an STL load that fails after
its registered file is missing); the focused W2b tests are not among them.
Before version 10, round-4 focused tests passed (5 tests), including a
regression assertion for the top-level completion counter. Python
`compileall`/syntax checks, metadata and criteria JSON parsing, criteria-chain
and sidecar hashes, all 12 version-9 output hashes, the kernel-log hash, the
Julia parser and top-level marker check, and `git diff --check` passed. The
full suite reported 1048 passed, 37 failed, and 4 skipped. Re-running the 37
failures confirmed they still depend on ignored `work/` evidence artifacts
missing from this managed worktree.
After retrieval,
the host verifier checks every manifest hash and recomputes the force means,
time-weighted coefficients, stationarity and all registered gates from the raw
force CSVs.

```bash
PYTHONPATH=src:scripts .venv/bin/python -m pytest -q tests/test_kaggle_w2b.py
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w2b --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/11
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/11
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/11 -p work/kaggle_w2b_version11
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w2b.py \
  work/kaggle_w2b_version11
```

Use the version actually returned by `push` consistently in all four Kaggle
commands and the retrieval path. Version 11's exact output passed host
verification as recorded above. For any later round, a missing `DONE`,
`ERROR.txt`, hash mismatch, or failed gate remains diagnostic; do not relax
numerical thresholds after seeing solver results. Rounds 2 through 5 preserve
round-1 numerical bounds.

## W3: v16 first-primal input-path diagnostic

W3 has its own immutable criteria and private v16 input dataset. Criteria SHA
`3c54f3867d9eb9a5960b4c153bd1bffbfc4ca3a547456ecd51b340f808476de3` binds
source commit `b46ef4270df0c76d91922b8f1b2455fabad62418`. The dataset is
`ramhachi888/cfd-opt-sdf-v16-genesis-state`; the kernel is
`ramhachi888/cfd-opt-sdf-w3-v16-primal`.

Kaggle version 1 stopped during criteria loading because the registered JSON
was not present at the runner's expected path under `/kaggle/input`. It did not
inventory a GPU, fetch source, start Julia, or take a solver step. The failure
and hashes are preserved in
[`evidence/kaggle_w3_v16_primal_version1_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version1_diagnostic_2026_09.json).
The kernel metadata returned by `kaggle kernels pull` contains the expected
dataset source, and the dataset status was `ready`; the missing criteria path
does not establish whether the input mount was empty or differently named.
Version 2 re-pushes the unchanged kernel after the new private source was
ready. If a first run immediately after attaching a new Kaggle source fails
before solver initialization, keep the criteria unchanged and inspect the
exact version's logs and `ERROR.txt` before deciding whether a retry or a
path-resolution fix is required.

Version 2 was collected on 2026-09-28 and failed at the same criteria lookup
as version 1. Its append-only diagnostic records the exact logs/output hashes
and confirms no GPU inventory or solver step was reached:
[`evidence/kaggle_w3_v16_primal_version2_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version2_diagnostic_2026_09.json).
The dataset API reported `ready` and listed the criteria file, but the runtime
did not record its `/kaggle/input` mount inventory. The runner now discovers
the unique criteria file recursively and records top-level mount entries
before lookup. No threshold or registered criteria was edited.

Static source-review note (not execution evidence): the pinned W3 Julia job
also used several non-exported `CFDSDFWaterLily` definitions without explicit
imports. Version 2 failed before reaching Julia, so this was not its observed
failure. The W3 job now explicitly imports its profile constants and helpers;
that source change, together with input-path discovery, must be bound to a new
immutable criteria round before retrying.

Historical W3 version 2 collection commands (completed; do not run the
success-only host verifier against this ERROR output):

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w3 --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/2 -p work/kaggle_w3_version2
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w3_v16.py \
  work/kaggle_w3_version2 \
  --dataset-dir work/kaggle_w3_v16_dataset_registered_3c54f386 \
  --kernel-version 2
```

The round-1/round-2 host verifier rechecks registered source and dataset hashes,
reads the canonical SDF state independently, recomputes its margin and
force-window metrics, validates the available raw force-component closure, then
recomputes T0-T9. Those rounds do not gate stationarity. Round 3 below adds the
full three-axis closure and T10 stationarity gate. W3 remains an explicitly
non-equivalent WaterLily finite-box approximation; even a round-3 pass does not
qualify the OpenFOAM physical profile, grid/domain response, gradients,
topology, or a shape update.

### W3 immutable round 2 and retry workflow

After the source fix is committed and pushed, the working tree must be clean
before generating a new round. Round 2 is append-only and binds the new runner
and Julia job hashes without changing any acceptance limit:

```bash
.venv/bin/python scripts/register_kaggle_w3_v16_primal_2026_09.py \
  --round 2 --state work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz
.venv/bin/python scripts/register_kaggle_w3_v16_primal_2026_09.py --round 2 --check
git add docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round2.json \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round2.json.sha256
git commit -m "Register W3 v16 primal criteria round 2"
git push origin codex/kaggle-batch-migration
.venv/bin/python scripts/prepare_kaggle_w3_dataset_2026_09.py \
  work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round2.json \
  work/kaggle_w3_v16_dataset_round2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets version \
  -p work/kaggle_w3_v16_dataset_round2 \
  -m "W3 v16 immutable criteria round 2: input mount discovery" --dir-mode zip
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets status \
  ramhachi888/cfd-opt-sdf-v16-genesis-state
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w3 --accelerator NvidiaTeslaT4 --timeout 7200
```

Use the actual kernel version returned by the push in every status/log/output
command. If it is version 3:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3 -p work/kaggle_w3_version3
test ! -e docs/evidence/kaggle_w3_v16_primal_result_round2_2026_09.json
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w3_v16.py \
  work/kaggle_w3_version3 \
  --criteria docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round2.json \
  --dataset-dir work/kaggle_w3_v16_dataset_round2 \
  --kernel-version 3 \
  > docs/evidence/kaggle_w3_v16_primal_result_round2_2026_09.json
```

The verifier prints an append-only PASS candidate containing the exact
criteria/source/version bindings, T0-T9 recomputation and observed backend
identity, including `waterlily_backend`. Confirm it reports `verdict: PASS`
and `host_verification_passed: true`, then commit and push that result evidence
before registering W4.

If version 3 still fails criteria discovery, its downloaded
`input_mount_inventory.json` distinguishes the visible `/kaggle/input` entries
from a registered dataset that is absent from the runtime mount.

### W3 round-2 version 3 terminal diagnostic (2026-09-28)

Version 3 used the exact immutable round-2 criteria and source binding above.
Its Kaggle worker status is `KernelWorkerStatus.ERROR`, but the solver ran
10,600 steps through `tU/L=120.0103759766` and completed force integration.
Criteria discovery, dataset/source hashes, Julia setup, CUDA smoke, T4
inventory, SDF transfer/body/simulation construction, finite fields, runtime,
and VRAM gates passed. T7 alone failed: the registered `[80,120]` time-weighted
`+Fx` drag was negative (`-23.45292019493048` solver units,
`-0.05863230048732621 N`). The raw force CSV and independent host recomputation
agree; this is a measured registered acceptance failure, not an infrastructure
or primal-start failure. Do not flip the sign or alter round-2 criteria based
on this result.

The exact append-only diagnostic is
[`evidence/kaggle_w3_v16_primal_version3_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version3_diagnostic_2026_09.json)
(SHA-256 `fa278d11d7f2dfcde134671fea35580955d542447a51646864fc14ddad2fbe1f`).
It records all T0-T9 values (T0-T6, T8 and T9 true; T7 false), exact source,
criteria, backend and output hashes. The downloaded `sha256.json` and all 19
listed output files were independently rehashed and match. Independent host
helpers verified registered source and staged dataset identities, CPU-side
SDF margin (`0.3499999939931499 m` against the `0.15 m` gate), raw force
recomputation, summary metrics, and recorded x-force closure. The success-only
formal W3 verifier was not run because the output contains `ERROR.txt` and no
`DONE`; `formal_host_verification_passed=false`. The W3 CSV records separate
pressure/viscous x components but not separate y/z components, so y/z component
closure is not independently verifiable from this output.

The run recorded two Tesla T4 GPUs, selected UUID
`GPU-208ce4aa-07f3-1e25-2d6e-f1f2e2adbef9`, driver `580.159.04`, CUDA driver
API `13.3.0`, runtime `12.8.0`, Julia `1.12.6`, CUDA.jl `6.3.1`, WaterLily
`1.8.0` / `KernelAbstractions`, and `CUDA_VISIBLE_DEVICES=0`. It recorded 441
force samples in the measurement window, 94.272 seconds wall time, and peak
VRAM `7,132,408` bytes. The first/second-half force means are diagnostic only;
they do not establish stationarity. The registered-window diagnostic means
were approximately drag `-8.73/-37.27` and downforce `-196.19/-254.50` for
the first/second halves, respectively. This response shows why a positive
drag-only pass would not be enough for an FD baseline; the round-3 stationarity
limit comes from W2 registration, not these v3 values.

Exact-version collection commands (completed):

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/3 -p work/kaggle_w3_version3
```

Keep `waterlily_v16_primal_qualified=false`,
`physical_profile_qualified=false`, `grid_response_qualified=false`,
`sdf_gradient_qualified=false`, both reverse qualification flags false, and
`shape_update_allowed=false`. W4 remains implemented only: do not register
its criteria, stage/upload its dataset, or start measurement until an exact
W3 run has a passing formal host verification. Investigate the negative
registered drag against the force convention and physical fixture without
changing round 2; any justified source or measurement change requires a new
immutable criteria round before a new run.

### W3 expanded-domain immutable round 3 (prepared, not registered)

The v3 negative `+Fx` drag is a registered T7 failure, not proof of a sign
implementation bug. Keep `drag=+Fx` and `downforce=-Fz`. Do not rerun the same
small box by flipping signs. The next round uses the expanded WaterLily
finite-box fixture because independent Stage V evidence already reports the
original `[-1,2]x[-0.8,0.8]x[-0.6,0.6] m` OpenFOAM box as failed at
`outer_patch_backflow_and_pressure_disturbance`, while the expanded
`[-2.5,2.5]x[-1.2,1.2]x[-0.9,0.9] m` profile passed. A same-candidate
OpenFOAM parent/child domain check from x-max 2.5 to 3.5 m also passed its
registered domain gate. Its parent/child `Cd` (`1.16939914/1.17036295`) and
downforce (`0.75655147/0.75735487`) are fixture-selection evidence only; they
are not WaterLily targets and establish no OpenFOAM/WaterLily equivalence.
The W2 round-5 sphere's positive-drag result is a separate precedent for the
same `+Fx` convention.

Round 3 keeps the canonical design SDF fixed at origin `[-1,-0.8,-0.6] m`,
spacing `0.05 m`, and point shape `61x33x25`. It separates that origin from the
flow origin `[-2.5,-1.2,-0.9] m`; flow dims are `100x48x36`, dx `0.05 m`,
solver length 16, viscosity 0.20 and Re 80. The SDF-to-solver body map uses the
flow origin while the canonical `GridSDF` retains its original origin. The
moving-ground plane is solver z=0, which maps to world z=-0.9 m, the bottom of
the expanded flow domain. The candidate world geometry, canonical phi bytes,
moving-ground velocity, freestream and force signs remain fixed.

Round-3 raw force output has total, pressure and viscous `Fx/Fy/Fz`, drag and
downforce. T7 checks positive time-weighted +x drag, all three
`total=pressure+viscous` components, projections and independent host
recomputation. It imposes no downforce sign/magnitude gate. T10 is a hard
stationarity gate for drag and downforce, each using
`abs(mean_first-mean_second)/max(abs(mean_whole),eps(Float64)) <= 0.02`. Each
mean uses exact endpoint-clipped trapezoidal integration over `[80,100]`,
`[100,120]`, or `[80,120]`. The 2% limit is inherited from registered W2
sphere capability criteria and fixed before W3 round-3 measurement; it was not
chosen from v3 output.

Before freezing round 3, run the adapter test, syntax parse, focused contracts,
JSON parsing, Python compilation and diff check:

```bash
julia --startup-file=no --project=julia/CFDSDFWaterLily \
  julia/CFDSDFWaterLily/test/test_v16_physical_profile_adapter.jl
julia --startup-file=no --project=julia/CFDSDFWaterLilyT4 \
  -e 'Meta.parseall(read("scripts/waterlily_w3_v16_primal_job.jl", String)); println("W3 Julia syntax parsed")'
.venv/bin/python -m pytest -q tests/test_kaggle_w3.py tests/test_kaggle_w4.py
.venv/bin/python -m compileall -q src tests scripts infra/kaggle/kernel_w3 infra/kaggle/kernel_w4
python3 -m json.tool docs/evidence/w4_v16_sensitivity_criteria_draft_2026_09.json >/dev/null
git diff --check
```

Only after all source, tests and the mutable W4 draft are final, commit and
push the source to `codex/kaggle-batch-migration`. On that clean pushed source
commit, register W3 criteria round 3 and commit/push the criteria plus sidecar:

```bash
.venv/bin/python scripts/register_kaggle_w3_v16_primal_2026_09.py \
  --round 3 --state work/sdf_native_genesis_v16/sdf_design_state.npz
.venv/bin/python scripts/register_kaggle_w3_v16_primal_2026_09.py --round 3 --check
git add docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json.sha256
git commit -m "Register W3 expanded-domain criteria round 3"
git push origin codex/kaggle-batch-migration
.venv/bin/python scripts/prepare_kaggle_w3_dataset_2026_09.py \
  work/sdf_native_genesis_v16/sdf_design_state.npz \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  work/kaggle_w3_v16_dataset_round3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets version \
  -p work/kaggle_w3_v16_dataset_round3 \
  -m "W3 v16 expanded-domain immutable criteria round 3" --dir-mode zip
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets download \
  -d ramhachi888/cfd-opt-sdf-v16-genesis-state \
  -p work/kaggle_w3_v16_dataset_round3_remote --force --unzip
```

Before kernel submission, compare the re-downloaded remote dataset's manifest
and exact file inventory/SHA-256 values against the staged round-3 dataset.
Then submit the W3 kernel. Use the exact version returned by `push` for every
subsequent status, log, output and verifier command. Set `KAGGLE_W3_VERSION`
to that integer:

```bash
KAGGLE_W3_VERSION=4  # Replace with the exact version returned by push
KAGGLE_W3_RUN="work/kaggle_w3_version${KAGGLE_W3_VERSION}"
mkdir -p "$KAGGLE_W3_RUN"
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w3 --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  "ramhachi888/cfd-opt-sdf-w3-v16-primal/${KAGGLE_W3_VERSION}"
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  "ramhachi888/cfd-opt-sdf-w3-v16-primal/${KAGGLE_W3_VERSION}" \
  > "$KAGGLE_W3_RUN/kaggle.log"
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  "ramhachi888/cfd-opt-sdf-w3-v16-primal/${KAGGLE_W3_VERSION}" \
  -p "$KAGGLE_W3_RUN"
```

If the exact version reaches `COMPLETE` and contains `DONE`, run the success
verifier. It independently verifies T0-T10 and writes a unique append-only
result plus SHA sidecar only if every gate passes:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w3_v16.py \
  "$KAGGLE_W3_RUN" \
  --criteria docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version "$KAGGLE_W3_VERSION" \
  --kaggle-log "$KAGGLE_W3_RUN/kaggle.log" \
  --result-evidence docs/evidence/kaggle_w3_v16_primal_result_round3_2026_09.json
```

An `ERROR` or failed gate is diagnostic only: preserve the exact log/output,
record solver start/step count and failure stage, and do not relax criteria or
proceed to W4. W4 stays unregistered/unmeasured until exact round-3 host
verification passes.

### Diagnostic-only Enzyme reverse spike version 1 (2026-09-28)

Exact version 1 completed as a Kaggle worker but produced `ERROR.txt` before
the reverse Julia script. Its append-only diagnostic is
[`evidence/kaggle_enzyme_reverse_spike_version1_diagnostic_2026_09.json`](evidence/kaggle_enzyme_reverse_spike_version1_diagnostic_2026_09.json)
(SHA-256 `9d969272bd3730b6d7cd5609a93bd3748d3fe9698dcf5597c3ee8def755e0e67`).
The runner recorded two Tesla T4 GPUs and downloaded/hash-checked/extracted
Julia 1.12.6. `Pkg.instantiate()` then tried to write the project manifest
under `/kaggle/src/julia`, the read-only Kaggle source mount, and failed with
`EROFS`. This is a Julia setup/project-path failure; package-resolution
completion is unverified. No CUDA initialization, Enzyme probe, isolated
Poisson VJP, WaterLily Flow activity analysis, timestep reverse, or
host/device derivative ran. Do not label it a package-compatibility or
reverse-mode failure.

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1 \
  -p work/kaggle_enzyme_reverse_spike_version1
```

The exact reverse spike v2 result is an earlier source-packaging diagnostic.
Kaggle reports `KernelWorkerStatus.COMPLETE`, but its output has `ERROR.txt`
before GPU inventory: the script was at `/kaggle/src/script.py`, while the
adjacent `julia/Project.toml` was not present in the Kaggle source bundle. The
append-only record is
[`evidence/kaggle_enzyme_reverse_spike_version2_diagnostic_2026_09.json`](evidence/kaggle_enzyme_reverse_spike_version2_diagnostic_2026_09.json)
(SHA-256 `bb57d2db8a1bf4391e5c8dbdb7adb43d5a7a96807a385be4d3fccf24a5a5b656`).
Its exact CLI log SHA-256 is
`f6f13b40f46d4852b0aad1e21782806bd4a476a92d187ebebcd24bc28141e828`,
`ERROR.txt` SHA-256 is
`f8578e487c1d675eab4d510b6ddacb4375b8beb5efd3bf34502d5216f845fec8`, and
output-manifest SHA-256 is
`9b322e174657e1c8701bf7841011a224be1c6948cc35e29028aa4c22de6c6db9`. No
GPU inventory, Julia setup, Pkg instantiation, CUDA initialization, or reverse
probe ran. This is not an Enzyme/CUDA or package-resolution failure.

The next diagnostic revision on `exp/w3-enzyme-reverse-spike` fetches the
scratch Julia project from fixed source commit
`9b22f719e2f06222dd7f01788154399f0fef441d`, verifies the exact Project,
Manifest and reverse script SHA-256 values, then copies it to writable
`/kaggle/working`. The expected pins are Project
`867d0e3f1846d65322b65c44261d649c43775984d36cbc6bfb43a02285653383` and
Manifest `f30dacad47411641cbf297c4663e12029de2565ab6d875aa05891127289a8b6e`.
It logs source archive, source input, pre/post-instantiation copy hashes and
the exact failure stage. CUDA.jl 6.2.1, Enzyme and WaterLily PR #285 remain
isolated from W2/W3/W4.

Submit and collect the next reverse diagnostic with Kaggle CLI 2.2.4:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_enzyme_reverse_spike --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3 \
  > work/kaggle_enzyme_reverse_spike_version3/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3 \
  -p work/kaggle_enzyme_reverse_spike_version3
```

Check that `project_identity.json` reports the pinned commit and input
Project/Manifest hashes, identical pre-instantiation writable-copy hashes,
post-instantiation hashes and failure stage. Classify failures separately as
source fetch, dependency resolution, CUDA initialization, basic Enzyme CUDA
reverse, isolated Poisson VJP, Flow activity analysis/mutation, timestep
reverse, or host/device-transfer derivative. This run remains diagnostic-only
regardless of its per-stage status.

## W4 v16 resolution/domain sensitivity preparation (not registered)

W3 version 3 completed the registered primal horizon but failed its T7
positive-drag acceptance gate; expanded-domain W3 round 3 must first pass its
exact-version host verifier. The local W4 execution shell and gated
final-registration/staging tools are now implemented, but its draft remains
`immutable: false` / `registered_before_computation: false`; there is no final
criteria file or staged W4 dataset and no W4 run is authorized.

- `julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl` defines the four fixed case
  maps and checks physical-box alignment, dimensions, solver length, and Re=80.
  The mutable draft separates canonical SDF origin `[-1,-0.8,-0.6] m` from
  flow origin `[-2.5,-1.2,-0.9] m`. On the unchanged expanded baseline box,
  `flow_16/24/32` are `100x48x36` at `dx=.05 m`, `150x72x54` at
  `dx=.033333... m`, and `200x96x72` at `dx=.025 m`, with solver viscosities
  `.20/.30/.40`. The domain case is
  `[-2.5,3.5]x[-1.2,1.2]x[-.9,.9] m`, `120x48x36`, extending +x by 1 m to
  match the existing OpenFOAM parent/child pair. All retain Re=80; the
  canonical 0.05 m design lattice is not resampled.
- `scripts/waterlily_w4_v16_sensitivity_job.jl` runs the four T4 cases against
  the unchanged canonical v16 SDF and writes raw 3-axis pressure, viscous, and
  total force vectors. It also writes physical-time-weighted solver means,
  physical N forces, half-window diagnostics, runtime, VRAM, SDF hashes, and
  backend identity. Sampling is every eight solver steps plus a terminal force
  sample; host and Julia recomputation linearly interpolate to the exact
  registered [80,120] endpoints before trapezoidal integration.
- `infra/kaggle/kernel_w4/runner.py` discovers the criteria by filename under
  `/kaggle/input` (not a hard-coded Kaggle mount path), checks criteria,
  dataset, source commit, input hashes, W3 PASS evidence, canonical state,
  measured SDF margin, T4 inventory and CUDA smoke, then records stage and
  solver-step progress with a complete output SHA manifest. It refuses draft
  criteria.
- `scripts/verify_kaggle_w4_v16.py` independently checks the version-bound
  output, inputs, SDF hashes/margin, all raw force rows, component closure,
  projections, endpoint-clipped time-weighted means, physical N conversion,
  runtime/VRAM, backend identity and the W3 prerequisite. It recomputes both
  the runner's gates and the domain-versus-resolution follow-up rule.
- `tests/test_kaggle_w4.py` covers runner/host gate agreement, 3-axis force
  closure, exact [80,120] endpoint interpolation, grid identity rejection,
  the extended-domain rule, the SDF margin definition, staged-file inventory,
  and refusal to register W4 from W3 error evidence.
- `scripts/register_kaggle_w4_v16_sensitivity_2026_09.py` refuses final
  criteria without an exact host-verified W3 PASS and complete observed T4
  backend identity. It binds the W3 criteria/result and W4 source hashes.
- `scripts/prepare_kaggle_w4_v16_dataset_2026_09.py` accepts only immutable
  W4 criteria, rechecks pinned source and canonical state/phi identities, and
  stages the exact private dataset inventory.
- `infra/kaggle/kernel_w4/kernel-metadata.json` is private T4 metadata pointed
  at the future W4 dataset. Do not push it while W3 is still pending.

After W3 formally passes, bind both its immutable criteria file and its
append-only result evidence. The round-3 host verifier emits
`verdict: PASS`,
`host_verification_passed: true`, the exact W3 criteria SHA, kernel version,
source commit, and the observed `backend_identity` (including the
`waterlily_backend` string). Copy that backend identity into the W4 criteria;
the W4 runner and host verifier require exact equality while recording the
selected T4 UUID separately for each run. Then bind the exact W4
runner/job/case module/profile/SDF adapter, Project/Manifest,
verifier/test/metadata hashes, criteria, raw phi and canonical state. Register
the final immutable criteria, stage the private dataset, validate the hashes,
and only then push the W4 kernel. For the W3 round-3 result path:

```bash
.venv/bin/python scripts/register_kaggle_w4_v16_sensitivity_2026_09.py \
  --w3-criteria docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  --w3-result docs/evidence/kaggle_w3_v16_primal_result_round3_2026_09.json
.venv/bin/python scripts/register_kaggle_w4_v16_sensitivity_2026_09.py \
  --w3-criteria docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  --w3-result docs/evidence/kaggle_w3_v16_primal_result_round3_2026_09.json --check
git add docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json \
  docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json.sha256
git commit -m "Register W4 v16 sensitivity criteria"
git push origin codex/kaggle-batch-migration
.venv/bin/python scripts/prepare_kaggle_w4_v16_dataset_2026_09.py \
  --state work/kaggle_w3_v16_dataset_round3/sdf_design_state.npz \
  --criteria docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json \
  --output work/kaggle_w4_v16_dataset
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets create \
  -p work/kaggle_w4_v16_dataset --dir-mode zip
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets status \
  ramhachi888/cfd-opt-sdf-v16-w4-sensitivity
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle datasets files \
  ramhachi888/cfd-opt-sdf-v16-w4-sensitivity
```

Run this only after the W3 evidence is an exact host-verified PASS. The new
W4 dataset remains private by default. Once Kaggle reports it ready and its
file listing matches the staging manifest, submit and retrieve W4:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w4 --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w4-v16-sensitivity/<VERSION>
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w4-v16-sensitivity/<VERSION>
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w4-v16-sensitivity/<VERSION> \
  -p work/kaggle_w4_version<VERSION>
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w4_v16.py \
  work/kaggle_w4_version<VERSION> --criteria docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json \
  --dataset-dir work/kaggle_w4_v16_dataset --kernel-version <VERSION>
```

The `<VERSION>` value must be the exact version printed by `push` and kept the
same for status, logs, output and verification. If either physical-force domain
delta is greater than or equal to its corresponding 24-to-32 resolution delta,
register and run the extended-domain fine-grid case before centered FD. W4
reports sensitivity; it does not qualify convergence or the physical profile.

Preparation checks (no solver/GPU measurement):

```bash
julia --startup-file=no -e 'include("julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl"); using .V16W4Sensitivity; foreach(println, V16W4_CASES)'
julia --startup-file=no --project=julia/CFDSDFWaterLilyT4 -e 'Meta.parseall(read("scripts/waterlily_w4_v16_sensitivity_job.jl", String)); println("W4 Julia syntax parsed")'
python3 -m json.tool docs/evidence/w4_v16_sensitivity_criteria_draft_2026_09.json >/dev/null
python3 -m pytest -q tests/test_kaggle_w4.py
git diff --check
```

The four-case builder, Julia parser, JSON parser and focused W4 contract tests
pass. These checks do not run a solver and do not qualify W4.

### Exact execution checkpoint: W3 round 3, kernel version 4 (2026-09-28)

The round-3 criteria and private dataset are now registered and remotely
verified. Criteria SHA-256 is
`f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`; the
registered source commit is `5e985fa3395a01228c18910d96e09ecbc5497628`. The
remote dataset reports `ready`; its downloaded five-file inventory matches
the staged files and hashes (including manifest SHA-256
`17f0db110af5e989905e43b83ac7a003efe9b0587f127d5633b8910e7a0e8e9b`).

The exact push returned version 4:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w3 --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4 > work/kaggle_w3_version4/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4 -p work/kaggle_w3_version4
```

At the latest check, exact version 4 is `KernelWorkerStatus.RUNNING`. The
retrieved `kaggle.log` is 1 byte (newline only; SHA-256
`01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`) and no
output artifact is exposed yet. Thus solver start, steps, and measurements
remain unobserved. Repeat the exact-version status/log/output commands until
terminal; use this same `work/kaggle_w3_version4` directory for collection.

Preflight command results before submission: W3 round-3 registrar `--check`
reproduced the criteria SHA; `tests/test_kaggle_w3.py` and
`tests/test_kaggle_w4.py` passed (19 tests); Python `compileall` passed; and
the W3 Julia adapter passed 16 checks without a solver step. On this host, the
managed worktree has no `.venv`; those Python checks used
`/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python` from the separate
project checkout, with the working directory set to the managed worktree.
The separate checkout's edits were left untouched.

Do not register W4 or start W4/FD measurements unless exact version 4 passes
the round-3 host verifier. Enzyme reverse spike version 3 is a separate
diagnostic-only run and was `RUNNING` at this checkpoint; it is never gradient
qualification evidence.

### W3 round 3, exact kernel version 4: terminal diagnostic (2026-09-28)

This section supersedes the preceding active-run status. Exact W3 version 4 is
terminal `KernelWorkerStatus.ERROR`. The immutable round-3 criteria and dataset
were not changed; no force sign or threshold was adjusted after observing the
run.

The expanded fixture choice is backed by independent Stage V records, not by
WaterLily/OpenFOAM equivalence: the original small OpenFOAM box failed its
outer-patch pressure-disturbance gate (inlet normalized mean absolute
disturbance `0.153719 > 0.05`); the registered expanded box passed, and the
same-candidate +x outlet-extension pair passed with parent/child Cd
`1.16939914/1.17036295` and downforce `0.75655147/0.75735487`. The measured
domain-pair values justify the WaterLily fixture selection only and are not
WaterLily acceptance targets. W2b's positive sampled-sphere `T4_drag_sign`
gate remains the independent precedent for keeping `drag=+Fx`.

Collect the exact version with the same version number in every command:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4 > work/kaggle_w3_version4/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-primal/4 -p work/kaggle_w3_version4
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16.py work/kaggle_w3_version4 \
  --criteria docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 --kernel-version 4 \
  --kaggle-log work/kaggle_w3_version4/kaggle.log
```

The success-only host verifier refused formal verification with
`Kaggle W3 completion marker missing`; the output contains `ERROR.txt` and no
`DONE`. Preserve that as `formal_host_verification_passed=false`. The separate
host diagnostic recomputation independently checked the registered source and
dataset hashes, canonical SDF identity/margin, backend, raw CSV schema and
sampling, 3-axis pressure-plus-viscous closure, exact-window force metrics and
T0-T10; its gate map matched the runner. This diagnostic recomputation is not
a PASS result and must not be used to generate W4 criteria.

Recorded exact-run facts:

- Criteria SHA-256: `f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`;
  dataset manifest SHA-256:
  `17f0db110af5e989905e43b83ac7a003efe9b0587f127d5633b8910e7a0e8e9b`.
- Kaggle status output SHA-256:
  `368662655f7cc049a9f53b4e73c2db1e674c8d6dc20fd026940603cbe300f115`;
  exact logs SHA-256:
  `c1217626c24d099c850c79378c42771ed235ad392393d3b8098e51cee3544ab3`;
  output-bundled log SHA-256:
  `ce76ce09ac07ed4c0285144081752401ce5eb2ab6ad74349a53c50b98de3af68`.
- All 19 output artifacts match the bundled SHA-256 manifest. The T4 run
  reached 3,841 solver steps and `tU/L=120.015625`, recording 481 force rows
  (160 in `[80,120]`). Every total, pressure, and viscous component on all
  three axes is signed zero. The raw force CSV SHA-256 is
  `cf20d9ccf0c685500819801be9a6925346d15a2c881031a09cba599135ea8d9c`.
- Runner and host diagnostic gates agree: T0-T6 true, T7 false, T8-T10 true.
  The numeric T10 drift is zero only because the signal itself is zero, so it
  is a degenerate stationarity observation. T7's registered positive `+Fx`
  condition remains unchanged. This does not establish a force-sign bug.
- Backend: two Tesla T4 GPUs; selected UUID
  `GPU-3adff65b-4908-2981-c7a1-cfd5b5a5bd3c`; Julia 1.12.6, CUDA.jl 6.3.1,
  CUDA runtime 12.8.0, WaterLily 1.8.0 / `KernelAbstractions`. Runtime was
  31.033535 s and peak VRAM 24,741,180 bytes.
- A follow-up host-only mapping probe found 1,121 negative-distance solver
  lattice points for the expanded fixture and placed the unchanged interface
  inside the `100x48x36` box. A 100-step CPU smoke using Julia 1.12.6 and
  WaterLily 1.8.0 returned nonzero raw WaterLily force by step 20. These
  probes do not reproduce the T4 path and leave the all-zero T4 history's
  cause open. Exact probe scripts/logs are under the ignored `work/` paths
  bound by the follow-up diagnostic evidence; rerun with:

  ```bash
  julia --project=julia/CFDSDFWaterLily work/w3_v4_grid_occupancy.jl
  julia --project=julia/CFDSDFWaterLily work/w3_v4_cpu_smoke.jl
  ```

Append-only records:
[`W3 version-4 diagnostic`](evidence/kaggle_w3_v16_primal_version4_diagnostic_2026_09.json)
and
[`host CPU follow-up diagnostic`](evidence/kaggle_w3_v16_primal_version4_followup_diagnostic_2026_09.json).
Do not create a W3 PASS record from this output. Keep W4 criteria and dataset
unregistered, W4 measurements and formal FD unrun, and all physical-profile,
gradient, reverse, topology and shape-update claims false.

Local validation for this checkpoint:

```bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  -m pytest -q tests/test_kaggle_w3.py tests/test_kaggle_w4.py
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  -m compileall src tests
julia --startup-file=no --project=julia/CFDSDFWaterLily \
  -e 'Meta.parseall(read("scripts/waterlily_w3_v16_primal_job.jl", String)); Meta.parseall(read("scripts/waterlily_w4_v16_sensitivity_job.jl", String)); println("W3/W4 Julia syntax parsed")'
julia --startup-file=no --project=julia/CFDSDFWaterLily \
  julia/CFDSDFWaterLily/test/test_v16_physical_profile_adapter.jl
git diff --check
```

The focused W3/W4 tests passed (19); `compileall`, W3/W4 Julia parsing, and
all 16 no-solver adapter checks passed. The full suite returned 1,068 passed,
37 failed, and 4 skipped. Its reported failures were `FileNotFoundError` on
historical host-local fixtures under ignored `work/` directories that are not
present in this managed worktree; no W3/W4 test failed. This worktree has no
`.venv`, so Python checks used the compatible environment in the separate
project checkout; that checkout's source changes were left untouched.

### Enzyme reverse spike, exact kernel version 3: terminal diagnostic

Retrieve the scratch run by exact version:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3 \
  > work/kaggle_enzyme_reverse_spike_version3/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/3 \
  -p work/kaggle_enzyme_reverse_spike_version3
```

The worker status is `KernelWorkerStatus.COMPLETE`, but its output includes
`ERROR.txt`. The Project/Manifest writable copy passed pre/post SHA checks,
package instantiation completed, CUDA initialized, and the two-T4 inventory
was recorded. A basic Enzyme CuArray reverse then failed with
`EnzymeRuntimeActivityError` at `GPUArrays._mapreduce`. The subsequent
WaterLily `Flow` compilation failed on unsupported
`llvm.nvvm.shfl.sync.down.f32` before any primal. Poisson VJP and timestep
reverse were not reached. This is diagnostic-only, not reverse qualification;
the scratch CUDA.jl 6.2.1 / Enzyme / WaterLily PR #285 environment must remain
isolated from production W2/W3/W4 dependencies. Exact artifact identities and
the failure boundary are in
[`reverse spike version-3 diagnostic`](evidence/kaggle_enzyme_reverse_spike_version3_diagnostic_2026_09.json).

### W3 v4 all-zero force: CPU/T4 implementation diagnostic

W3 round-3 version 4 reached the registered end time with finite fields but
recorded an exactly zero three-axis force history. That run remains
unqualified. Preserve its criteria SHA
`f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`, force
projection, and thresholds. The following job is a separate private diagnostic
kernel; it reuses the exact round-3 W3 input dataset but has no W3 acceptance
gates and never creates qualification evidence.

The CPU-only reference is reproducible without CUDA:

```bash
julia --startup-file=no --project=julia/CFDSDFWaterLily \
  scripts/waterlily_w3_v16_cpu_diagnostic_reference.jl \
  work/kaggle_w3_v16_dataset_round3/canonical_v16_phi_f4_fortran.raw \
  work/w3_v4_cuda_diagnostic_cpu_reference
```

It scans all `100x48x36` WaterLily pressure-cell centers for the candidate and
candidate-plus-ground SDF, records the combined-body CPU `measure!` fields, and
advances one CPU step. In the 2026-09-28 run, canonical phi SHA-256 was
`9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`, measured
margin was `0.3499999939931499 m`, candidate negative/support counts were
`1009/2481`, and combined negative/support counts were `1009/7281` (support
means `|d|<=1` solver unit). Initial force was zero; after one CPU step at
`t=0.015625`, raw WaterLily pressure and viscous force vectors were respectively
`[-3375.1481610226565,-22.193702077892354,4640.059766063432]` and
`[-109.8979301765703,-0.2722819617444081,-12.88964694003107]`. This is a
one-step CPU diagnostic, not a sign, stationarity, or physical-profile result.
The output log and text result are ignored files under `work/`; their recorded
SHA-256 values at this checkout are `a1036a1e31aef5737ed75584a970f9436cdba88c11d4597c4efd357057c37fb1` and
`4b8694cf537d37d2decd653f9debfd23f759b4fd94397616222c04d594cdf42e`.

This host has no `nvidia-smi`, and its T4 Julia environment does not have the
CUDA package instantiated. Do not interpret the CPU reference as a CUDA check.
Use the private Kaggle T4 diagnostic kernel, which performs: representative
world-to-solver probes; a complete CPU/CUDA flow-grid scan of candidate,
ground, and combined distance/normal/velocity; solver-free combined-body
`measure!`; one v16 CPU and CUDA step; and one-step W2b sphere controls. The
device owner remains strongly referenced while the non-owning `CuDeviceArray`
view is used. Stage checkpoints are written before/after each operation so an
ERROR output identifies the last completed stage.

The diagnostic runner is pinned to source commit
`ca67673ccff69a0b79243c461f82158ad8e61522`; the Julia job SHA-256 is
`4c080a72f48754c758ee999a38b7d7b83737dd01d2fe7573f4b164d7f0e1ce4e`. Before
submitting, commit and push the matching diagnostic runner, host verifier,
metadata and tests, then use the kernel's version returned by `push` in every
collection command:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_w3_cuda_diagnostic \
  --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/VERSION \
  > work/kaggle_w3_v16_cuda_diagnostic_versionVERSION/kaggle_status.txt
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/VERSION \
  > work/kaggle_w3_v16_cuda_diagnostic_versionVERSION/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/VERSION \
  -p work/kaggle_w3_v16_cuda_diagnostic_versionVERSION
PYTHONPATH=src:scripts python3 scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_diagnostic_versionVERSION \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version VERSION --kernel-status COMPLETE_OR_ERROR \
  --kaggle-status-file work/kaggle_w3_v16_cuda_diagnostic_versionVERSION/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_diagnostic_versionVERSION/kaggle.log
```

Replace both `VERSION` placeholders with the exact positive version number and
`COMPLETE_OR_ERROR` with its terminal status. The verifier checks the
version-bound status/log captures and output manifest; criteria/dataset/source
hashes; the full 172,800-row CSV and WaterLily cell-center coordinate order;
CPU and CUDA statistics for all three bodies; force component closure and
projection; and an independent NumPy trilinear SDF value/gradient reference.
It records CPU/CUDA disagreement as diagnostic output rather than changing a
W3 threshold. A Kaggle ERROR can still produce a host-verified diagnostic if
the exact partial output bundle and checkpoints are retrievable. The resulting
evidence must keep every primal, physical, grid-response, gradient, reverse,
topology, optimizer, and shape-update flag false. Do not start W4, formal FD,
or another W3 qualification attempt from this diagnostic alone.

The separate diagnostic kernel version 1 reached the registered input and
device identity checkpoint on a Tesla T4, then errored while constructing the
representative probe list, before solver-free body measurement or any solver
step. The Julia log identified `UndefVarError: f not defined` at
`v16_representative_probes`: one probe had the malformed Julia literal `0.0f`.
The smallest correction is `0.0f0`; no W3 source, criteria, threshold, or force
projection changed. The original host diagnostic and an append-only correction
record are
[`version 1`](evidence/kaggle_w3_v16_cuda_diagnostic_version1_2026_09.json)
and
[`version 1 classification correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version1_correction_2026_09.json).
Version 1's artifacts passed host hash/input verification; its failed stage is
the probe fixture itself, not SDF transfer or WaterLily CUDA measurement.

Diagnostic kernel version 2 also terminated with `KernelWorkerStatus.ERROR`.
Its T4 smoke completed with Julia 1.12.6, CUDA.jl 6.3.1, CUDA runtime 12.8.0,
WaterLily 1.8.0, and two Tesla T4 devices. The input/device checkpoint matched
the registered phi hashes and measured `0.3499999939931499 m` margin. It
constructed all 10 representative probes and entered the candidate probe
stage. The CUDA and CPU candidate `WaterLily.measure` calls returned, then
`compare_rows` failed on the malformed Julia token `1e-5f0` (`f0` was treated
as an undefined name). Version 2 persisted neither probe-row matrices nor a
completed comparison, so those numeric values are unavailable. Ground and
combined representative probes, the full flow-grid scan, simulation
construction, and solver steps were not reached. Its append-only host record
and source-identity correction are
[`version 2`](evidence/kaggle_w3_v16_cuda_diagnostic_version2_2026_09.json)
and
[`version 2 identity correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version2_identity_correction_2026_09.json).
The corrected source uses Julia Float32 scientific literal `1f-5`, checkpoints
the CPU/CUDA candidate probe matrices before comparison, and writes a pinned
criteria/dataset/backend/source fingerprint before attempting the measurement.

### W3 all-zero-force CUDA implementation diagnostic, exact kernel version 3

Version 3 of the private diagnostic kernel completed on Kaggle T4 and was
retrieved and host-verified by exact kernel version. It is diagnostic-only; it
does not reuse a W3 acceptance decision or qualify any physics/gradient claim.
The immutable W3 round-3 criteria remain SHA-256
`f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`.

Exact local capture paths:

- `work/kaggle_w3_v16_cuda_diagnostic_version3/kaggle_status.txt`
- `work/kaggle_w3_v16_cuda_diagnostic_version3/kaggle.log`
- `work/kaggle_w3_v16_cuda_diagnostic_version3/w3_v16_cuda_diagnostic/`

Captured status is `KernelWorkerStatus.COMPLETE`, SHA-256
`e728d1ce05074fee394cf33e6f060f6a09a02868dbd21c289b90701744c0f763`; exact
Kaggle log SHA-256 is
`4113bfa739c118ec231681e27a2fed95388e2b0f25aef1f720f37c35ede2d216`. The
output manifest SHA-256 is
`f37511b67b0a08dbf9bbcb05723df4efed39f396fe4b296044079862619c9721`, and the
raw 172,800-row lattice CSV SHA-256 is
`7ce428a9b0ede9b76abadb8578930acd9e34e1fc3e499c2e5e553aec8eeed02f`.

Re-run the exact host verification from the repository root:

~~~bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_diagnostic_version3 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 3 \
  --kernel-status KernelWorkerStatus.COMPLETE \
  --kaggle-status-file work/kaggle_w3_v16_cuda_diagnostic_version3/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_diagnostic_version3/kaggle.log
~~~

The resulting append-only records are
[`v3 host diagnostic`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_2026_09.json)
and
[`v3 interpretation and source audit`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_interpretation_2026_09.json).
The host diagnostic evidence SHA-256 is
`e0c9f1ee5bff1f07fb6daf268924b55e6b78fb61863d5620afc93dc11191f3cb`; its
recorded verifier SHA-256 is
`e600e8faaa6c7131e68444cfe61b605c9124b3791420c0a2901494ecc240835e`.

The observed runtime was a Tesla T4 (`GPU-d5fd398c-ae72-ef9e-54ae-c229cf2ea025`),
Julia 1.12.6, CUDA.jl 6.3.1, CUDA runtime 12.8.0, CUDA driver API 13.3.0,
NVIDIA driver 580.159.04, and WaterLily 1.8.0 / `KernelAbstractions`. The
unchanged canonical SDF is `61x33x25`, origin `[-1,-0.8,-0.6] m`; the flow
lattice is `100x48x36`, origin `[-2.5,-1.2,-0.9] m`. CPU/CUDA candidate
negative-distance counts are 1009 each, support counts at `|d|<=1` solver unit
are 2481 and 2476, and there are no distance-sign mismatches outside the zero
band. Candidate distance maximum absolute CPU/CUDA difference is
`4.76837158203125e-7 m`. The ground field matches its analytic distance,
normal, and velocity values.

The candidate's initial force snapshot is zero before any step, as expected
from the initial state. After one step at `t=0.015625`, repository-projected
CPU/CUDA drag is `3485.046517/3485.132996` solver units and downforce is
`4627.170260/4627.474695` solver units. Raw force components satisfy
`total = pressure + viscous` on all axes to floating-point roundoff. This
one-step response is not a time-window statistic or W3 qualification. The
independent CUDA normal comparison has a maximum vector error of about 1.338;
distance agreement does not imply normal or gradient qualification.

Source audit: the pinned full W3 job at
`5e985fa3395a01228c18910d96e09ecbc5497628` creates `device_owner`, derives the
kernel-safe view with `kernel_grid(device_owner)`, builds the body/simulation,
then calls `run_primal` without an explicit `GC.@preserve` for the owner. The
`DeviceGridSDF` contract documents that this view is non-owning and its
`DeviceGridSDF`/CuArray owner must outlive every kernel use. Diagnostic v3
keeps the owner rooted through the CUDA checks and gets nonzero force after a
step. This makes owner lifetime the leading source-level hypothesis for the
old all-zero full run, but does not prove that the owner was collected or that
it caused the zero history. The diagnostic did not force GC in a controlled
retained-versus-unrooted comparison and did not execute a long horizon.

The full W3 version-4 outcome is unchanged: 3,841 steps, `tU/L=120.015625`,
and all total/pressure/viscous force components signed zero; T7 failed and W3
remains unqualified. Do not flip the force sign, relax thresholds, start W4,
or run formal FD from this diagnostic. The next minimum investigation is a
diagnostic-only T4 owner-lifetime A/B on the same frozen fixture: retain the
owner with `GC.@preserve` in one arm, build the view-backed objects in a helper
scope and force full GC in the other, then record weak-owner collection, fixed
geometry checks, fields, and force after only a tiny number of steps. Only a
repeatable difference coincident with actual owner collection would confirm
the lifetime hypothesis. Preserve all qualification flags as false.

Local checks for the v3 evidence/verifier update:

~~~bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  -m pytest -q tests/test_kaggle_w3_cuda_diagnostic.py tests/test_kaggle_w3.py tests/test_kaggle_w4.py
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m py_compile \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  infra/kaggle/kernel_w3_cuda_diagnostic/runner.py
julia --startup-file=no --project=julia/CFDSDFWaterLily \
  -e 'Meta.parseall(read("scripts/waterlily_w3_v16_cuda_diagnostic_job.jl", String)); println("diagnostic Julia syntax parsed")'
git diff --check
~~~

The focused slice passed 30 tests. Python compileall/py_compile, Julia syntax
parsing, JSON plus evidence-sidecar verification, and `git diff --check` passed.
The full suite command was `PYTHONPATH=src:scripts
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` and
reported 1,079 passed, 37 failed, 4 skipped. Failures inspected in that run
were `FileNotFoundError` for historical inputs under ignored `work/` folders
not present in this managed worktree; for example, the Stage-S FD test lacks
`work/stage_s_work_f_v1/adjoint/base/optimisation/controlPoints/boxcpsBsplines0.csv`.
The changed W3/W4/diagnostic slice had no failures.

### Force projection interpretation for diagnostic snapshots

The diagnostic snapshot saves the direct WaterLily API vectors under
`waterlily_pressure_force_raw`, `waterlily_viscous_force_raw`, and
`waterlily_total_force_raw`. The registered W3 job first negates the two raw
vectors to form force-on-body components, then computes
`drag=+Fx_body_total` and `downforce=-Fz_body_total`. Thus, when starting from
the diagnostic's unmodified WaterLily raw vector, the equivalent projections
are `drag=-Fx_raw` and `downforce=+Fz_raw`. The diagnostic host verifier checks
this mapping explicitly. W2b's `pressure_force_on_body` and
`viscous_force_on_body` helpers use the same negation.

The v3 candidate's one-step positive projected drag is therefore consistent
with the registered W3 body-force convention. It remains a one-step snapshot,
not the registered `[80,120]` time-weighted force measurement or a qualification
result. The clarification record is
[`v3 force-projection correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_force_projection_correction_2026_09.json)
(SHA-256 `8511973f3f6cc4d2b3166e15752072e83891cbc2535f35915116a39ffa8ed58c`).
This corrects an overly cautious intermediate interpretation; the W3 force
sign and all acceptance criteria remain untouched.

### Diagnostic-only CUDA owner-lifetime A/B/C, criteria round 2

The purpose of this private T4 run is to test whether the non-owning CUDA SDF
view changes behavior after its `DeviceGridSDF`/CuArray owner becomes
unreachable. It is an implementation diagnostic only. It does not execute a
full horizon and cannot qualify W3, target physics, gradients, reverse mode,
or a production fix.

Round-2 immutable criteria:

- path: `docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round2.json`
- SHA-256: `8530e084ed33807b67b175f2234266cae34f74ccf510ea31130a199f30a0bec9`
- sidecar SHA-256: `ef9df9f54f4408783a243f3b92f014722a3131da7bccc86f5b34b24100538b43`
- source commit: `885ae7558012da43e6310e2ffb04db4230150f5b`
- owner job SHA-256: `7fa98a26105f1a2938ab85550931a22cb1020bd27d687d6f4dedb99c1b5572ea`

Round 1 was superseded before measurement because its representative
positive-phi probe did not use the v3-compatible minimum-positive selection.
Round 2 changes only that probe selection; fixture, arms, forced-GC procedure,
tolerances, and causal rules stay fixed. A and C run first. B1 and B2 each run
in a separate Julia process so an invalid-memory exit cannot remove the A/C or
first-B evidence.

The reviewed source was pushed, then private kernel version 4 was submitted.
Its first exact-version status check returned `KernelWorkerStatus.RUNNING`.
Wait for a terminal state before downloading logs and output. Keep using `/4`
for status, logs, and output:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/4 \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle_status.txt
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/4 \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/4 \
  -p work/kaggle_w3_v16_cuda_owner_lifetime_version4

PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_owner_lifetime_version4 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 4 \
  --kernel-status KernelWorkerStatus.COMPLETE \
  --kaggle-status-file work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle.log
```

For a terminal `ERROR`, use `KernelWorkerStatus.ERROR` and still retrieve all
three exact-version artifacts before classifying the failure.

Verify that `ERROR.txt`, partial
arm checkpoints, per-arm process logs and `sha256.json` were preserved. The
host verifier recomputes arm identity, input and backend bindings, geometry
and field bundle hashes/order, raw pressure/viscous/total closure, body-force
projections, A/C agreement, both B weak-owner GC brackets, and repeated
post-GC divergence classes. WeakRef clearing, a CUDA error, or nonzero force
alone does not support the hypothesis. Append the result to a new evidence
path; never replace round-1 criteria, round-2 criteria, or earlier Kaggle
version evidence.

### Exact version 4 terminal error and host-verification correction

Exact version 4 returned `KernelWorkerStatus.ERROR`. Retrieve results as
above; captured local files are under
`work/kaggle_w3_v16_cuda_owner_lifetime_version4/`. Kaggle's
`kernels pull .../4` request returned HTTP 403, so the version-specific runner
was reconstructed from the commit that had been pushed immediately before
submission:

```bash
git show 6fe9752:infra/kaggle/kernel_w3_cuda_diagnostic/runner.py \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version4/kernel_source/runner.py
shasum -a 256 work/kaggle_w3_v16_cuda_owner_lifetime_version4/kernel_source/runner.py
```

The runner hash is
`609a86f40424a83ab4ed870d1fe2c321c9c0994ff5e27077e821c01457f36378`, matching
the immutable `fingerprint.json` downloaded from version 4. Pass this exact
runner file to the host verifier when re-verifying the historical version;
the current runner will change for the corrected retry:

```bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_owner_lifetime_version4 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 4 \
  --kernel-status KernelWorkerStatus.ERROR \
  --kaggle-status-file work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_owner_lifetime_version4/kaggle.log \
  --kernel-runner work/kaggle_w3_v16_cuda_owner_lifetime_version4/kernel_source/runner.py \
  --evidence docs/evidence/kaggle_w3_v16_cuda_diagnostic_version4_runner_correction_2026_09.json
```

The exact terminal evidence is
`docs/evidence/kaggle_w3_v16_cuda_diagnostic_version4_2026_09.json` and its
append-only classification/verification correction is
`docs/evidence/kaggle_w3_v16_cuda_diagnostic_version4_runner_correction_2026_09.json`.
Exact status/log/output-manifest/`ERROR.txt` hashes are recorded in the
correction evidence. Input, source, runtime, device round-trip, full base flow
lattice, and base one-step artifacts verify. The error happened in the wrapper
when it tried to spawn owner arm A after the Julia binary's temporary directory
had already been removed. Thus base v16 CUDA diagnostic reached one step, but
the owner experiment reached zero arms; this is neither an owner-lifetime
observation nor evidence against the hypothesis.

The retry runner now validates the base output and runs A/C/B1/B2 before
leaving the Julia `TemporaryDirectory`. The error-classification test also
checks the exact missing-executable failure. The owner criteria round 2,
fixture, tolerances, and arm procedure stay unchanged because version 4 did
not launch an owner arm or produce an owner measurement. Use the exact new
kernel version and current runner hash for the retry, preserving version 4 and
both version-4 evidence files unchanged.

### Corrected retry: exact kernel version 5

The workspace-lifetime fix and host-verifier update were pushed in commit
`a5022c8`; private T4 kernel version 5 was then submitted. The initial status
was `KernelWorkerStatus.RUNNING`. Use `/5` for every status, log, and output
request, then invoke the verifier with the current runner (default) after
terminal state:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5 \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version5/kaggle_status.txt
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5 \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version5/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5 \
  -p work/kaggle_w3_v16_cuda_owner_lifetime_version5

PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_owner_lifetime_version5 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 5 \
  --kernel-status KernelWorkerStatus.COMPLETE \
  --kaggle-status-file work/kaggle_w3_v16_cuda_owner_lifetime_version5/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_owner_lifetime_version5/kaggle.log
```

For terminal `ERROR`, keep the exact outputs and pass
`--kernel-status KernelWorkerStatus.ERROR`. Criteria round 2 remains unchanged
because version 4 launched no owner arm and measured none of the registered
owner-lifetime outcomes.

### Version 5 exact error and registered round-3 retry

Version 5 terminated as `KernelWorkerStatus.ERROR`. The exact-version output
was recovered to
`work/kaggle_w3_v16_cuda_owner_lifetime_version5/`; the initial verifier record
is `docs/evidence/kaggle_w3_v16_cuda_diagnostic_version5_2026_09.json` and the
append-only exact-stage correction is
`docs/evidence/kaggle_w3_v16_cuda_diagnostic_version5_host_correction_2026_09.json`.
Both output manifests were host-verified. The correction records all four
arm processes, their identical Julia exception, and the wrapper exception.

Exact hashes:

- log: `500306c3c4e0f7ca31dfe7a3c4191b5180ec7a8ad0fd8a154cb008a5581cb8f3`
- captured status: `2341886fe14bda95b1cf663ab933c531b25e6cba8b281d9b6fd6c4cd6d8c5f16`
- output `sha256.json`: `c95d0836fee46c74334599fd7ff00d98559495b19d26224d8cde61ad6525a91e`
- `ERROR.txt`: `01f5ccc61439cb579aba16c988da9a51381fbf6084d20033b5d0396f74b6eb81`
- original evidence: `6e125c47a252fcbbf5c2e78c8342cc16e352a1edea7674bf1510d75a0832e19e`
- host classification correction:
  `907babecef7f5ee9547e3c74a1f18d4bf751e9187a7a078de9bc67f9dd47a823`

The base v16 CUDA diagnostic reached one primal step and host force/artifact
checks passed. Each owner arm then stopped at the `v16_physical_profile_bodies`
lookup with `UndefVarError` in `Main`, before candidate body construction. No
owner or `WeakRef` was created, no forced-GC bracket ran, and no arm geometry,
field, force, or owner-step data exists. This is a Julia job import failure,
not an owner-lifetime or CUDA failure, and it does not explain W3 v4's full-run
all-zero force history.

Round 3 freezes only the required explicit imports for the two non-exported
WaterLily helpers and the new owner-job SHA. Criteria file:
`docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round3.json`;
criteria SHA:
`906fda6a3991d7a37ea29f50ccc851f3788cde9a6bb90dfcc5b11279fb3f4274`;
sidecar SHA:
`23033b9601f6f38932e08c3c5e994651f71559da6b0966f7e0bc4172fe166c03`; owner
job SHA:
`b952aae000f6a2047b050ca5d46bd8fdd1a5c320ebc222bd380b70c0924c8cac`. The
flow fixture, A/C/B1/B2 order, measurements, tolerances, and causal rules are
unchanged. Submit only after the source commit pinned in the runner is pushed.

### Exact version 6 result and WeakRef target limitation

Version 6 completed and its exact `/6` artifacts were retrieved under
`work/kaggle_w3_v16_cuda_owner_lifetime_version6/`. Run the host verifier with
the exact COMPLETE status and output paths:

```bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_owner_lifetime_version6 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 6 \
  --kernel-status KernelWorkerStatus.COMPLETE \
  --kaggle-status-file work/kaggle_w3_v16_cuda_owner_lifetime_version6/kaggle_status.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_owner_lifetime_version6/kaggle.log
```

The first pass found host-verifier assumptions that had not been exercised by
completed owner arms: `julia_archive_sha256` is registered under `criteria.inputs`,
and verified NumPy arrays need to remain internal to comparison rather than be
serialized into JSON. The append-only host correction records those fixes and
the exact owner diagnostic limitation. Artifact/source/runtime verification
passed. The owner experiment itself is incomplete for causal purposes because
the round-3 Julia code calls `WeakRef(owner)` on immutable `DeviceGridSDF`, not
on its backing mutable `CuArray` at `owner.grid.phi`.

This correction does not revise the registered measurements. A and C geometry
arrays and final fields were exactly equal. Candidate geometry counts were 1009
negative CPU/CUDA cells and CPU/CUDA distance difference at most
`4.7683716e-7 m`. The normal discrepancy remained `1.3379748`. B1/B2 geometry
also exactly matched A, and both matched A force through step 1. At step 2,
the drag/downforce pairs were A/C `707.1370 / 847.9948`, B1
`720.2276 / 854.9039`, B2 `712.4746 / 853.7397` solver units; final flow-field
arrays diverged in both B runs. Because the wrapper WeakRef was already clear
before the registered GC bracket (for C, B1 and B2), those differences do not
prove owner collection caused the step-2 response. A/C controls match, but the
owner-lifetime hypothesis remains unresolved.

Exact version-6 hashes:

- runner: `deb12c2b9a9a72993f9a8967f12385d935022306ac25b8c30cd9cd07c3e5bc4e`
- log: `0e300babad42276fcf18f6d9b11d2b6fd5f05802e906bd9c98c5e0becabf4b95`
- captured status: `2f547f8fea5f9f2cc6b6c1d9bf11669c39105cb8dc194699c6d6398fc068a2b1`
- output `sha256.json`: `f4944ddac2b19b6e1ba680964ed587e81c173a3544b8f3a189bd90a6b03b46ac`
- `DONE`: `c3ae0c1108a07ac153b0ee13893bc731b7e210607850bbb5c7956f02c3fc2525`
- first result evidence: `68cf588200b84edf056a815e7d7f35683e113e21533a8819f641d7f17354482d`
- host correction evidence: `ad7e930eda5aa0ade067ed8797cacf03de256c31ddb7390383460e44652b25fb`

The next criteria round must make the WeakRef target explicitly
`owner.grid.phi` and record its runtime type. Preserve the same v16 input,
mapping, arms, full geometry, fields, force snapshots, GC sequence, tolerances,
and causal decision rules. W3 v4 remains unqualified; this scratch result does
not authorize a production ownership fix.

### Owner-lifetime diagnostic round 4 submitted; version 7 running

Round 4 is registered. Its immutable
criteria file is
`docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round4.json`
(SHA-256
`58867bf2e68e989200edb39b401f8db2f52df340db2d84534853dad01679530e`; sidecar
SHA-256
`0637966ce609c452797241e42498e6503a02dde6ba09298b93e692ac5373f3c0`). The
registered owner Julia job SHA-256 is
`3676babc3b7516690a813acb84fa324a46a75e8b98b39c447b755394a80c6212`. The
kernel runner SHA-256 is
`5e004a1e32529271b1b45a7f65086e173ca8246b5df57e8ea127b40f834ea710` and pins
source commit `ffb5cc7edc4d3a598d420ef6c065d10c5c8bbc07`, containing the exact
job, criteria, and sidecar.

This round corrects only the observation method exposed by exact version 6:
all arms WeakRef `owner.grid.phi` (the backing `CuArray`) and record its path
and type. B1/B2 disable automatic GC after constructing the unrooted objects
and WeakRef, check that automatic GC had been enabled, keep it disabled through
pre-GC observations, enable it immediately before each registered `GC.gc(true)`,
disable it between the two forced collections, then leave it enabled. A/C use
the same two explicit collections while their registered owner retention is
active. Inputs, arm order, solver work, force and field probes, comparison
tolerances, and causal decision rules are unchanged. This is diagnostic-only;
it changes no W3 production code or criterion.

Local preregistration checks completed: 40 focused W3/W4/diagnostic tests
passed; Python `compileall` and targeted `py_compile` passed; the Julia owner
job parsed; criteria JSON/sidecar SHA verification and `git diff --check`
passed. Repository-wide pytest completed with 1,089 passed, 37 failed, and 4
skipped. The 37 failures are the known historical tests that need ignored
`work/` checkpoints, logs, and case files absent from this managed checkout;
the focused W3/W4/diagnostic slice is green. After pushing source-pin commit
`dec3e2f0728ba03df2d3951d6c5972bdb41c7d1a`, exact private kernel
`ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7` was submitted with T4 and
7200-second timeout. The first exact-version status was
`KernelWorkerStatus.RUNNING` and is saved as
`work/kaggle_w3_v16_cuda_owner_lifetime_version7/kaggle_status_initial.txt`
(SHA-256
`172bce72b56e63812fe433424e62e85da4677860437b57b598d5db11ec53048c`). No
round-4 logs/output or measurement has been recovered yet. Continue polling
only `/7`; at terminal status, save the terminal status, exact logs and output
to the same version-bound directory and verify them against round-4 criteria
before interpreting the owner-lifetime hypothesis.

### Owner-lifetime diagnostic version 7 exact recovery and host verification

The exact private kernel
`ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7` completed. Its terminal
status, exact-version logs, and output bundle are retained under
`work/kaggle_w3_v16_cuda_owner_lifetime_version7/`. Do not mix these with
versions 5 or 6.

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels status ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels logs ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7 \
  > work/kaggle_w3_v16_cuda_owner_lifetime_version7/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels output ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7 \
  -p work/kaggle_w3_v16_cuda_owner_lifetime_version7
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_v16_cuda_diagnostic.py \
  work/kaggle_w3_v16_cuda_owner_lifetime_version7 \
  --dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --kernel-version 7 \
  --kernel-status KernelWorkerStatus.COMPLETE \
  --kaggle-status-file work/kaggle_w3_v16_cuda_owner_lifetime_version7/kaggle_status_terminal.txt \
  --kaggle-log work/kaggle_w3_v16_cuda_owner_lifetime_version7/kaggle.log \
  --kernel-runner infra/kaggle/kernel_w3_cuda_diagnostic/runner.py
```

The verifier writes append-only
[`version-7 primary diagnostic evidence`](evidence/kaggle_w3_v16_cuda_diagnostic_version7_2026_09.json)
(SHA-256
`66dd9396967f95ef92cb682b24ed14ac4a56345b12cfb2d38f67d4e5bbbb63c3`) and a
matching `.sha256` sidecar. Host artifact verification and owner-lifetime
diagnostic verification pass. A/C retain the backing `owner.grid.phi` WeakRef
through both full GCs; B1/B2 clear it after registered forced GC and reproduce
the same step-2 field/force divergence. B step-2 viscous and total raw force
components are invalid JSON `null` observations, not finite force values; the
host verifier records them only for this registered collected-owner phase and
does not claim closure on those axes.

The first host attempt failed before writing evidence because its verifier
rejected these post-GC B step-2 nulls. The fixed verifier and a separate
append-only record are covered by
[`version-7 host correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version7_host_correction_2026_09.json).
Its SHA-256 is
`53900176b17b0f91a0513c40b531ad538ae028da0b13034244d7fe6ea939ba6c`.
No measurement or criterion changed. Also preserve the exact runtime type
string discrepancy: registered label
`CuArray{Float32, 3, CUDA.DeviceMemory}` versus observed
`CuArray{Float32, 3, CUDACore.DeviceMemory}`. The host verifier surfaces this
and does not assume alias equivalence.

Local correction checks were run with:

```bash
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  -m pytest -q tests/test_kaggle_w3_cuda_diagnostic.py tests/test_kaggle_w3.py tests/test_kaggle_w4.py
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  -m compileall src tests
git diff --check
```

The focused slice passed 42 tests; compileall and diff checks passed. Full
`pytest -q` reported 1,091 passed, 37 failed, and 4 skipped. The failures
reference ignored historical `work/` artifacts (PQ checkpoints, Stage S/V
cases, and logs) absent from this managed worktree; no W3/W4 diagnostic test
failed.

This result supports owner-lifetime sensitivity in the two-step diagnostic
only. It does not prove the cause of W3 v4's full-horizon zero force history,
authorize a production ownership change, or qualify W3 primal, physical
profile, gradient, or any downstream optimization gate. All qualification
flags remain false.

### Full-horizon owner diagnostic round 3, exact kernel version 2

The current exact private kernel is
`ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic/2`. It completed
under immutable criteria
[`round 3`](evidence/kaggle_w3_owner_full_horizon_criteria_2026_09_round3.json),
SHA-256 `2b28c0284833cdc3b360fe2f55e6babb435394b69ea001fcb677fe94c5b40000`.
The version-bound status, Kaggle logs and output are stored in
`work/kaggle_w3_owner_full_horizon_version2/`; do not mix them with version 1
or any W3 primal kernel version.

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels status ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic/2
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels logs ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic/2 \
  > work/kaggle_w3_owner_full_horizon_version2/kaggle.log
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle kernels output ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic/2 \
  -p work/kaggle_w3_owner_full_horizon_version2
PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python \
  scripts/verify_kaggle_w3_owner_full_horizon.py \
  work/kaggle_w3_owner_full_horizon_version2/w3_owner_full_horizon \
  --criteria docs/evidence/kaggle_w3_owner_full_horizon_criteria_2026_09_round3.json \
  --criteria-dataset-dir work/kaggle_w3_owner_full_horizon_dataset_round3_remote \
  --w3-dataset-dir work/kaggle_w3_v16_dataset_round3 \
  --actual-kernel-id ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic \
  --kernel-version 2 \
  --status work/kaggle_w3_owner_full_horizon_version2/kaggle_status_terminal.txt \
  --log work/kaggle_w3_owner_full_horizon_version2/kaggle.log \
  --record-evidence
```

Exact terminal status is `KernelWorkerStatus.COMPLETE`; status SHA-256
`b460246279ec24d862be48d472007531d1b16c7e49584c98fe9fc862fdd28c35`, exact
Kaggle log SHA-256
`763c53bfd5b5fe234da74e2a475ca8dc1a7b73d7befa46566b9a640e7a4ac239`, and
output `sha256.json` SHA-256
`58b7265cfe8f9e53997683e966ec00fadc5d9986ab83201472a03ab5b692324c`. The
host result evidence is
[`round-3 result`](evidence/kaggle_w3_owner_full_horizon_result_2026_09_round3.json),
SHA-256 `72e887e02b406b964bf7b6c617dcf111fc51dc9e1d275fc827689e80e29c9aeb`.

The first host attempt ended with `KeyError: qualification_flags` while
assembling evidence: the immutable schema places the field at
`evidence_output.qualification_flags`. No result was written by that attempt.
The corrected host reader writes the registered output flags and records its
own hash mismatch against the criteria-bound host verifier. This host-only
correction did not alter criteria, measurement data, thresholds, or Kaggle
output. Its append-only evidence is
[`round-3 host correction`](evidence/kaggle_w3_owner_full_horizon_result_2026_09_round3_host_correction.json),
SHA-256 `a56590757b46b176102d7c3e92517bbac57d7d9740ca41036c72fd28bbe29ccb`.
The registered verifier SHA is
`c38a6547ec75929c131c449a1a0b449a6b1d4d467c2af9696e60c1d1eec6bc84`; the
corrected local verifier SHA is
`8e46de364be46b54dc8a52d347a64a45b265e7068ffff653965b48be36b53153`. Keep
both values visible; they are not the same hash.

The result confirms the registered owner-lifetime production-fix gate, but
does not reproduce W3 v4's exact all-zero force history. A-natural/A-forced
retained the owner and completed 4,808 steps with finite, nonzero force; their
601 samples matched. Both B-natural replicas observed collection at step 1.
The first sampled non-finite force occurred at step 16 (`tU/L=0.3506548703`)
and step 128 (`tU/L=3.0178484917`); registered velocity/pressure snapshots
were finite. Therefore the lifetime contract is a confirmed implementation
defect, while the exact v4 all-zero root cause remains open. The production
fix uses `OwnedV16Run` to retain the backing owner and preserve that run bundle
through `run_primal`; a new immutable W3 round is required before the next
T4 qualification attempt. W4 and formal FD remain blocked.

### W3 production owner fix: immutable qualification round 4 registered

W3 round 4 applies only the structural `OwnedV16Run` owner-retention fix. Its
immutable criteria are
[`kaggle_w3_v16_primal_criteria_2026_09_round4.json`](evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json),
SHA-256
`eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`; the
sidecar contains the same digest. The source commit is
`ee6298e843e130b121d918ca9a321b707dcd4ae0`. The criteria preregister the owner
diagnostic criteria/result/correction identities and preserve round-3 W3
geometry, force, backend, runtime, thresholds and claims. The drag/downforce
2% stationarity limit is inherited from the already registered W2 sphere
capability convention; it was not chosen from W3 v3/v4 measurements. W3 v4's
all-zero force root cause remains unresolved.

The round-4 registration check passed before any round-4 primal computation:

```bash
PYTHONPATH=src:scripts .venv/bin/python \
  scripts/register_kaggle_w3_v16_primal_2026_09.py --round 4 --check
python3 -m json.tool \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json >/dev/null
shasum -a 256 docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json
git diff --check
```

After committing and pushing the exact criteria and documentation, stage the
canonical state into a new work directory; do not reuse or overwrite the
round-3 stage or a downloaded version-bound run. The source state remains the
registered canonical v16 NPZ:

```bash
PYTHONPATH=src:scripts .venv/bin/python \
  scripts/prepare_kaggle_w3_dataset_2026_09.py \
  work/kaggle_w3_v16_dataset_round3/sdf_design_state.npz \
  docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json \
  work/kaggle_w3_v16_dataset_round4
```

Verify the staged dataset manifest and full staged inventory first. Then use
the existing private dataset ID and retrieve its just-published version into
a fresh directory:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle datasets version -p work/kaggle_w3_v16_dataset_round4 \
  -m "W3 v16 owner lifetime fix immutable criteria round 4" --dir-mode zip
uvx --index https://pypi.org/simple --from kaggle==2.2.4 \
  kaggle datasets download -d ramhachi888/cfd-opt-sdf-v16-genesis-state \
  -p work/kaggle_w3_v16_dataset_round4_remote --force --unzip
```

Before submitting a kernel, compare the complete file inventory and SHA-256
values from the staged and re-downloaded directories (including the criteria,
criteria sidecar, canonical NPZ, Fortran-order phi, dataset manifest and
dataset metadata). Any mismatch is an infrastructure stop; do not submit until
the registered bytes are present remotely. Push
`infra/kaggle/kernel_w3` with `--accelerator NvidiaTeslaT4 --timeout 7200`,
record the exact version returned by Kaggle, and use only that version for
status, logs, output and host verification. W3 remains unqualified before that
exact host verification; W4 measurement and formal FD remain blocked.
