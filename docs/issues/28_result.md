# Issue #28 result: explicit SDF reinitialization

## Conclusion

The round3 method-specific operator-effect qualification is **FAIL** under its preregistered gates. This is a geometric/operator result for the registered analytic and canonical-v16 fields only. It is not an FD, solver, optimizer, shape-update, topology-policy, or aerodynamic qualification. No qualification flag was enabled.

The operator passed for the analytic sphere and two-sphere fixtures. It failed for the thin-box fixture and canonical v16. The unchanged acceptance thresholds were not relaxed after observing results.

## Registered method and round history

The method is sub-cell edge-crossing initialization followed by deterministic second-order Godunov Eikonal relaxation, with exact-zero preservation and exact far-band retention beyond the fixed `3h` update band. Reinitialization remains a post-accepted-update operator; it is excluded from the `phi -> response` finite-difference map.

- Round1 was rejected before measurement because its Eikonal sample set was defined from output `phi`, allowing the accepted points to vary after reinitialization. The immutable registration was left unchanged and not used for measurements.
- Round2 preregistered the input-defined Eikonal/interior mask and the same gates and cases. Its command aborted during construction of the registered `sphere_pair` fixture because the runner tried to read a single `center_m`; it produced no case metrics or output files. The raw pre-measurement traceback remains at `work/issue_28/qualification_round2_2026_10.stdout.log` (SHA-256 `ccd58b1f379959061aac4c973afdfcc790b55b8105cf051f2d531990b9f1c7d9`).
- Round3 contains the mechanical fixture-dispatch fix and regression test. It retains round2's evaluation semantics, the same four cases, canonical input, invariants, and numeric gates. No round1 or round2 measurements were reused.

Round3 criteria: `docs/evidence/sdf_native_reinitialization_godunov2_v2_round3_2026_10.json`, raw file SHA-256 `3f8716b39438e28a523ad2961596f7977e1df1fe0bbea4d1e28558f9d975aa25`; canonical criteria digest `be65faf79b4c76e2e5b30d45bf42982d9c5568bfc756df6b5aa82f2a71e86454`; method payload SHA-256 `9895ab008e880ea65b30bbf01ab2489c62ad655ee911f9f237e300a118cc4f98`. Its gates and fixture/canonical bindings compare exactly equal to rounds1 and 2. All source hashes and criteria sidecar verified before execution.

## Commands and evidence

The all-case preflight used the registered criteria, constructed all three analytic fixtures, loaded the canonical-v16 NPZ, and checked source hashes, exact canonical NPZ/state/phi identity, shape, finiteness, and strict solid/fluid interface presence for each analytic fixture. It passed before reinitialization was run.

Formal CPU command:

```text
env PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scripts/qualify_sdf_reinitialization.py --criteria docs/evidence/sdf_native_reinitialization_godunov2_v2_round3_2026_10.json --canonical-state work/issue_28/canonical_v16/sdf_design_state.npz --output-dir work/issue_28/qualification_round3_2026_10
```

It returned exit code 1 and verdict `FAIL`, with four cases. Tracked evidence is [round3 result JSON](../evidence/sdf_native_reinitialization_godunov2_v2_round3_result_2026_10.json), SHA-256 `ddb29fe605c146512467eeeaaa7bf979a372cef32e70870477127f576fd04ffe`. The raw stdout log at `work/issue_28/qualification_round3_2026_10.stdout.log` has SHA-256 `e759c48f9e476e4c8a277688f39683eccb252fc55a81e98d6c18390a0c6e963e`; preflight log `work/issue_28/qualification_round3_preflight.log` has SHA-256 `eaad54bd6d72199f108d9b7e29c9838de24f1aecd71dad46d066547015b34a6a`.

| Case | Result | Failed gates |
| --- | --- | --- |
| Analytic sphere | PASS | — |
| Analytic thin box | FAIL | Fluid Eikonal max `0.5768 > 0.50`; solid p50 `0.1885 > 0.05`, p95/max `0.82 > 0.25/0.50`; idempotence `0.2519h > 0.10h` |
| Analytic two spheres | PASS | — |
| Canonical v16 | FAIL | Smoothed-volume relative drift `0.32249 > 0.05`; common-edge zero-level displacement `0.50 > 0.25`; idempotence `0.64995h > 0.10h` |

The complete result lists every gate, the fixed Eikonal sample counts (input-band count 11,826 / 3,994 / 4,208 / 6,349 for sphere / thin box / two spheres / canonical v16), runtime, state hashes, and output artifact hashes. Generated NPZ outputs remain in ignored `work/issue_28/qualification_round3_2026_10/`; their hashes are bound in the tracked result JSON.

## Verification

Focused command:

```text
env PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_sdf_native_reinitialization.py
```

Result: `6 passed`.

Repository compile command:

```text
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests
```

Result: passed. The full-suite command was `env PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q --tb=short`; after restoring the ignored canonical-v17 state NPZ and Fortran-order field inputs, it produced `37 failed, 1243 passed, 5 skipped`. Its sorted failure IDs equal the registered 37-ID baseline exactly: zero new failures. The full log is `work/issue_28/qualification_round3_2026_10/full_pytest.log` (SHA-256 `961bcd8f54a636eb55833a3e8607cb476f15151300052534de6358aa5182286b`); the ID list is `work/issue_28/qualification_round3_2026_10/full_pytest_failure_ids.json` (SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`), equal to `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json`.

The first full-suite attempt, before the ignored canonical-v17 inputs were restored, had 38 failures and 1242 passes; the additional failure was `tests/test_kaggle_sdf_directional_fd_v16.py::test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity`, caused by missing `work/sdf_native_genesis_v17/sdf_design_state.npz`. That run's raw log path was overwritten by the corrected full-suite rerun. The counts and missing-file traceback survive in the command output, but there is no preserved raw log for that first run.

`git diff --check` passed after the source/criteria edits.

## Evidence scope and artifacts

Evidence class: CPU-only geometric operator-effect qualification on three registered analytic fields and one canonical-v16 state. No CFD solver, GPU, finite-difference response, optimizer update, or physical force calculation was run. All six qualification flags remained false.

The four output NPZ hashes are recorded in the result JSON and the corresponding files remain in the ignored work output directory. The canonical input NPZ SHA-256 is `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`; its registered state and phi hashes were verified before the run.
