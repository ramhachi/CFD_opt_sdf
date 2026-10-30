# LOWDIM-03 Amendment 1 result record

## Decision and scope

Formal registered analyzer verdict: **LOWDIM03_ACCEPT** for the bounded two-grid, fixed-direction actual-primal trial. The selected common positive step is **1.25 mm** under the frozen rule: maximize the minimum actual downforce gain across the two grids; exact ties choose the smaller step. All three registered positive steps passed the registered per-grid conditions and hard geometry gates; 1.25 mm had the largest minimum-grid computed downforce gain.

This result is scoped to the registered direction, three-step ladder, two grids, and saved 14-run matrix. It is not a physical downforce claim, a noise-resolved drag claim, grid convergence, gradient/optimizer qualification, or a qualification of the vehicle. `selected_delta` remains null; all six qualification flags remain false; `shape_update_allowed=false`; reinitialization remains `none`.

Attempt 1 remains an integrity-failed analysis attempt. Amendment 1 does not retroactively convert Attempt 1 into a passing run. It authorizes a fresh analysis of the immutable retained measurement outputs after correcting an analyzer-only byte-order identity expectation.

## Lineage and frozen change

- Measurement source commit: `e5386910d8b77decd748fdbd5efaee002803d86c`.
- Original prerun freeze SHA-256: `6009d6b02bd674f78c398b525d6d0319693f12febbb34efae952cb506862b069`.
- Original inventory SHA-256: `e42cf5e8dd05e58ddc0598b8bdab93b4dba3a6740471c0d2ec701492625f8cd3`.
- Original runner SHA-256 values: flow_24 `b7d2566c3c0e9db52e51fe037e78035c73b08db6ddb4cea764a4b37131855230`; flow_32 `51ad636d7031d929d31ef991001ff573161ca7f5af757adb6f2a767d32ea7499`.
- Failed Attempt 1 commit: `3908c95c068c2c086d86e73673ada104c05b22cc`; its 76-entry `SHA256SUMS` manifest SHA-256 is `3ebf4c41b450183e642345118b4407874a3f2d6d6303805b5b24c09c97ebcd96`.
- Amendment source commit: `b88ea35b6cecf1252afaf873e43153ee58b6e6d9`.
- Amendment analysis freeze SHA-256: `c8b17f6666b66274784a40e825ce17d58c2224e9cc165d6af5abd9e083c7e893`.
- Amended analyzer SHA-256: `06ac375bcff616226e67dfe4a50642bad96b327d72c1b3f535d3fc5994188a2a`.
- Authorized semantic correction: `summary.device_roundtrip_sha256` is checked against `phi_fortran_order_sha256`, not `phi_c_order_sha256`. Julia `vec(phi)` is column-major and both registered jobs compare the device round-trip hash to `EXPECTED_PHI_FORTRAN_SHA256` before writing summaries.
- Only the analyzer and its synthetic analyzer test changed in the source amendment. Acceptance rules, solver, jobs, runner, inventory, original freeze, geometry inputs, candidate set, step rules, trust/model diagnostic definitions, and qualification flags were not changed.
- Measurement/CFD reruns: **0**. Kaggle kernel resubmissions: **0**. Amendment `--write` executions: **1**.

### Result visibility disclosure

Before the Amendment 1 freeze, the independent reviewer accidentally surfaced a saved summary JSON excerpt containing per-state mean/time-weighted drag and downforce fields and force-CSV SHA-256 values. The reviewer reports not interpreting or comparing those fields; the excerpt did not show a trial delta, selected step, verdict, rho/model diagnostics, or acceptance result. The primary analysis agent did not analyze result values before the freeze. **Full result blindness is not claimed.** The disclosure is also recorded in `analysis_freeze.json` and `independent_review.md`.

## Analysis sequence and artifacts

- Independent static review: no blocking code defect; review record at `independent_review.md`. The reviewer noted no dedicated unit test for the new freeze validator. The committed `--check` exercised that validator before force-result parsing.
- Focused tests: `63 passed` for `tests/test_lowdim03_contract.py`, `tests/test_lowdim03_analyzer.py`, and `tests/test_lowdim03_prereg.py`.
- `compileall src scripts tests`: passed. `git diff --check`: passed.
- Full pytest before amendment: `2176 passed, 37 failed, 23 skipped`. After amendment: `2177 passed, 37 failed, 23 skipped`; all 37 failure IDs were unchanged, so **new failures = 0**. The failures concern ignored historical `work/` artifacts absent from this worktree.
- `--check`: run once after the amendment freeze was committed; exit code 0, `integrity.pass=true`, zero failures. Exact output: `analysis_check_output.json`.
- `--write`: run once after the passing check, against the same freeze and original saved `failed_attempt1/kernel_output/lowdim03_a` and `lowdim03_b` paths. The resulting report SHA-256 is `8615474dee771d37ad4c853c9efc276878423adbd02b154c7e3cb4604e24c54a`; report: `lowdim03_analysis.json`.
- Attempt 1 outputs were not changed, normalized, copied, or regenerated. The analyzer reverified all 76 entries from the original manifest during `--check` and `--write`.

