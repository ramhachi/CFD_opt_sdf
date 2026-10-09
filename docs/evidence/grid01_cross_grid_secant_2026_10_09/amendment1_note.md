# GRID-01 (#26) Amendment 1: CUDA device-probe code (infrastructure only, before any flow_32 measurement)

## What happened
The first and only T4 submission (`ramhachi888/cfd-opt-sdf-grid01-a` version 1, source `c3f53df1`, freeze `f18201ee…`, 2026-10-09 13:22 UTC) stopped in the runner's independent CUDA device probe, after Julia install and `Pkg.instantiate()` and **before any state was run**: the probe snippet did `using CUDA, JSON3`, and `JSON3` is not a dependency of `julia/CFDSDFWaterLilyT4` (`Package JSON3 not found`). The runner failed closed (`ERROR.txt`, no `DONE`, stage `observed_cuda_device_probe`). The worker exposed two Tesla T4s (index 0 and 1); the registered policy selects physical index 0. Raw records: `failed_attempt1/` (hash list in `failed_attempt1/SHA256SUMS`).

No flow_32 force, summary or any other measurement was produced or observed: flow_32 responses observed = 0. The failure is independent of any result.

## The only change
`scripts/grid01_runner_template.py::GPU_PROBE_CODE` now writes the same JSON record with Julia Base string functions only (`using CUDA` is the single `using`; quote/backslash in a value is asserted absent). The record keys/values the runner compares (`logical_device_count`, `visible_gpu_names`, `visible_gpu_uuids`, `default_device_uuid`, `cuda_device_order`, `cuda_visible_devices`) are unchanged, and so are the runner's comparison, the states, the job, the baseline gate, the budgets, the thresholds, the measurement and proposal contracts, the inventory and every pin. `tests/test_grid01_followup.py` gained one regression test that runs the probe against a CUDA stub in a local Julia and checks the JSON against the runner's expectation (and that neither the T4 project nor the probe uses JSON3).
`scripts/build_grid01_freeze.py` gained `--amendment 1` (writes `prerun_freeze_amend1.json`; the original `prerun_freeze.json` is kept unchanged as history and no longer validates against the amended source files; the analysis uses the amendment freeze).

## Process
A new source commit contains the fix; the runner is re-rendered for it; the amendment freeze is written with the unchanged builder logic (same identity-free record, still inside its 24 h window); the same slug is pushed as kernel version 2 (the slug now exists because of the failed attempt; the identity-free record stays valid as the pre-creation record of the registration). One independent read-only review covers the amendment diff. The nine-state design, thresholds and proposal formulation were not touched.
