# Candidate C inherited W2a sphere preparation

This directory records preparation for a new immutable W2a-C Round 2. No
W2a-C numerical solver step has run. Round 1 was frozen as an exact rejected
pre-execution snapshot at
`candidate_c_w2a_sphere_cpu_2026_10_round1_rejected/`; it was superseded before
measurement because it could lose transcript/partial-history evidence on
failure or timeout and serialized the native arm's not-applicable SDF margin as
non-standard JSON `NaN`.

Round 2 criteria:

- `candidate_c_w2a_sphere_cpu_criteria_2026_10_round2.json`
- SHA-256 `1185b98aa69d1765b6fe6829305e5842a2e81a5fd2c22c76ddfd4a478c8b51ec`
- source manifest `candidate_c_w2a_sphere_cpu_sources_2026_10_round2.sha256`
- source manifest SHA-256 `d7f935eb56da31c5d0e50711c344f924fe3122e6ab26794e24d4414458502d4d`

The registered fixture is inherited unchanged from W2a: Float32 Array,
`96×64×64`, `Re_D=100`, the exact sampled sphere with `D=1 m`, and the
`[40,60] tU/D` window split at 50. The arms are native analytic sphere,
same-grid sampled GridSDF through upstream `normal_floor=0.25` (diagnostic
only), sampled GridSDF through the Candidate C composite body (primary), and a
fresh analytic repeat. The Candidate C identity is the moment blend together
with `normal_floor=0.25`, using the frozen transition width from FD-07.

The numeric limits remain the inherited W2a limits: 2% stationarity, 10%
Candidate C versus native analytic Cd, 10% lift/drag, and `1e-6` analytic
repeatability. This new round explicitly uses linearly interpolated endpoints
at 40, 50, and 60 followed by trapezoidal time integration. The historical
W2a runner used arithmetic sample means. The registered criteria text also
uses reference-value denominators for comparisons, while the historical helper
used a symmetric maximum denominator. These evaluator semantics are different
in this round; no historical criteria or evidence is edited, and the numeric
thresholds are not relaxed. W3-C/W4-C remain governed by their own existing
criteria/evaluator.

The runner preserves and flushes each raw force and mass-flow sample to CSV.
It records all sample brackets needed to independently recompute the three
window means. Julia transcripts are written on success, error, and timeout. A
failure writes append-only `terminal-FAIL.json` with the stage, criteria/source
identity, scope, and hashes of available partial artifacts. Existing output
paths are not overwritten; an atomic claim directory reserves the run.

Forces are recorded in solver units and N using
`rho*U_ref^2*h^2 = 0.00390625 N` per solver-force unit. Signed outward mass
flow is recorded on all six external boundary planes using
`rho*U_ref*h^2 = 0.00390625 kg/s` per solver-velocity unit. Net boundary flow,
integrated discrete divergence, and their difference are finite-value
integrity diagnostics only; there is no mass-conservation threshold or
conservation qualification claim. Sampled GridSDF arms must meet the inherited
three-spacing margin gate of `0.15 m`. The analytic native control reports
its not-applicable margin as JSON `null`.

Before a solver run, the registered command supports `--preflight-only`, which
checks source identities and initializes Candidate C without calling
`sim_step!`. The Round 2 preflight transcript is stored separately after the
source manifest and criteria hashes are finalized. Parent source review is
required before any measurement.

This fixture cannot establish production acceptance, W3-C/W4-C qualification,
absolute physical accuracy, grid convergence, or mass conservation. Every
qualification flag remains false.