## Registered actual changes

All values below are computed force changes from the frozen analyzer report. Drag values are computed signs under the registered projection convention; they are not noise-resolved or physical claims.

| Positive step | flow_24 Δdownforce (N) | flow_24 Δdrag (N) | flow_32 Δdownforce (N) | flow_32 Δdrag (N) |
|---:|---:|---:|---:|---:|
| 0.625 | +1.405544900e-04 | -4.893992711e-05 | +2.010550354e-04 | -3.607524616e-05 |
| 1.25 | +2.092162269e-04 | -1.300936093e-04 | +3.871987631e-04 | -6.305368200e-05 |
| 2.5 | +1.159194267e-04 | -3.886426378e-04 | +6.764761496e-04 | -2.023565284e-04 |

## Reverse-pair diagnostics

Reverse pairs are diagnostics only; `reverse_controls_eligible=false` and they do not enter acceptance or selection.

| Step | Grid | Reverse Δdownforce (N) | Reverse Δdrag (N) |
|---:|---|---:|---:|
| 0.625 | flow_24 | -2.225607274e-04 | +1.102960822e-05 |
| 0.625 | flow_32 | -2.900643706e-04 | -7.215561297e-05 |
| 1.25 | flow_24 | -5.100209113e-04 | +2.685372027e-06 |
| 1.25 | flow_32 | -5.491262946e-04 | -6.857765906e-05 |
| 2.5 | flow_24 | -1.306033023e-03 | -1.133325041e-04 |
| 2.5 | flow_32 | -1.183324798e-03 | -1.581458745e-04 |

## Forward model prediction versus actual diagnostics

The raw finite-step predictions, L1-sensitivity lower/upper predictions, prediction errors, and downforce rho values below are descriptive diagnostics only. Rho is not an acceptance gate. The flow_32 drag prediction at 1.25 mm is within the registered ±3e-5 N small-drag margin, so its computed drag sign is not expected to be noise-resolved.

| Step | Grid | Response | Actual Δ (N) | Raw prediction (N) | L1 bound (N) | Prediction error (N) | ρ (downforce only) |
|---:|---|---|---:|---:|---:|---:|---:|
| 0.625 | flow_24 | downforce | +1.405544900e-04 | +1.765972872e-04 | +1.721497982e-04 | -3.604279719e-05 | 0.795904 |
| 0.625 | flow_24 | drag | -4.893992711e-05 | -3.519339707e-05 | -3.074590808e-05 | -1.374653004e-05 | — |
| 0.625 | flow_32 | downforce | +2.010550354e-04 | +2.342993543e-04 | +2.298518653e-04 | -3.324431893e-05 | 0.858112 |
| 0.625 | flow_32 | drag | -3.607524616e-05 | -4.447488998e-06 | -2.356637170e-20 | -3.162775716e-05 | — |
| 1.25 | flow_24 | downforce | +2.092162269e-04 | +3.531945745e-04 | +3.442995965e-04 | -1.439783475e-04 | 0.592354 |
| 1.25 | flow_24 | drag | -1.300936093e-04 | -7.038679415e-05 | -6.149181615e-05 | -5.970681511e-05 | — |
| 1.25 | flow_32 | downforce | +3.871987631e-04 | +4.685987086e-04 | +4.597037306e-04 | -8.139994545e-05 | 0.826291 |
| 1.25 | flow_32 | drag | -6.305368200e-05 | -8.894977996e-06 | -4.713274340e-20 | -5.415870400e-05 | — |
| 2.5 | flow_24 | downforce | +1.159194267e-04 | +7.063891489e-04 | +6.885991929e-04 | -5.904697222e-04 | 0.164101 |
| 2.5 | flow_24 | drag | -3.886426378e-04 | -1.407735883e-04 | -1.229836323e-04 | -2.478690495e-04 | — |
| 2.5 | flow_32 | downforce | +6.764761496e-04 | +9.371974172e-04 | +9.194074612e-04 | -2.607212676e-04 | 0.721808 |
| 2.5 | flow_32 | drag | -2.023565284e-04 | -1.778995599e-05 | -9.426548680e-20 | -1.845665724e-04 | — |

## Stop boundary

No next optimization iteration, secant rebuild, basis expansion, curvature model, reinitialization, GEOM-01 modification, Stage B work, #30 supersession, or new CFD run was started. LOWDIM-03 is recorded and stopped for user direction.

## Hash manifest

`SHA256SUMS` binds the Amendment 1 review, freeze and sidecar, `--check` output, final analysis, and this note. The original 76-entry Attempt 1 manifest remains separately preserved and unchanged.
