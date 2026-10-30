# FD-07 sign-consistency causal diagnosis — 2026-10-01

## Result

This bounded intervention supports **Case A for the dominant short-horizon
solved-force irregularity on the registered v17 / `flow_24` CPU fixture**.
Disabling only WaterLily 1.8.0's face-distance sign-consistency correction
removed the large perturbation-induced initial `μ₀` jump and reduced the
measured force departures by roughly three to five orders of magnitude in
most comparisons. The weakest reduction among the recorded odd force
responses was still about 108-fold. Residual responses remain, so this is not
a claim of zero response or an `ε`-proportional finite difference.

This advances the FD-06 mechanism from a solver-free localization to bounded
causal evidence for this fixture. It does not qualify the formal centered-FD
result or generalize to another geometry, resolution, thin-body regime, or
physical flow. The correction is part of the discrete inside/outside
construction; deleting it from production is not a remedy authorized by this
diagnostic. A future remedy would need to preserve the intended geometry and
baseline semantics, including thin-body treatment and conservation, and be
qualified separately.

## Preregistered experiment

The plan was written and hashed before initialization or force results were
inspected. Plan SHA-256: `790a50aaa5eee8342c8f09ade54db808fd4992dcdfeaee6c6d48969f6f153478`.
The exact starting commit was
`b41c8fa8ff054f7f9aeee983850dadeefdf8a7d4`, on a dedicated branch from
`codex/kaggle-batch-migration`. WaterLily 1.8.0 `Body.jl` SHA-256 was
`aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee`.

The two arms were `UPSTREAM` (diagnostic copy matching the pinned correction)
and `NO_SIGN_CORRECTION` (the same private initialization with only that
`copysign` operation omitted). Production source and the Julia package were
not changed. Both arms used original v17 coordinates and `h=0.025 m`,
`flow_24` (`150×72×54`, spacing `1/30 m`), normal floor 0.25, Float32 CPU
arrays, unchanged pressure settings, the same moving ground, and no shifted
lattice. For each arm there was one baseline and paired `+/-` perturbations
at `1e-8 m` and `1e-7 m` for seeds 1, 11, and 2026: 26 solves total.
The per-arm baseline was intentionally run once; no baseline repeat variance
was estimated.

The implementation difference is one expression in the private diagnostic
copy, at the point where sampled face distance is passed to the BDIM moments:

```julia
# UPSTREAM
dᵢ = abs(dᵢ) ≤ 0.5 ? dᵢ : copysign(dᵢ, d[I])

# NO_SIGN_CORRECTION
# leave dᵢ as sampled; the next μ₀/μ₁ calls are unchanged
```

The pinned routine and its discrete geometry meaning are summarized in the
[WaterLily semantics note](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/waterlily_semantics.md).

Every perturbation used a shared seed/noise field across arms. The persisted
`realized_noise.csv` records raw noise hashes and the Float32-quantized node
count, RMS, and maximum magnitude. The exact `[2,3] tU/L` metric is independently
integrated from raw histories with endpoint interpolation and trapezoids, then
converted by `1/900 N` per solver-force unit. Odd/even definitions are
`(R+−R−)/2` and `(R++R−)/2−R0`. No new pass threshold was applied.

## Initial coefficient comparison

Across the six seed/amplitude pairs, the maximum `|Δμ₀|` relative to each
arm's own baseline was `0.81831127–0.81831428` in `UPSTREAM`, with 51–136
faces above `10⁻³`. In `NO_SIGN_CORRECTION` it was `8.34×10⁻⁷–9.30×10⁻⁶`,
with zero faces above `10⁻³`. The baseline A/B comparison itself has one
changed `μ₀` face with maximum difference `0.8183106184`; this is the expected
discrete-model change from the intervention and is recorded explicitly.

The nine fixed-face scalar control groups (maps A/B/C × baseline and two
10-nm perturbations, 261 rows per group) passed a Float32 re-evaluation against
the previously registered CSV. The control reproduced the corrected A/C
jumps (`0.8183102–0.8183113`, depending on case) and the no-correction
roundoff-scale changes (at most `2.98×10⁻⁷`) within its preregistered
tolerance; corrected face distances were bitwise equal. This is a scalar
replay of recorded samples, not a full set of map initializations.

