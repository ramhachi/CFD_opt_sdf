# Campaign harness (`harness v1.1`)

One parameterised harness for the WaterLily T4 campaigns (HARNESS-01, #58). It replaces the per-campaign copies of the runner template, kernel builder, freeze script and the integrity half of the analyzer (about 20 post-run defects in earlier campaigns came from those copies: C- vs Fortran-order SHA expectations, schema mismatches, missing imports, Kaggle slug collisions, timeouts, formula bugs).
v1.1 scope: WaterLily on a Kaggle T4 only. No in-kernel optimizer, no scheduler, no OpenFOAM profile. Capability evidence only; it measures nothing and qualifies nothing.

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
scripts/harness.py freeze CAMPAIGN_JSON --source-commit X --smoke-table SMOKE_TABLE   # verified smoke record, paginated identity-free check, clean tracked tree, commit on a remote head of repo_url, pins -> <campaign>.prerun_freeze.json; refuses to overwrite
scripts/harness.py verify KERNEL_DIR... --campaign CAMPAIGN_JSON --freeze FREEZE [--out TABLE.json]   # integrity -> validated state-force table
scripts/harness.py verify KERNEL_DIR --campaign CAMPAIGN_JSON --smoke --source-commit X --out SMOKE_TABLE   # the same for a smoke output
```

`X` is a full commit SHA that is already pushed (the Kaggle runner fetches it from GitHub) and contains every bound file, including the campaign and the template, byte for byte. The rendered `runner.py`/`kernel-metadata.json` need not be in X; `freeze` requires the rendered files to equal a fresh render at X.

## Smoke before formal (rule)

No formal kernel is pushed before a smoke kernel of the same campaign has run and `verify --smoke` has passed on its output; `freeze` refuses to write unless it is given that smoke verify table (same campaign hash and source commit, passed, one kernel) and records its SHA-256. `smoke` renders the formal runner of the cheapest kernel with only `KERNEL_ID` (`-smoke` suffix) and `SMOKE = True` changed inside the PIN block and asserts nothing else differs (it fails otherwise). A smoke runs the full path: sparse checkout, pin check, stage-0 self-test, Julia install, instantiate, CUDA probe, the first state, index/manifest/DONE. It does not exercise the other kernels' jobs; a kernel with a different job is smoke-tested with `--kernel K`. `verify --smoke KERNEL_DIR --campaign CAMPAIGN_JSON --source-commit X` (no freeze) checks a smoke output with the formal checks on the first state and requires the smoke runner's source commit, pin map and runner SHA-256 to equal the campaign's smoke rendering at X (not just a well-formed SHA).

## What the runner does (equal to the proven GRID-02 runner for the same inputs)

GPU inventory (Tesla T4 only, physical index 0) -> sparse checkout of the pinned commit and pin verification of every bound file -> **stage-0 self-test** (imports, campaign validation, a schema dry write through the runner's own writers, a planted-truth force recomputation, regeneration and identity check of every state's phi in both byte orders) -> Julia install (pinned SHA) -> `Pkg.instantiate` -> JSON3-free CUDA probe (singleton, UUID equals the selected GPU) -> per state: job with per-state/aggregate/kernel budgets -> index + `output_manifest.json`; `DONE` xor `ERROR.txt`. Optional first-state byte gate against a pinned historical force CSV. Differences from the grid02 runner: the self-test runs before any Julia work (a phi mismatch now stops with zero jobs instead of at that state), `self_test.json` and `harness_version`/`campaign_sha256`/`smoke` identity fields are added.

## campaign.json

All keys are required unless marked optional; `SC.validate_campaign` (in `campaign_schema.py`) is the authority.

```
harness_version   "harness v1.1"
legacy_replay     bool. true only for the verification-only description of pre-harness outputs (the GRID-02 replay): the single case where outputs may lack the harness identity
                  fields and self_test.json, and which build/smoke/freeze refuse. "Harness format" is decided here, never from the output being verified, so stripping the harness fields
                  from a harness output fails instead of downgrading it. The freeze must carry the same flag.
campaign_id       [a-z0-9_]+ ; kernel dirs are infra/kaggle/kernel_<campaign_id>_<k>[_smoke]
owner, repo_url   Kaggle owner; GitHub URL the runner fetches
index_name        e.g. "harness_index.json" ; out_prefix e.g. "<campaign_id>_" (output dir = out_prefix + kernel)
job_env_common    W4_* environment of every job (needs W4_CANONICAL_DESIGN_SPACING_M, _STATE_LABEL, W4_POINT_SHAPE, W4_CELL_SHAPE, W4_SOURCE_SURFACE_SHA256, W4_MARGIN_GATE_M)
job_env_keys      the job variables a run's env may set besides W4_CANONICAL_ORIGIN_M (e.g. ["GRID02_CASE"]). Run env is an allowlist; neither it nor job_env_common (nor job_env_keys) may set a
                  device variable (CUDA_*, JULIA_NUM_THREADS), a per-state identity variable (W4_STATE_*, W4_PHI_*, W4_EXPECTED_MARGIN_M) or W4_SELECTED_GPU_UUID; `job_env` also re-asserts them last.
scrub_env         inherited variables removed before a job env is built (e.g. ["GRID02_CASE"])
measurement       {candidate_operator, time_window_t_u_l: [start, end]}
domain            {flow_origin_m, physical_box_max_m}
baseline          {path, sha256_fortran_raw}            the Fortran-order float32 raw phi every state derives from
directions        {name: {path, sha256_fortran_raw}}    direction raws (max-norm 1)
states            {name: {kind, direction, step_mm, sign, state_sha256, npz_sha256, phi_fortran_order_sha256, phi_c_order_sha256,
                          zero_level_margin_m, margin_tolerance_m, changed_node_count, maximum_pointwise_change_m}}
                  direction null (step 0, sign 0) = the baseline phi itself; otherwise phi = float32(float64(baseline) + sign*step_mm/1000*direction)
                  (scripts/step01_states.perturb) and must reproduce every identity field. Kind and direction agree (parent/parent_repeat <=> direction null); exactly one `parent`;
                  a `parent_repeat` carries the parent's identity fields; every other state has its own phi SHAs (both orders). phi_fortran = SHA of the Fortran-order bytes
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
Semantics: `solver_wall_time_cap_s` is the AGGREGATE cap on the summed solver-process seconds of all states of the kernel, not n x `per_state_timeout_s`; the runner gives each state `min(per_state_timeout_s, remaining kernel time, cap - elapsed)` and stops the kernel (ERROR) the moment a state or the sum exceeds its bound. A cap smaller than one state's timeout is rejected as unsatisfiable by the first state.
Pin closure: every `include("x.jl")`, `include(joinpath(@__DIR__, "a", "x.jl"))` and `Base.include(Module, joinpath(@__DIR__, ...))` of a pinned `.jl` file (recursively) must itself be pinned (as a file, or inside a pinned directory); any include the scanner cannot resolve to a literal path fails the build. Add such files to the kernel's `pins`.
Pinned automatically: Julia project files, `julia/CFDSDFWaterLily/src`, `scripts/step01_states.py`, `scripts/grid01_gpu.py`, `scripts/fd08_v2_campaign_io.py`, the schema, the campaign, baseline and direction raws (checked against the declared hashes at build time), each kernel's job.

## verify and the analyzers

`verify` is the integrity half of an analyzer: manifest safe paths and hashes, DONE xor ERROR, exact state order, schema, run identity and pins against the freeze, GPU, per-state job-summary identity (both phi byte orders, grid, origin per state, margin, window), host recomputation of drag/downforce with the case's force scale against the Julia summary at 1e-9, budgets, first-state gate. It prints/writes the **state-force table** (`kind: harness_state_force_table`, `state_forces_n[kernel][state] = {drag_n, downforce_n, forces_csv_sha256, summary_sha256, solver_process_wall_seconds, julia_summary_wall_seconds}`) or fails closed (exit 3, nothing written; malformed inputs, including KeyError/TypeError/AttributeError/ValueError, also exit 3 with a message). Duplicate JSON keys are rejected when a campaign, freeze or output file is loaded. The table also carries `legacy_replay`, `source_commit`, and `harness_tool_sha256` (the SHA-256 of the schema, build, verify, template and CLI files that produced it). A campaign analyzer is then a small statistics function over that table.

**Smoke tables are not evidence.** A table with `smoke: true` is a check of the path on the first state only; downstream analyzers must read tables through `campaign_schema.require_formal_table`, which rejects `smoke: true` and non-passing tables.

Freeze re-validation: `verify` does not trust `identity_free_check.all_free`; it re-validates the embedded record (owner, kernel ids equal to the campaign's, each page command and result, rows re-parsed from the recorded stdout, no slug/title collision, positive controls, captured <= 24 h before `frozen_utc`, `frozen_utc` not in the future), `campaign_path`, and that each kernel's pins cover the base pins, the campaign (with its hash), the job, the raws (with the declared hashes) and the declared extras. The identity-free listing paginates until a page adds no new ref (not `len(page) < 100`) with a hard 100-page cap that fails closed. The remote check (`freeze`, `smoke`) requires `origin` to be the campaign's `repo_url` (normalised), because that is what the runner fetches. The freeze also records `harness_tool_sha256` and `smoke_verified_sha256`. The run identity records `campaign_work_root` (`CAMPAIGN_WORK_ROOT`, default `/kaggle/working`).

Replay equivalence: `tests/test_harness_replay.py` verifies the five saved GRID-02 outputs through the replay campaign (`legacy_replay: true`; its synthetic freeze carries the same flag and the pre-harness identity-free record, whose all_free flag is the only part re-checked) and checks the table equals `state_forces_n` of `docs/evidence/grid02_trend_2026_10_16/grid02_analysis.json` bit for bit.

Not verifiable offline: the Kaggle side (real Julia/CUDA, the `kaggle` CLI, provider listing). Tests use a fake job, a scratch git remote and a fake `kaggle`.

Harness v1.1 vs v1: legacy decided by the campaign (S1); run-env allowlist and device/identity keys forbidden (S2); identity-free pagination until no new ref (S3); remote check against `repo_url` (S4); freeze re-validation in `verify` (S5); Julia include closure and tool hashes (S6); smoke verify bound to the rendering at a given commit, freeze gated on a verified smoke table, cross-state campaign rules, CLI exit 3 on malformed input, duplicate-JSON-key rejection, `campaign_work_root` in the run identity.
