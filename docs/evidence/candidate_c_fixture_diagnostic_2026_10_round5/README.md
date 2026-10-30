# Candidate C bounded CPU diagnostic, Round 5

Evidence class: exploratory bounded CPU primal diagnostic. This round does not
qualify W2a, mass conservation, solver equivalence, W3-C, W4-C, or the production
operator. Its short sphere differs from the registered W2a sphere.

The immutable plan is `plan.json` (SHA-256
`40e81772763eacbcb5943a8e79abccd0931e6573fdeb489ba4f575ad674dcdd2`), the
runner is `scripts/candidate_c_grid_sdf_fixture_probe.jl` (SHA-256
`b9723f7c5f10bd55f17878e97ff52b6de41927464c2fc6b52db5e8f367498acf`), and the
input source manifest is `runner_sources.sha256` (SHA-256
`6bb8ba232d10f48cc5f05e0f80a8061d486efcdc2ba179a6a2c5c2902689d6c4`). The
result manifest `run-001.csv.sha256` binds those inputs and both result CSVs.

Execution command:

```text
julia -t auto --project=julia/CFDSDFWaterLily scripts/candidate_c_grid_sdf_fixture_probe.jl docs/evidence/candidate_c_fixture_diagnostic_2026_10_round5/plan.json work/candidate_c_fixture_diagnostic_2026_10_round5/run-001.csv
```

It exited 0 and wrote 12 aggregate rows and 126 per-step rows across native,
sampled-upstream, and Candidate C arms for the sphere, 1-cell plate, 2-cell
plate, and moving-ground-only fixtures. Each force was converted to N with
`rho*U^2*dx^2 = 0.0025 N` per solver-force unit. Raw inlet/outlet plane sums are
velocity flux proxies only.

The aggregate CSV has SHA-256
`eaba35128a168366574efc685f31f5b4dc8daebdf7c7de4a1bcdff6f5062403d`; the raw
history has SHA-256
`f29f2f6ffb396424006d6587a26ea042f95c46a7e0ea85bee71fa666ef915dfa`; and the
result manifest has SHA-256
`b3d52ddc8f26d8e2caab012a80e179a2b598f0816d58157ec85a88561e6685bc`. Identical
copies of the generated `work/` artifacts are stored beside this README for
repository retention.

Post-run checks independently verified 126 finite samples, all force closure
errors below `2.85e-14 N`, and a before/after bracket for every `[0.10, 0.25]`
window. Independently recomputed endpoint-interpolated trapezoid means for all
nine force components agree with the aggregate within `5.56e-17 N`. These are
integrity checks on this diagnostic, not acceptance gates for the operator.

## Append-only preflight history

- Round 1 was rejected before solver execution for incorrect force conversion,
  confounded controls, arithmetic rather than endpoint-window averaging,
  unenforced stop conditions, and a sphere different from W2a.
- Round 2's first attempt failed before any solver step because `String` could
  consume the plan byte buffer before the hash check. Preserved log:
  `../candidate_c_fixture_diagnostic_2026_10_round2/preflight_attempt1.log`.
- Round 3's first execution failed before any solver step because Julia 1.12
  does not support `open(..., "x")`. Preserved log:
  `../candidate_c_fixture_diagnostic_2026_10_round3/preflight_attempt2.log`.
- Round 4's no-step initialization caught the normal-floor origin being passed
  as a vector rather than a tuple. Preserved log:
  `../candidate_c_fixture_diagnostic_2026_10_round4/init_preflight.log`.

No failed preflight called `sim_step!` or produced measurement evidence.
