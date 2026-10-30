# FD-05 (#37) result: v17 / flow_24 directional-FD round 1

**Verdict: terminal FAIL, fail-closed.** The single registered Kaggle kernel
completed all 33 fresh primal runs. The N-based directional resolution and
plateau gates T10 and T11 failed. Strict host verification also failed closed
because Kaggle returned `KernelWorkerStatus.ERROR` and the output had no `DONE`
marker. No kernel retry was submitted and no registered criterion was changed.

## Implementation and registered contract

The FD workflow was generalized for v17 and `flow_24` in the Julia job,
shared and v17 Kaggle runners, registrar, dataset preparation, CPU preflight,
host verifier, and FD tests. Canonical label, shape, spacing, hashes, and flow
case are read from criteria; v16 defaults and the meaning of earlier criteria
remain intact. The v17 criteria regenerated all three directions and 30
perturbations through the existing `generate_directions` and
`perturbed_state` functions; the generators themselves were not modified.
The immutable measurement contract kept the R5 absolute ε ladder, 33-run
composition, measurement windows, noise/resolution/sign/plateau thresholds,
stationarity limits, and resource gates unchanged.

## Registered run identity

- Canonical state: v17, state SHA-256
  `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`,
  121×65×49 points, design spacing 0.025 m.
- Flow case: `flow_24`, 150×72×54, spacing 1/30 m.
- Criteria: round 1, file SHA-256
  `782cdea8c92a9a9ac54bdc7d85e87c0c52fc744ac3934d88c9119c1b3fad0844`,
  bound to source commit
  `933b043f993a2136daba906d85a44d38e23dee04`.
- Dataset: `ramhachi888/cfd-opt-sdf-v17-flow24-directional-fd-oracle`, version
  2. Its 37 registered inputs and manifest were remotely verified with an
  exact 38-file inventory. Dataset manifest SHA-256:
  `4143b048eeee8343a82ea8c62e21733d107a1835987f6db4a6ea1e4ec2e6749e`.
- Kernel: `ramhachi888/cfd-opt-sdf-v17-flow24-fd-oracle`, version 1. It was
  submitted once and ended with `KernelWorkerStatus.ERROR` after all solver
  calls completed. No retry was performed.

The local Julia 1.12.6 CPU pre-step reached immediately before the first
`sim_step!`; all 33 run identities and 30 perturbation identities passed that
preflight. The existing `generate_directions` and `perturbed_state` generators
were used without modification. The append-only record is
[`sdf_directional_fd_v17_flow24_cpu_prestep_schemafix5_2026_09.json`](../evidence/sdf_directional_fd_v17_flow24_cpu_prestep_schemafix5_2026_09.json),
SHA-256 `fc5d562493715e0177f4f911333c654e963dcc256227a916c82eb038bf9535ce`.

## N-based force and directional results

Baseline A/B/C were bit-identical after host recomputation: drag was
`0.32631743972608007 N` on each repeat and downforce was
`0.33102903147696705 N` on each repeat. For each response the baseline span
was `0 N` and the registered noise floor was `1e-8 N`; the resolved-pair
threshold was therefore `2e-7 N`.

Pair signals below are `|R(+ε) − R(−ε)|` in N, ordered by the unchanged ε
ladder 0.0005, 0.001, 0.0025, 0.005, 0.01 m. All five pairs in each row were
resolved and had stable derivative sign over the first three registered
plateau epsilons. The maximum relative plateau deviation is evaluated over
those three epsilons against the unchanged 5% criterion.

| Direction | Response | Pair signals by ε (N) | Max plateau deviation | Gate |
| --- | --- | --- | ---: | --- |
| D0 interface offset | Drag | 0.0025233, 0.0023561, 0.0019482, 0.0014335, 0.0019494 | 114.20% | T10 FAIL |
| D1 filtered seed 11 | Drag | 0.0013957, 0.0014157, 0.0014721, 0.0015632, 0.0018707 | 97.18% | T10 FAIL |
| D2 filtered seed 2026 | Drag | 0.0009113, 0.0007289, 0.0001750, 0.0007607, 0.0025744 | 150.04% | T10 FAIL |
| D0 interface offset | Downforce | 0.0009511, 0.0017687, 0.0038673, 0.0072436, 0.0121178 | 12.54% | T11 FAIL |
| D1 filtered seed 11 | Downforce | 0.0010211, 0.0011121, 0.0014217, 0.0018324, 0.0026043 | 83.63% | T11 FAIL |
| D2 filtered seed 2026 | Downforce | 0.0005182, 0.0004331, 0.0000854, 0.0004712, 0.0015097 | 139.28% | T11 FAIL |

