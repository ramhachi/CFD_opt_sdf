# Campaign harness (`harness v1`)

One parameterised harness for the WaterLily T4 campaigns (HARNESS-01, #58). It replaces the per-campaign copies of the runner template, kernel builder, freeze script and the integrity half of the analyzer (about 20 post-run defects in earlier campaigns came from those copies: C- vs Fortran-order SHA expectations, schema mismatches, missing imports, Kaggle slug collisions, timeouts, formula bugs).
v1 scope: WaterLily on a Kaggle T4 only. No in-kernel optimizer, no scheduler, no OpenFOAM profile. Capability evidence only; it measures nothing and qualifies nothing.

| Piece | File |
| --- | --- |
| schema: every name, shape and integrity check (shared by runner, tools and verifier) | `src/cfd_harness/campaign_schema.py` |
| runner template (rendered to `infra/kaggle/kernel_<campaign>_<k>/runner.py`) | `src/cfd_harness/campaign_runner_template.py` |
| build / smoke / freeze | `src/cfd_harness/campaign_build.py` |
| verifier | `src/cfd_harness/campaign_verify.py` |
| CLI | `scripts/harness.py` |
| replay campaign (GRID-02, verification only: its Kaggle slugs already exist) | `docs/harness/replay_grid02_campaign.json` |

## The four commands

```
scripts/harness.py build  CAMPAIGN_JSON --source-commit X   # render the kernel dirs (title == slug); refuses to overwrite
scripts/harness.py smoke  CAMPAIGN_JSON --source-commit X   # the SAME runner under a -smoke slug, first state, cheapest case; prints the kaggle push command; never pushes
scripts/harness.py freeze CAMPAIGN_JSON --source-commit X   # paginated identity-free check, clean tracked tree, commit on a remote head, pins -> <campaign>.prerun_freeze.json; refuses to overwrite
scripts/harness.py verify KERNEL_DIR... --campaign CAMPAIGN_JSON --freeze FREEZE [--out TABLE.json]   # integrity -> validated state-force table
```

`X` is a full commit SHA that is already pushed (the Kaggle runner fetches it from GitHub) and contains every bound file, including the campaign and the template, byte for byte. The rendered `runner.py`/`kernel-metadata.json` need not be in X; `freeze` requires the rendered files to equal a fresh render at X.

## Smoke before formal (rule)

No formal kernel is pushed before a smoke kernel of the same campaign has run and `verify --smoke` has passed on its output. `smoke` renders the formal runner of the cheapest kernel with only `KERNEL_ID` (`-smoke` suffix) and `SMOKE = True` changed inside the PIN block and asserts nothing else differs (it fails otherwise). A smoke runs the full path: sparse checkout, pin check, stage-0 self-test, Julia install, instantiate, CUDA probe, the first state, index/manifest/DONE. It does not exercise the other kernels' jobs; a kernel with a different job is smoke-tested with `--kernel K`. `verify --smoke KERNEL_DIR --campaign CAMPAIGN_JSON` (no freeze) checks a smoke output with the formal checks on the first state.

## What the runner does (equal to the proven GRID-02 runner for the same inputs)

GPU inventory (Tesla T4 only, physical index 0) -> sparse checkout of the pinned commit and pin verification of every bound file -> **stage-0 self-test** (imports, campaign validation, a schema dry write through the runner's own writers, a planted-truth force recomputation, regeneration and identity check of every state's phi in both byte orders) -> Julia install (pinned SHA) -> `Pkg.instantiate` -> JSON3-free CUDA probe (singleton, UUID equals the selected GPU) -> per state: job with per-state/aggregate/kernel budgets -> index + `output_manifest.json`; `DONE` xor `ERROR.txt`. Optional first-state byte gate against a pinned historical force CSV. Differences from the grid02 runner: the self-test runs before any Julia work (a phi mismatch now stops with zero jobs instead of at that state), `self_test.json` and `harness_version`/`campaign_sha256`/`smoke` identity fields are added.

## campaign.json

All keys are required unless marked optional; `SC.validate_campaign` (in `campaign_schema.py`) is the authority.

```
harness_version   "harness v1"
campaign_id       [a-z0-9_]+ ; kernel dirs are infra/kaggle/kernel_<campaign_id>_<k>[_smoke]
owner, repo_url   Kaggle owner; GitHub URL the runner fetches
index_name        e.g. "harness_index.json" ; out_prefix e.g. "<campaign_id>_" (output dir = out_prefix + kernel)
job_env_common    W4_* environment of every job (needs W4_CANONICAL_DESIGN_SPACING_M, _STATE_LABEL, W4_POINT_SHAPE, W4_CELL_SHAPE, W4_SOURCE_SURFACE_SHA256, W4_MARGIN_GATE_M)
scrub_env         inherited variables removed before a job env is built (e.g. ["GRID02_CASE"])
measurement       {candidate_operator, time_window_t_u_l: [start, end]}
domain            {flow_origin_m, physical_box_max_m}
baseline          {path, sha256_fortran_raw}            the Fortran-order float32 raw phi every state derives from
directions        {name: {path, sha256_fortran_raw}}    direction raws (max-norm 1)
states            {name: {kind, direction, step_mm, sign, state_sha256, npz_sha256, phi_fortran_order_sha256, phi_c_order_sha256,
                          zero_level_margin_m, margin_tolerance_m, changed_node_count, maximum_pointwise_change_m}}
                  direction null (step 0, sign 0) = the baseline phi itself; otherwise phi = float32(float64(baseline) + sign*step_mm/1000*direction)
                  (scripts/step01_states.perturb) and must reproduce every identity field. phi_fortran = SHA of the Fortran-order bytes
                  (equals the job summary's device_roundtrip_sha256), phi_c = SHA of the C-order bytes: two different fields.
kernels           {k: {kernel_id "<owner>/<slug>", job "scripts/....jl",
                       case {case_id, flow_dims, flow_spacing_m, solver_length, solver_time_unit_s, solver_viscosity, reynolds, density_kg_m3,
                             dynamic_viscosity_pa_s, reference_length_m, reference_area_m2, freestream_mps},
                       config {per_state_timeout_s, solver_wall_time_cap_s, kernel_timeout_s, instantiate_timeout_s, gpu_probe_timeout_s, reserve_s, ...extras echoed into run_identity.config},
                       runs [{state, env}]   ordered; the first state must be a baseline state; env = per-state job overrides
                                             (W4_CANONICAL_ORIGIN_M is required here or in job_env_common; GRID02_CASE where the job reads it),
                       pins (optional)       extra pinned repo paths, first_state_csv_sha256 (optional)}}
sparse, pins      extra sparse-checkout paths / extra pinned repo paths (files or directories)
```

Budget rule enforced at validation: `solver_wall_time_cap_s + reserve_s + instantiate_timeout_s + gpu_probe_timeout_s <= kernel_timeout_s` and `per_state_timeout_s <= solver_wall_time_cap_s` (and `kernel_timeout_s` must equal `kaggle kernels push --timeout`; `smoke` prints it).
Pinned automatically: Julia project files, `julia/CFDSDFWaterLily/src`, `scripts/step01_states.py`, `scripts/grid01_gpu.py`, `scripts/fd08_v2_campaign_io.py`, the schema, the campaign, baseline and direction raws (checked against the declared hashes at build time), each kernel's job.

## verify and the analyzers

`verify` is the integrity half of an analyzer: manifest safe paths and hashes, DONE xor ERROR, exact state order, schema, run identity and pins against the freeze, GPU, per-state job-summary identity (both phi byte orders, grid, origin per state, margin, window), host recomputation of drag/downforce with the case's force scale against the Julia summary at 1e-9, budgets, first-state gate. It prints/writes the **state-force table** (`kind: harness_state_force_table`, `state_forces_n[kernel][state] = {drag_n, downforce_n, forces_csv_sha256, summary_sha256, solver_process_wall_seconds, julia_summary_wall_seconds}`) or fails closed (exit 3, nothing written). A campaign analyzer is then a small statistics function over that table.

Replay equivalence: `tests/test_harness_replay.py` verifies the five saved GRID-02 outputs through the replay campaign and checks the table equals `state_forces_n` of `docs/evidence/grid02_trend_2026_10_16/grid02_analysis.json` bit for bit.

Not verifiable offline: the Kaggle side (real Julia/CUDA, the `kaggle` CLI, provider listing). Tests use a fake job, a scratch git remote and a fake `kaggle`.