The detailed per-seed initialization data and branch counts are in
[`initialization_comparison.csv`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/initialization_comparison.csv)
and [`summary.json`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/summary.json).

## Solved-force response

Each perturbed history had 29 samples and reached `tU/L ≥ 3`. The table gives
the signed odd/even components in N. The full table includes plus/minus
departures, all six total/pressure/viscous responses, arm baselines, and
`NO_SIGN_CORRECTION / UPSTREAM` magnitude ratios for every seed and amplitude.

| Seed | ε (m) | Drag odd/even UPSTREAM (N) | Drag odd/even NO_SIGN (N) | Downforce odd/even UPSTREAM (N) | Downforce odd/even NO_SIGN (N) |
|---:|---:|---:|---:|---:|---:|
| 1 | 1e-8 | −1.057e-4 / 2.502e-4 | −7.253e-8 / −2.131e-8 | −1.233e-4 / 8.536e-4 | 2.836e-7 / 2.117e-7 |
| 1 | 1e-7 | 7.638e-4 / −5.530e-4 | 4.370e-8 / 1.783e-11 | 2.321e-4 / −1.889e-4 | −1.753e-7 / 1.080e-7 |
| 11 | 1e-8 | 3.251e-6 / 3.117e-4 | 3.005e-8 / −3.644e-8 | 1.415e-4 / 8.239e-4 | −1.970e-7 / 2.822e-7 |
| 11 | 1e-7 | −7.194e-4 / −2.387e-4 | 1.549e-8 / 6.573e-9 | −4.896e-4 / −8.573e-5 | −1.634e-7 / 5.696e-8 |
| 2026 | 1e-8 | −2.121e-5 / 3.143e-4 | 3.413e-8 / −1.123e-7 | −4.814e-5 / 1.004e-3 | −2.539e-7 / 7.246e-7 |
| 2026 | 1e-7 | 3.910e-5 / 1.261e-4 | 2.294e-9 / −9.301e-8 | 3.099e-4 / −1.721e-4 | −3.666e-7 / 4.391e-7 |

The largest `NO_SIGN / UPSTREAM` ratio for the main absolute departures was
`1.10×10⁻³` for drag and `1.67×10⁻³` for downforce. For the paired odd/even
responses, the largest ratio was `9.2441×10⁻³` (seed 11, `ε=1e-8 m`, drag
odd), about a 108-fold reduction; the upstream odd denominator in this case
is relatively small (`3.2506×10⁻⁶ N`), and the no-sign residual is
`3.0049×10⁻⁸ N`. The weakest downforce odd ratio was `5.2747×10⁻³`
(seed 2026, `ε=1e-8 m`), about a 190-fold reduction.

The range of B/A magnitude ratios over all six perturbation pairs is:

| Response | `|Δ+|` | `|Δ−|` | `|odd|` | `|even|` |
|---|---:|---:|---:|---:|
| Drag | 2.029e-5–6.493e-4 | 1.855e-5–1.096e-3 | 2.153e-5–9.244e-3 | 3.225e-8–7.377e-4 |
| Downforce | 8.824e-5–1.557e-3 | 7.365e-5–1.672e-3 | 3.336e-4–5.275e-3 | 2.480e-4–2.552e-3 |
| Pressure Fx | 5.405e-7–7.971e-4 | 4.412e-5–3.463e-4 | 4.858e-5–1.980e-3 | 4.884e-6–3.369e-4 |
| Pressure Fz | 8.750e-5–6.768e-4 | 8.159e-5–1.176e-3 | 2.026e-4–7.508e-3 | 1.342e-4–1.969e-3 |
| Viscous Fx | 3.906e-6–7.178e-4 | 9.277e-6–4.086e-3 | 1.033e-5–4.051e-4 | 8.369e-6–1.836e-4 |
| Viscous Fz | 2.325e-6–2.018e-4 | 9.809e-7–7.741e-4 | 4.455e-6–1.373e-4 | 2.071e-7–1.067e-4 |

