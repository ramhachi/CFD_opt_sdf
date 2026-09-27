# Kaggle background GPU runbook (K0 and W1g)

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

Use the version printed by `push` if it is not 4, and change both the output
reference and directory to match. The verifier checks the output file
manifest, registered criteria and prerequisite hashes, uploaded runner hash,
source commit, fixture parameters, runtime/GPU identity, and recomputed G1–G9
gates. A failed run is retained as diagnostic evidence. Only a fully verified
round-2 pass opens the next planned slice, W2-T4b.
