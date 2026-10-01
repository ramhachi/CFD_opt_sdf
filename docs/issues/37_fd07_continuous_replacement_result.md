# FD-07 continuous sign-consistency candidates — result (2026-10-02)

## Decision

**Candidate C, one-sided moment-level regularization, is the most promising
bounded diagnostic candidate.** It is selected for possible future study only.
It is not adopted into production, does not establish a formal finite
difference, and does not authorize gradient, optimizer, Kaggle, v18, or W3/W4
requalification work.

The scope is the registered v17 / `flow_24` / `normal_floor=0.25` Float32 CPU
fixture. The plan SHA-256 is
`5da4f0f9f82fd59215e0c642f0c14644ba47335e542007b482e0b6d19a0a87c9`; its
repository-source manifest is
`a9afd938b7762260dad04335944126455ffbbf41da6ebcbe61798e68e82ab063`, and the
13-case input manifest is
`285b14b36a7ee1b940d85b3959ce775f62628dde5c389982ada06aff428a978a`. The
experiment began at `ecaa1572734596130ffefdd0d7b0ab3c2af67c15` on
`exp/issue-37-continuous-sign-consistency`. WaterLily was 1.8.0; pinned
`Body.jl` SHA-256 was
`aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee`.

The first registered attempt completed the upstream baseline flow but stopped
in its recorder before saving the remaining run status. Its plan, partial raw
history, Julia scope error, and byte-verified snapshot of all 19 registered
sources are preserved under
[`attempt 1 evidence`](../evidence/sdf_native_fd07_continuous_replacement_2026_10/).
The successful attempt 2 has a new plan and source hash; it reran the geometry,
coefficient, and full force matrices without overwriting attempt 1.

## Semantics and candidate screen

