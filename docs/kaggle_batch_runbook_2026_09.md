# Kaggle background GPU runbook (K0, W1g, W2-T4b, and W2b)

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
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/10
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/10
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder/10 -p work/kaggle_w2b_version10
PYTHONPATH=src:scripts .venv/bin/python scripts/verify_kaggle_w2b.py \
  work/kaggle_w2b_version10
```

Use the version actually returned by `push` consistently in all four Kaggle
commands and the retrieval path. A missing `DONE`, `ERROR.txt`, hash mismatch,
or any failed gate remains diagnostic; do not relax numerical thresholds after
seeing the solver result. Rounds 2, 3 and 4 preserve round-1 numerical bounds.
No complete W2b ladder measurement is recorded in this runbook until the exact
version-specific output has passed host verification.
