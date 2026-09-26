# Colab T4 batch-worker execution plan — 2026-09-26

Date: 2026-09-26
Status: plan-only, solver-free. No evidence, manifest, or flag changes.
Authority: subordinate to [`phase_plan.md`](phase_plan.md). This document is an
additive amendment to the hash-frozen
[`CFD_opt_sdf_SDF_native_handoff/00_HANDOFF_MASTER.md`](CFD_opt_sdf_SDF_native_handoff/00_HANDOFF_MASTER.md)
§16 (Colab-first runtime) and §17 (hardware roles); the frozen master itself is
not edited, consistent with `sdf_native_architecture_registration_2026_09.json`.

## 1. Decision

Colab use is authorized from this point on. The execution design becomes:

```text
session controller agent (ChatGPT/Codex/OpenCode)
        ↓  Colab MCP / driven notebook
Colab T4 worker (batch)
        ↓  git exact commit + pinned Manifest
one job manifest entry
        ↓
immutable artifacts on Drive
        ↓
result.json → controller queues the next job
```

The design target is explicitly: **design the Colab T4 as the primary
production worker.** The frozen master's "do not assume a fixed Colab GPU type"
remains as an engineering discipline (runtime fingerprints, per-backend
identity), but the qualification and campaign design is targeted at T4-class
16 GB runtimes, not generic.

## 2. Hardware architecture (fixed)

| Role | Hardware | Duty |
| --- | --- | --- |
| Primary | Colab T4 | all CUDA primal / FD perturbation / campaign jobs |
| Secondary | Colab CPU | Julia env validation, small smoke cases, CPU regression before GPU spend |
| Witness / development | RTX 4070 Ti | re-run of the **same manifest** when a T4 result looks wrong (independent CUDA witness); local development only |
| Control plane / lightweight | MacBook Air | manifests, review, Python tests, 4070 Ti launching, SDF geometry ops (Julia install pending) |

The optional, non-blocking Metal Float32 spike on the MacBook Air stays as
recorded in the 2026-09-26 audit addendum.

## 3. Batch-worker execution model

Colab notebooks are never research logic. A notebook is a thin bootstrap
wrapper. The authoritative notebook set is reduced to one worker plus a probe:

```text
colab/worker.ipynb
colab/00_runtime_probe.ipynb   (optionally kept for manual debugging)
```

`worker.ipynb` does exactly this, in order:

1. Drive mount;
2. repo clone / fetch;
3. checkout the manifest's exact commit (dirty-worktree check must fail closed);
4. Julia environment instantiate (pinned Manifest);
5. GPU / runtime probe → `runtime.json`;
6. `run_worker(job_manifest)` — repo-side logic, started with fail-closed exit;
7. artifact flush (the last thing that happens, on every exit path).

All research logic lives in the repository:

```text
scripts/run_waterlily_job.py     # job runner orchestration
julia/CFDSDFWaterLily/...        # solver-side implementation
```

The controller drives with four verbs:

```text
run job abc123
show status
fetch result
resume campaign
```

MCP wiring for Colab is an open integration item; the verb set is the design
contract regardless of which agent sits in the control plane.

## 4. Campaign directory layout (Drive-persistent)

```text
campaign/
  manifest.json                 # immutable, hash-recorded before any run
  jobs/
    001.json
    002.json
  results/
    001/
      result.json               # fail-closed, written on success AND failure
      runtime.json              # runtime fingerprint
      force_history...          # raw artifacts
```

Rules:

- `manifest.json` is generated on the control plane before any run and is
  immutable afterwards; a changed manifest is a new campaign.
- Job state machine: `pending → claimed (runtime.json started) → done | failed`.
  Flat: one worker at a time; no local job locking; the worker picks the next
  uncompleted job ID sequentially.
- Idempotency: a job with an existing valid `result.json` is skipped unless the
  manifest declares `"rerun": true`.
- A dead Colab session loses nothing: a fresh T4 runtime restarts step 1–7 and
  continues. This implements the standing rule **"die only after flushing
  logs"**: any exit path (exception, disconnect, OOM) must first write partial
  logs plus a fail-closed `result.json` to Drive.

## 5. Job kinds

SDF centered-FD qualification (the first real consumer):

```text
direction_01_plus
direction_01_minus
direction_02_plus
...
```

No controller-side numerical logic: the FD bracket direction list is expanded
into one immutable job per (direction, sign); qualification logic (epsilon
plateau, noise floor, 5% rule) is evaluated by repo-side scripts from
`result.json` files, never inside the notebook.

After the reverse backend exists, the optimization loop becomes the same job
grammar: `parent_primal`, `gradient`, `trial_primal` are separate immutable
jobs. Acceptance logic stays on the control plane / repo side per the master's
§14 (never accept from an adjoint prediction alone).

## 6. Runtime identity and memory discipline

Every job must record `runtime.json` with at least: platform, GPU name, VRAM,
CUDA driver/runtime, Julia version, WaterLily commit, Enzyme version, repo
commit, precision, grid, Re, Poisson tolerance, measurement window (per
master §16). A changed T4 runtime is a different backend identity, exactly as
the master already demands.

T4-specific memory: Float32 by default; reverse-mode memory policy follows
master §10 (bounded horizons, checkpoint/recompute, custom rules) sized to the
16 GB budget. No full-timestep tape is designed — unchanged.

## 7. What this changes in the PR plan

- PR-03 (WaterLily stable primal bridge): default execution matrix becomes
  Colab T4 (primary) + Colab CPU smoke; RTX 4070 Ti becomes the re-run witness
  for anomalous T4 results. Previously local-first CUDA work is demoted.
- PR-06 (SDF directional FD): the preregistered direction set is executed as
  per-(direction, sign) manifest jobs on T4; FD qualification reasoning stays
  repo-side.
- PR-07/PR-08: unchanged in content (pinned PR #285 replay; bounded CUDA
  spike), now targeted at T4 as the qualification runtime.
- Unchanged: gate order (SDF genesis → WaterLily primal → SDF centered FD →
  CPU reverse → GPU reverse Go/No-Go → one SDF update → topology birth →
  OpenFOAM PQ5); all qualification flags remain `false` until their registered
  gates pass; no qualified-gradient, shape-update, or benchmark claim is
  authorized by this document.

## 8. Open items

1. Colab MCP integration for the four controller verbs (or an explicit
   "paste-command" fallback for the first campaign).
2. `scripts/run_waterlily_job.py` and the worker state machine do not exist
   yet; they arrive with PR-03 (primal) / PR-06 (FD).
3. Julia pinning (from the audit: Julia is not installed locally; the T4
   primary path makes local Julia a dev-only convenience).
4. No Docker assumption on Colab; no credentials cached in Drive.
