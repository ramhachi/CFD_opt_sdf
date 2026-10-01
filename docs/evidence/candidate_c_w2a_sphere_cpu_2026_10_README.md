# Candidate C inherited W2a sphere preparation

This directory contains the pre-measurement W2a-C Round 3 registration. No
W2a-C numerical solver step has run. Rounds 1 and 2 were rejected before
measurement and are preserved in `candidate_c_w2a_sphere_cpu_2026_10_round1_rejected/`
and `candidate_c_w2a_sphere_cpu_2026_10_round2_rejected/` respectively.
Round 2 was rejected after review found its G5 implementation used
`abs(first_half-full_mean)` instead of the preregistered
`abs(first_half-second_half)`, which could understate drift and falsely pass.

Round 3 criteria:

- `candidate_c_w2a_sphere_cpu_criteria_2026_10_round3.json`
- SHA-256 `eecb4d1291032231f6b283c3aafabaf4b57c25e704c94601dbd710a825c5c540`
- source manifest `candidate_c_w2a_sphere_cpu_sources_2026_10_round3.sha256`
- source manifest SHA-256 `14d0d4da783a07ee8fc7c3d640e6f1097c25fde13ebc4db2b93e3f3839f008ce`

The fixture is inherited unchanged from W2a: Float32 Array, `96×64×64`,
`Re_D=100`, exact sampled sphere with `D=1 m`, and `[40,60] tU/D` split at
50. Arms are native analytic sphere, same-grid sampled GridSDF through
upstream `normal_floor=0.25` (diagnostic only), sampled GridSDF through the
Candidate C composite body (primary), and a fresh analytic repeat. Candidate C
identity is the moment blend together with `normal_floor=0.25`, using the
frozen transition width from FD-07.

The numeric limits remain the inherited W2a limits: 2% stationarity, 10%
Candidate C versus native analytic Cd, 10% lift/drag, and `1e-6` analytic
repeatability. This new round uses linearly interpolated endpoints at 40, 50,
and 60 followed by trapezoidal time integration. The historical W2a runner used
arithmetic sample means. The registered criteria text uses reference-value
denominators, while the historical helper used a symmetric maximum denominator.
These evaluator semantics differ in this round; no historical criteria or
evidence is edited, and numeric thresholds are not relaxed. W3-C/W4-C remain
governed by their own existing criteria/evaluator.

The runner flushes each raw force and mass-flow sample to CSV. It independently
recomputes exact window statistics from CSV and requires the results to match
the Julia summary within the preregistered numerical-integrity tolerance; raw
derived values are used for G4-G8. G5 is exactly
`abs(mean_drag(40–50)-mean_drag(50–60))/abs(mean_drag(40–60))`, with the two
equal-duration half windows. Zero or non-finite denominators fail closed.
Julia transcripts are written on success, error, and timeout. Failure writes
append-only `terminal-FAIL.json` with stage, criteria/source identity, scope,
and hashes of available partial artifacts. Existing output paths are not
overwritten; an atomic claim directory reserves the run.

Forces are recorded in solver units and N using
`rho*U_ref^2*h^2 = 0.00390625 N` per solver-force unit. Signed outward mass
flow is recorded on all six external boundary planes using
`rho*U_ref*h^2 = 0.00390625 kg/s` per solver-velocity unit. Net boundary flow,
integrated discrete divergence, and their difference are finite-value
integrity diagnostics only; there is no mass-conservation threshold or
conservation qualification claim. Sampled GridSDF arms must meet the inherited
three-spacing margin gate of `0.15 m`. The native analytic control reports
its not-applicable SDF margin as JSON `null`.

The runner's `--preflight-only` mode checks source identity and initializes
Candidate C without calling `sim_step!`. Parent source review is required
before any measurement. This fixture cannot establish production acceptance,
W3-C/W4-C qualification, absolute physical accuracy, grid convergence, or mass
conservation. Every qualification flag remains false.