The pinned WaterLily branch preserves a sampled face sign when
`|dᵢ|≤0.5` solver cells, where a real center-to-face interface crossing can
occur, and imposes center-sign consistency beyond that half-cell distance.
The corrected distance feeds `μ₀` and `μ₁`; changing only its sign changes
`μ₀`, while pinned `μ₁` is even in distance. The upstream history records this
geometric rationale in [commit 3273a26](https://github.com/WaterLily-jl/WaterLily.jl/commit/3273a26160708010320a974a678da442ea4650c0),
without proving universal accuracy. The candidate equations and fixed
parameters are in the [pre-registered design](37_fd07_continuous_replacement_design.md).

The transition width was fixed at
`δ=1.1444091796875e-4` solver cells (`3.814697265625e-6 m`), derived as eight
times the largest previously recorded Float32 node displacement at `1e-7 m`.
No width was adjusted after seeing force data.

| Operator | Solver-free and geometry result | Disposition |
|---|---|---|
| A — smooth the half-cell threshold, retain hard center sign | The center-sign sweep still has an adjacent `μ₀` change of `0.72145`; 987 baseline faces change by more than `1e-3` versus upstream. It changes all 49 legal half-cell crossings in the near-center plane fixture, changes the analytic plate moments (maximum `0.40915`), and fails bitwise moving-ground identity. | Reject: not continuous in center sign and changes permitted thin-body/ground samples. |
| B — smooth center-sign distance blend | Center-sign sweep is continuous in the sampled sweep and coefficient response scales by about 10×. However, it changes all 49 legal crossings, changes the analytic plate moments (maximum `0.17162`), and fails moving-ground identity. It changes 1,421 baseline faces by more than `1e-3` versus upstream. | Reject: continuity does not preserve the registered half-cell semantics. |
| C — blend only `μ₀` on the sign-disagreement side | All seven exact analytic fixtures match upstream `μ₀`/`μ₁`; all 49 legal crossings and one-/two-cell plate samples are unchanged; reflection residuals remain below `2.3e-8`; moving-ground initialization is bitwise identical. The center-sign and face-threshold sweeps are monotone, with maximum adjacent `μ₀` changes `0.00536` and `0.01087`, respectively. No perturbed coefficient has `|Δμ₀|` or `|Δμ₁|>1e-3`; largest own-baseline changes are `9.30e-6` for `μ₀` and `1.055e-5` for `μ₁`. | Retain as the single most promising bounded candidate. |

The 13-input coefficient matrix contains 65 initializations and 30 paired
coefficient-response rows. `UPSTREAM` reproduces native initialization
exactly; all five modes have zero non-finite coefficients. Candidate C still
has an important baseline difference: one design-body face at Julia index
`(64,39,21)`, axis 2, world location
`(-0.416667, 0.033333, -0.250000) m`, has center distance
`-7.4974e-8` and face distance `+0.5000007` solver cells. There `μ₀` is
`0.9091553` for C versus `0.0908447` upstream (`|Δμ₀|=0.8183106`). Its
baseline force shift is small, but that does not make the coefficient
semantics identical.

The exact `μ₀≠1` support predicate differs at 95 entries for C's baseline
versus upstream and at most 381 entries in a paired input. This is retained as
a support-mask difference in the evidence; it is not folded into the
`|Δμ₀|>1e-3` count. The largest paired changes from candidate C's own
baseline are `9.30e-6` for `μ₀` and `1.055e-5` for `μ₁`. These counts are
specific to this array and fixture.

## Short CPU force comparison

Only C survived the registered semantic screen. Stage 3 therefore ran the
fixed controls `UPSTREAM` and `NO_SIGN_CORRECTION` plus C: 13 runs per mode,
39 total. All reached `tU/L=3.0123–3.0135`; each raw history has 29 force
samples. The independent integrator used the exact `[2,3]` window with
endpoint interpolation and trapezoids, then converted by `1/900 N` per
solver-force unit.

| Quantity | Largest `|+/- departure|` upstream (N) | Candidate C (N) | C / upstream |
|---|---:|---:|---:|
| Drag | `1.3168e-3` | `1.4646e-7` | `1.11e-4` |
| Downforce | `1.0522e-3` | `9.7855e-7` | `9.30e-4` |
| Pressure Fx | `5.6490e-4` | `1.5011e-7` | `2.66e-4` |
| Pressure Fz | `1.4247e-3` | `9.8031e-7` | `6.88e-4` |
| Viscous Fx | `9.6434e-4` | `2.1378e-8` | `2.22e-5` |
| Viscous Fz | `1.0037e-3` | `2.0650e-8` | `2.06e-5` |

Across all 72 signed departures (six force quantities, six seed/amplitude
pairs, and both signs), C's magnitude is lower than upstream. The no-sign
control is similarly quiet but fails to retain upstream correction semantics;
C is preferable because it also passes the exact geometry, thin-body, and
moving-ground checks.

The baseline window means are `0.334370109 N` drag and `0.345757243 N`
downforce for C, versus `0.334373767 N` and `0.345760171 N` upstream. Thus C's
baseline shifts are `-3.6580e-6 N` and `-2.9284e-6 N`, respectively. The
force-level 10× amplitude ratio for total-force odd/even terms ranges from
`0.265` to `3.08`, so the force response does not show 10× scaling. The short
window is useful for screening the discontinuity reduction; it does not
establish a derivative or a formal FD oracle.

Independent pressure/viscous closure is within `6.32e-17 N` per sample and
`5.56e-17 N` after window integration. No formal pass threshold was applied.

## Evidence and validation

The machine-readable result and raw artifacts are under
[`attempt 2 evidence`](../evidence/sdf_native_fd07_continuous_replacement_attempt02_2026_10/summary.json).
Key records are `plan.json`, `repository_sources.sha256`, `input_files.sha256`,
`analytic_fixture_coefficients.csv`, `analytic_reflection_symmetry.csv`,
`coefficient_metrics.csv`, `sensitive_faces.csv`, `stage3_progress.csv`,
`force_response_long.csv`, `force_pair_response.csv`, and
`artifact_manifest.sha256`. `execution_record.json` records commands, run
counts, and hashes.

The final `summary.json` SHA-256 is
`17713f5461aeeef1b3939c72488ca3ffd8566cc10f06595a0a03e946e502e551`; the
63-entry `artifact_manifest.sha256` file has SHA-256
`b421a2146acf508253d16da12f7a74dac4e8120475c641cd0b902ceadfde3e3d` and all
63 listed artifact hashes were verified.

Validation completed: focused test `1 passed`; Python `compileall` passed;
Julia parsed all three diagnostic scripts and the analytic operator self-test
passed. The full suite reported `1226 passed, 37 failed, 4 skipped`; the 37
failure IDs exactly match the prior registered baseline, with zero new or
resolved failures. The original full-suite output is preserved byte-for-byte as `full_pytest_raw.txt.gz` (decompressed SHA-256 matches the captured log); `full_pytest.txt` is the LF-normalized, trailing-space-trimmed reading copy. CSV line-ending normalization changed no parsed data. The failure-ID list and comparison are preserved in the evidence directory.

Stop here. Candidate C is not a production patch. Formal FD, conservation,
gradient qualification, long-horizon flow, grid/physical qualification,
W3/W4 requalification, Kaggle execution, v18, and optimization remain outside
this result and require a separate gate.
