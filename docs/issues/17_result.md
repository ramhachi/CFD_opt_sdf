# #17 INFRA-01 preflight completion

## Evidence

The local preview CLI now accepts explicit criteria, dataset, source checkout, Julia executable, and append-only output directory. It validates the attached immutable criteria and dataset inventory, registered prerequisites, canonical state and direction inputs, all 33 ordered queue rows and their input hashes, Kaggle kernel/dataset binding, and the Python verifier versus Julia summary-field contract. It instantiates a scratch copy of the pinned Julia project so the checkout's Project/Manifest remain unchanged, then runs the registered CPU-prestep job with `Array` storage.

Exact execution:

```text
python3 scripts/preflight_kaggle_sdf_directional_fd_v16_cpu.py --criteria docs/evidence/sdf_directional_fd_v17_flow24_normalfloor_criteria_2026_09.json --dataset /Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/work/kaggle_sdf_directional_fd_v17_nfloor_remote_v1_2026_09 --source-root . --preview-current-source --julia /opt/homebrew/bin/julia --output-dir work/infra01_preflight/normalfloor_preview_run3
```

Observed output: `prestep_passed=true`, 33 queue rows checked, `solver_step_invoked=false`, Julia 1.12.6. The job emitted `FD_PRESTEP_IDENTITY baseline_A`, `FD_PRESTEP_READY baseline_A`, and `FD_PRESTEP_COMPLETE runs_validated=33 next=sim_step!`; it emitted neither solver-step marker. Its identity line included `flow=flow_24`, the canonical state/phi hashes, `normal_floor=0.25`, and `body=NormalFloorWaterLilyBody`. The Julia output queue is byte-identical to the independently staged input queue.

The evidence is **local preview only**, not a formal registration or CFD/FD result. It uses immutable FD-06 criteria `sdf_directional_fd_v17_flow24_normalfloor_2026_09`, whose registration metadata remains `registered_not_run`. Current source SHA verification recorded two differences: the preflight wrapper being changed, and the untouched `docs/issues/37_fd06_normal_floor_probe.md` input (`expected 0a6d63eaf428746869fa25362cbe38b466c22c987f039bdfaf1a88521f6e2647`, observed `4cb1e2506569bf30518a6774c5cc5f274019e7e6f85d379d341e473bb3da53fa`). The preview therefore does not claim to reproduce the historical source checkout. The criteria file and sidecar were not modified. No solver step, force calculation, gradient qualification, or flag change occurred.

Artifacts under `work/infra01_preflight/normalfloor_preview_run3/`:

| Artifact | SHA-256 | Evidence class |
| --- | --- | --- |
| `preflight_evidence.json` | `7da0d5170f916052434e506cc282bf013fc3658a62bca524d12f1fa9df0888c9` | Local CPU setup boundary preview |
| `julia_job.log` | `ac2300497076fa9f3a6c7be18e0c085b2bd76ae64f3618ae5a33618970992cb2` | Julia setup log through pre-step boundary |
| `incoming_run_queue.tsv` and `job_output/run_queue.tsv` | `52e3d1ab1a078dbb471452fa4c2abd5c2ebd72aa17bb6d766341dd059bfc3797` | Validated input and exact Julia snapshot |
| `scratch_julia_project/Project.toml` | `5abca50d507cd809e6950ec654703cd1887977aab14ba5b864bcf066b4865e27` | Pinned scratch runtime input |
| `scratch_julia_project/Manifest.toml` | `65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c` | Pinned scratch runtime input |

The Julia scratch files match the registered Project/Manifest hashes. The output directory and job log persist after the temporary queue staging directory closes. The preflight also checks that the incoming queue cannot alias the Julia output snapshot and that all Python verifier summary keys are present in the Julia summary contract.

## Validation

Commands run:

```text
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_kaggle_fd_preflight.py
# 3 passed
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests
# passed
/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q
# initial dirty-tree run: 38 failed, 1227 passed, 5 skipped; one extra failure was the v17 prerequisite test because the worktree lacked its ignored canonical NPZ input and the working source was not yet committed
git diff --check
# pending final verification
```

The full-suite IDs were compared with the shared baseline `failure_ids.json` (SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`); the initial run had the 37 baseline failures plus that one missing-input/source-at-HEAD failure. The canonical state NPZ and matching Fortran raw fixture have since been copied into this worktree's ignored `work/sdf_native_genesis_v17/` for local validation. A post-commit focused recheck and any final full-suite comparison are recorded below after they run.

## Conclusion

The solver-free setup path reaches the real production Simulation initialization immediately before the first `sim_step!`, after validating the full 33-run queue. This closes the #17 execution-boundary capability check for the recorded local preview. It does not establish a Kaggle environment reproduction, solver result, FD oracle, or physical qualification.