All plus/minus departures and the pressure/viscous splits in N are preserved
in [`force_response_long.csv`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/force_response_long.csv).
Independent integration of all 26 raw histories matched the summary within
`1.11×10⁻¹⁶ N`. The largest per-sample pressure/viscous closure error was
`6.32×10⁻¹⁷ N`; all raw-history hashes matched.

## Baseline and intervention integrity

| Window-mean response | UPSTREAM (N) | NO_SIGN_CORRECTION (N) | NO_SIGN − UPSTREAM (N) |
|---|---:|---:|---:|
| Drag | 0.334373766684780 | 0.334370108728456 | −3.657956324e-6 |
| Downforce | 0.345760171297919 | 0.345757242854030 | −2.928443889e-6 |
| Pressure Fx | 0.232500689959924 | 0.232496429653406 | −4.260306517e-6 |
| Pressure Fz | −0.353510554007058 | −0.353508575519592 | 1.978487466e-6 |
| Viscous Fx | 0.101873076724856 | 0.101873679075049 | 6.023501929e-7 |
| Viscous Fz | 0.007750382709139 | 0.007751332665562 | 9.499564237e-7 |

The A/B baseline force is not byte-identical because the intervention changes
the sampled `μ₀` coefficient at one face. Geometry bytes, center/face map
inputs, normals, velocities, flow setup, and the moving-ground inputs are
otherwise held fixed and hash-checked. The diagnostic `UPSTREAM` initialization
matches the pinned native baseline exactly; the ground-only native and
no-correction arrays also match exactly. Thus the measured baseline shift is
the intended operator intervention, not an accidental moving-ground or map
change. Its drag/downforce relative size is `−0.001094%` / `−0.000847%`.

## Evidence, validation, and limits

Machine-readable result: [`summary.json`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/summary.json).
Raw input, initialization, and force-history hashes are recorded there and
in `input_files.sha256`; the complete diagnostic source manifest is
`repository_sources.sha256`. The fixed-face source CSV SHA-256 is
`ddc3e5ed8470c7c247cc616b686f078a9ce2ab91414b91ba0eb73d7ac2ce7519`.
The post-run file inventory is bound by
[`artifact_manifest.sha256`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/artifact_manifest.sha256):

| Artifact | SHA-256 |
|---|---|
| Preregistered `plan.json` | `790a50aaa5eee8342c8f09ade54db808fd4992dcdfeaee6c6d48969f6f153478` |
| Pinned WaterLily `Body.jl` | `aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee` |
| `summary.json` | `0c9783a57a05c68c08370102404a991e8b5d8fa2ef4e5a91e64e45a347086a83` |
| `force_response_long.csv` | `49e3537ffc8477b6301c6525b1e6080a996e17648e92b9da1c5138acff53c1cf` |
| `initialization_comparison.csv` | `2bbc6b6fb3218d19703909c42369a982fd259c572dddc5a2b54d977d55ac7beb` |
| `software_validation.json` | `377ad4ee1f3ebddf70b7e4fca91acd65f793bfc64f2418eb79d619859e7e44d0` |
| `artifact_manifest.sha256` | `098676a51eb4fcb6e6ca996074adfd07211cd14d524535ff9dfa931e91c1086f` |

Validation: the four focused diagnostic tests passed; `compileall` passed;
Julia parsing and solver-free preflight passed; all 26 CPU solves completed;
independent force integration/closure passed. The full suite reports 1225
passed, 37 failed, and 4 skipped. The 37 failing test IDs exactly match the
previous registered full-suite baseline (zero new failures). The failures are
preserved rather than relabeled as a green full suite. See
[`software_validation.json`](../evidence/sdf_native_fd07_sign_consistency_causal_2026_10/software_validation.json)
for commands, counts, and failure-ID identity.

This evidence is a one-fixture, short-horizon causal diagnostic. There is one
baseline per arm, so baseline repeat noise is not estimated. The `NO_SIGN`
operator is deliberately different and has residual perturbation responses;
these results do not establish derivative proportionality. Thin-body
behavior, conservation, long-horizon response, formal FD gates, grid
independence, target physics, and any production replacement remain
unqualified. No v18, optimizer, gradient backend, production patch, or formal
FD round was performed.
