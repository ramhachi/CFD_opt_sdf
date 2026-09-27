# Kaggle background GPU runbook (K0)

This is the execution path for the SDF-native WaterLily GPU line. The
authoritative order and gate status are in [`phase_plan.md`](phase_plan.md),
and the numeric K0 contract is
[`evidence/kaggle_k0_criteria_2026_09.json`](evidence/kaggle_k0_criteria_2026_09.json).
The existing Colab evidence remains a reference. No W1g, sampled-sphere, v16,
or optimizer result follows from K0 alone.

K0-A–F passed on 2026-09-27. Version 1 was the GPU inventory smoke; version 2
ran the Julia environment, analytic sphere and dual-process checks. The
append-only result is
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
- The source fetched by the kernel is the exact public commit
  `d81d0ccd13379fc86de48d52a797e6e7612658bd`, the last unchanged solver
  commit before this migration. The Julia binary and Project/Manifest are
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

## Submit and collect

Run from this repository's root. Kaggle credentials stay in the user's normal
Kaggle CLI configuration; do not print or upload them.

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel --accelerator NvidiaTeslaT4 --timeout 7200
```

Record the version number printed by `push`. Use that explicit version for
every later command; an unversioned `output` can point at a newer run.

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
