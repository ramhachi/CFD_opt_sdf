# Kaggle background GPU runbook (K0, W1g, W2-T4b, W2b, and W3)

This is the execution path for the SDF-native WaterLily GPU line. The
authoritative order and gate status are in [`phase_plan.md`](phase_plan.md),
and the numeric K0 contract is
[`evidence/kaggle_k0_criteria_2026_09.json`](evidence/kaggle_k0_criteria_2026_09.json).
The existing Colab evidence remains a reference. No sampled-sphere, v16, or
optimizer result follows from K0 or W1g alone.

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