Thus all six direction/response combinations fail the registered plateau
gate. Pair magnitudes alone do not establish why the plateau fails; this run
does not identify a causal mechanism for the non-plateau response. The W4
flow_24 reference and the FD baseline agree exactly at the registered
precision: drag `0.32631743972608007 N`, downforce `0.33102903147696705 N`.
That is a cross-check, not an additional qualification gate.

## Host verification and evidence scope

The strict verifier from the exact registered source commit stopped with
`ValueError: FD Kaggle output has no DONE marker`. The append-only strict
diagnostic is
[`sdf_directional_fd_v17_flow24_kernel1_diagnostic_2026_09.json`](../evidence/sdf_directional_fd_v17_flow24_kernel1_diagnostic_2026_09.json),
SHA-256 `07e69cefd87dad8c21bcb9c25b60f68fb4ee72e86d17dacf99cee8151c029244`.

A separate diagnostic-only recomputation then used the registered verifier
helpers at that same source commit. It verified the exact registered source
inputs, mounted dataset inputs, direction and perturbation identities, Julia
progress, all 33 raw force CSVs and summaries, all output SHA-manifest entries,
runtime identity, force closure, stationarity, and runner-summary metrics.
Those checks do not turn the strict result into a pass. The host T12 gate is
false: Kaggle status is `ERROR`, `DONE` is absent, and the runner's
`outcome.json` criteria hash does not match the canonical hash expected by the
registered host verifier (`outcome.json`: file SHA
`782cdea8c92a9a9ac54bdc7d85e87c0c52fc744ac3934d88c9119c1b3fad0844`; host
expects canonical criteria SHA
`d1abe118efdce1e04b88064232deec7e49067ecc6a7d30338d7cd5b974ad82a1`). The
runner's recorded T0-T11 gates and 33 metric records otherwise match the host
recomputation, including the T10/T11 fails.

The full N-based recomputation and exact provenance checks are preserved in
[`sdf_directional_fd_v17_flow24_kernel1_host_recomputed_metrics_2026_09.json`](../evidence/sdf_directional_fd_v17_flow24_kernel1_host_recomputed_metrics_2026_09.json),
SHA-256 `f0d72a49376e78b2efd0a31b176d4cf9a47c564d9d2d484ac188c24fc735d8d1`.
Both diagnostic JSON files have adjacent `.sha256` sidecars. The registered
dataset upload verification is
[`sdf_directional_fd_v17_flow24_dataset_v2_verification_2026_09.json`](../evidence/sdf_directional_fd_v17_flow24_dataset_v2_verification_2026_09.json),
SHA-256 `e30cf7fb8a9af4bee941c292da9f875f6b7a4334a55030e368268caa1fcca9aa`.

Implementation checks before execution: `compileall` passed; the focused FD
tests passed (`43 passed`); full pytest reported `1210 passed, 37 failed,
4 skipped`, with exactly the same 37 failure IDs as the recorded baseline and
no new failures; `git diff --check` passed. The 37 full-suite failures are the
known missing ignored `work/` fixtures documented in the session handoff.

This result supports only the exact v17 / flow_24 registered directional
response observations and their terminal FAIL. It does not qualify the FD
oracle, a gradient, a causal explanation, physical force accuracy, grid
convergence, an optimizer, topology, or a shape update. All qualification and
`shape_update_allowed` flags remain false. No follow-on gradient issue is
started by this result.

## Addendum 2026-10-01: solver-free diagnosis

A diagnostic-only re-analysis of the raw outputs is recorded in
[`37_fd05_solver_free_diagnosis.md`](37_fd05_solver_free_diagnosis.md). It does
not change the verdict above.
