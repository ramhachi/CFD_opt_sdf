# WP4 Amendment 5 validation and handoff

These artifacts are software regression / short CPU capability evidence.
They are not a study freeze, GPU qualification, TR-00 reference, RANS result,
or a physical concordance claim. Task-start source was `db36e4e5`; the exact
tested working-tree bytes are recorded in the execution records. Claude owns
the later host commit, push and PR #89 update.

## Records

- `authority.json`: SHA of the read-only follow-ups registration Amendment 5
  and Opus review used for this change. The local registration is not edited.
- `targeted_execution.json`, `full_execution.json`: argv, return code,
  duration, source hashes before/after and failure-node comparison.
- `cpu_execution.json`, `cpu_host_verification.json`, `cpu_selftest/`:
  branch-local WP1, static remeasurement bit identity, tuple `isbitstype`,
  moving ground, phase/core checks and the artificial tiny-timestep receipt.
- `polluted_env_execution.json`, `polluted_env_force_table.json`,
  `polluted_env_smoke/`: actual CPU smoke with inherited `TOPO2D_DIMS=12,12`,
  invalid resume/checkpoint/scene/device variables; actual dimensions 840x824.
- `geometry_regeneration.json`, `geometry_summary.json`: all ten scenes,
  unchanged polygon/surface coordinates, sampling metrics, ratios and noses.
- `checker_cli.json`, `synthetic_analysis/`, `synthetic_reference/`:
  planted coefficient/Cp fixtures only; WP4 analyzer, independent checker and
  the read-only WP5 digitizer agree. Their `CONCORDANT` is not a study result.
- `protected_source_closure.json`: unchanged protected source/evidence paths.
- `log_archives.json`: exact raw-log SHA and deterministic gzip transport.
- `wp04_pending_files.json`: complete intended host commit list.
- `SHA256SUMS`: the committed validation artifacts, excluding this manifest.

The deliberate `cpu_selftest/dt_collapse/ERROR.txt` is an expected negative
test: the actual job exits 42 with `NUMERICAL`. The artificial checkpoint is
excluded after its size/SHA is recorded; the failure receipt is retained.
No formal `topo2d00_window_re*.json` exists because no GPU pre-run was executed.

For a fresh checkout, restore the archived `polluted_env_smoke` job log to its
original path before running `scene_campaign.verify`: the original runner
manifest binds that byte stream. `log_archives.json` maps archive to raw path.
Archives live outside the smoke tree so they do not change its manifest file
set. The absolute raw-reference paths in the synthetic analysis identify this
worktree; retain that layout to replay its checker unchanged.

## Future parent pre-run and formal flow (host only)

This is a runbook, not permission or an execution record. First resolve the
PDF image verification / digitisation and source-review/freeze prerequisites.
`UNVERIFIED_OCR` scenes are deliberately refused on both the W admission path
and the study analyzer's five main/sharp geometry inputs. Verification needs
source evidence and a new source identity, rather than relabelling a JSON.

1. After the externally owned freeze 1 and backend gate, run the two E1 states
   with `scene_campaign.py run-frozen ... re1000 ... --prerun` and `re3000`.
   Both use phase 0, main grid, sample every 8 solver steps, horizon 520 c1/U
   and measurement window [80,520]. `verify --prerun` requires both kernels.
2. Use `scripts/topo2d00/prerun_window.py SERIES SUMMARY` once per Re. Its
   default target is `docs/harness/topo2d00_window_re<Re>.json`. Nominal force
   is N/m (rho=1, U=1), time c1/U and S0 (N/m)^2*c1/U.
3. The next external freeze supplies `parent_window_records[kernel]` with
   record path/SHA: re1000 uses its own record; re3000 and confirmation use
   the Re3000 record. It contains no `windows` or `formal_context` field.
   Admission re-hashes and recomputes the records from raw histories and
   checks runtime/source/scene/height before returning B and B+W.
4. Normal `run-frozen` excludes the two parents and executes the 125 formal
   states; normal `verify` requires all three kernels. The pre-run and formal
   outputs remain separate. Existing solver caps remain 14h + 14h + 6h;
   each separate parent is also bounded by the existing 1h per-state cap.
   No cap extension or automatic paid/retry route is supplied.
5. The formal analysis CLI requires the hash-bound verified force table,
   the WP5 RANS result, study freeze and all raw reference records. It writes
   analysis.json / analysis.md / tr00.json / SHA256SUMS once; invoke the
   independent checker on analysis.json after writing.

Burn-in discretisation is fixed before data: 100-wide blocks starting at
0,100,200,300; compare a candidate with the subsequent complete block means'
mean +/- sample SD/sqrt(n), at least two subsequent blocks. B=max(80,start).
An unbracketed time-zero candidate is skipped without extrapolation. Each
5/10/20/40/80 post-B batch length yields a one-sided 90% chi-squared upper
bound of length*sample variance; S0 is their maximum with incomplete trailing
batches omitted. W is the smallest 50 multiple meeting 1.5%, at most 400;
failure to meet that cap is refused. These engineering estimates are separate
from formal paired sigma_d=max(A,B), which uses no upper-bound multipliers.

## Future GPU capability smoke (user equipment only; not executed here)

Follow the Opus review's CPU-to-GPU conditions:

- Invoke `scripts/waterlily_topo2d_job.jl` directly, using
  `--project=julia/CFDSDFWaterLilyT4`, `TOPO2D_BACKEND=cuda`,
  `TOPO2D_SMOKE=1`, and `W4_SELECTED_GPU_UUID` of the actual device.
  Supply the actual job/scene SHA variables as required by the job.
- Start from a clean job/device environment; leave no inherited
  TOPO2D_CHECKPOINT, TOPO2D_RESUME, TOPO2D_DIMS or TOPO2D_TOP_FACTOR.
- Use scratch output, never docs/evidence. Run E1, then E3 (largest tuple),
  at the declared formal grid for a few hundred steps.
- Record Julia/CUDA/WaterLily/device/runtime/source/scene identities, compile
  time, acceptance of the approximately 15.7KB tuple kernel parameter, and
  measure! versus mom_step! milliseconds per step. The actual job keeps
  remeasure=false. Compare finite force values with the CPU reference and
  record the values/differences without inventing a qualification threshold.
- CUDA checkpoint restore, full windows and GPU performance remain
  unverified. Label the smoke capability-only; it is neither LOCAL-GPU-01
  nor TOPO-2D-00 scientific evidence.
