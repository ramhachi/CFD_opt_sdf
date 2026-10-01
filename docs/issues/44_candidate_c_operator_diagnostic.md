# C-OP-01 (#44): Candidate C operator diagnostic

Status: solver-free baseline-face diagnosis, composite-body API, and a bounded
CPU startup screen are implemented locally on
`feat/issue-44-candidate-c-qualification`. The production contract is not
frozen; W2a-C still needs its full inherited sphere fixture, and W3-C/W4-C have
not been submitted.

## Baseline face

The registered FD-07 `sensitive_faces.csv` identifies the exceptional
`flow_24` baseline face at Julia index `(64,39,21)`, axis 2, world location
`(-0.4166666667, 0.0333333333, -0.25) m`. Its center signed distance is
`-7.4974025e-8` solver cells and its face distance is `+0.5000007` solver
cells. The upstream correction branch is active because `abs(face)>0.5`, and
the center/face signs disagree. Thus upstream uses the negative corrected
face distance, yielding `μ₀=0.09084469`; raw Candidate C has
`μ₀=0.9091553` (`Δμ₀=0.8183106`). The baseline is 7.4974e-8 cells (about
2.4991e-9 m) from the upstream `center=0` branch boundary; it is near, but
not exactly on, that discontinuity.

Both-sided controls confirm the branch: seed 1 at `±1e-8 m` gives center
distances `-4.8356793e-7` and `+3.3361985e-7` cells. Upstream `μ₀` switches
from `0.09084481` to `0.9091555`; Candidate C remains approximately
`0.9091552` and `0.9091554`. At `±1e-7 m`, the face itself also crosses the
half-cell threshold, so those rows are not a pure center-sign control.

The solver-free coefficient records do not identify an individual force
contribution in N. WaterLily's force integration is a stress integral over the
body geometry and solved pressure/velocity fields; `μ₀` influences those
fields through the primal. There is no unique additive force attribution to
one altered moment entry in the saved evidence. The prior whole-body CPU
comparison reports Candidate C baseline shifts of `-3.6580e-6 N` drag and
`-2.9284e-6 N` downforce versus upstream, but it changes the full operator and
does not attribute either shift to this one face. A frozen-field attribution
would not measure the primal effect of `μ₀` because the frozen pressure and
velocity are unchanged.

## Composite body implementation

`CandidateCWaterLilyBody` wraps the `normal_floor=0.25` body (and optional
composed bodies such as moving ground), delegates SDF, normal and velocity
measurement, and changes only `μ₀` at the BDIM face-to-moment handoff. It uses
the registered Candidate C transition width `1.1444091796875e-4` solver cells,
leaves `μ₁` based on the raw face distance, and rejects an inner body without
the concrete `NormalFloorWaterLilyBody` at the exact normal-floor identity.
Its struct constructor also rejects any other floor value or transition
width. Historical `WaterLilyBody.jl` is untouched. The type is explicitly
loaded by Candidate C runners pending broader fixture evidence and contract
freeze.

## Bounded CPU startup diagnostic

The startup diagnostic runs the exact analytic sphere, one- and two-cell
plates, and moving-ground-only control beside sampled Float32 GridSDF versions
through both the upstream moment path with `normal_floor=0.25` and the Candidate
C composite body. It uses the same grid and floor for the primary upstream/C
comparison. This is an exploratory screen on a short, smaller flow domain; the
sphere differs from the inherited W2a sphere and it cannot freeze the
production operator contract.

The immutable Round 5 plan is
[`candidate_c_fixture_diagnostic_2026_10_round5/plan.json`](../evidence/candidate_c_fixture_diagnostic_2026_10_round5/plan.json),
SHA-256 `40e81772763eacbcb5943a8e79abccd0931e6573fdeb489ba4f575ad674dcdd2`.
Its runner hash is
`b9723f7c5f10bd55f17878e97ff52b6de41927464c2fc6b52db5e8f367498acf` and its
registered source-manifest hash is
`6bb8ba232d10f48cc5f05e0f80a8061d486efcdc2ba179a6a2c5c2902689d6c4`.
All plan, runner, and registered source hashes passed before execution. The
runner's initialized Candidate C GridSDF `Simulation`, exclusive atomic output
claim, and Julia parse were separately checked without calling `sim_step!`.

The run command was:

```text
julia -t auto --project=julia/CFDSDFWaterLily scripts/candidate_c_grid_sdf_fixture_probe.jl docs/evidence/candidate_c_fixture_diagnostic_2026_10_round5/plan.json work/candidate_c_fixture_diagnostic_2026_10_round5/run-001.csv
```

It completed 126 samples across 12 fixture/mode combinations. Every sampled
pressure and velocity field was finite; maximum pressure+viscous versus total
force closure was below `2.85e-14 N`. Each history included samples bracketing
the registered `[0.10, 0.25] tU/L` window. An independent Python endpoint
interpolation and trapezoid integration of all nine force components matched
the aggregate means within `5.56e-17 N`.

Raw artifacts are in the ignored work directory and are retained with these
hashes:

- Aggregate: `work/candidate_c_fixture_diagnostic_2026_10_round5/run-001.csv`,
  SHA-256 `eaba35128a168366574efc685f31f5b4dc8daebdf7c7de4a1bcdff6f5062403d`.
- Per-step history: `work/candidate_c_fixture_diagnostic_2026_10_round5/run-001.csv.history.csv`,
  SHA-256 `f29f2f6ffb396424006d6587a26ea042f95c46a7e0ea85bee71fa666ef915dfa`.
- Result manifest: `work/candidate_c_fixture_diagnostic_2026_10_round5/run-001.csv.sha256`,
  SHA-256 `b3d52ddc8f26d8e2caab012a80e179a2b598f0816d58157ec85a88561e6685bc`.

For the sphere, sampled-upstream and Candidate C exact-window mean forces differ
by less than `8.7e-5 N` in any component. For the one-cell plate, their
downforce differs by about `0.35 N`; the two-cell plate differs by about
`4.8e-5 N` in downforce. These are diagnostic observations, not pass/fail
criteria. The inlet/outlet values are raw velocity-plane sums, not mass flow
rates; they do not establish mass conservation. No physical accuracy,
conservation, W2a, W3-C, W4-C, or production qualification follows from this
short screen.

Rounds 1 through 4 remain append-only. Round 1 was rejected before execution
because of incorrect force scaling, confounded controls, non-endpoint window
averages, missing stop enforcement, and a sphere different from W2a. Round 2
identity checking initially failed before any solver step because Julia's
`String(::Vector{UInt8})` consumed the buffer before hashing; the preserved
attempt is `candidate_c_fixture_diagnostic_2026_10_round2/preflight_attempt1.log`
(SHA-256 `2b007040f413729918804f6785a4c13e460c3ad64ac9b82bcad288653337c545`).
Round 3 preserved that hash fix but Julia rejected unsupported `open(..., "x")`
before a solver step (`preflight_attempt2.log`, SHA-256
`f32ae329c5d57baf0ea5e549d27a216c0a6c6d17513d71af780eecc3ae007b79`). Round 4
added an atomic directory claim and failed its no-step initialization preflight
on a vector-versus-tuple origin mismatch (`init_preflight.log`, SHA-256
`09ee3d02f206851c42f86afd7ce8e17dc4cf40bf633ebd2e8f63622571ce972a`). None of
those attempts called `sim_step!` or produced measurements.

## Evidence and limits

Focused Julia self-test command:

```text
julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_candidate_c_body.jl
```

Result: `17 passed`. The test exercises candidate coefficient semantics,
normal-floor identity validation, composed moving-ground measurement, and
finite initialization of WaterLily's `μ₀`, `μ₁`, and velocity fields. This is
implementation/capability evidence, not CFD fixture, conservation, W3-C,
W4-C, force, or physics qualification.

Repository checks run on this branch:

- `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests` — passed.
- `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` — `37 failed, 1225 passed, 5 skipped`. Comparing sorted failure IDs with the measured integration baseline (`37 failed, 1226 passed, 4 skipped`) found the same 37 failures, zero new failures, and zero resolved baseline failures. The one pass/skip count difference is optional ignored-fixture availability in this worktree.
- `git diff --check` — passed before commit.
- `git diff --cached --check` — passed before commit.

The next evidence gate is the full inherited W2a sphere on its fixed `96×64×64`
flow lattice, `Re_D=100`, and `[40,60] tU/D` window, with the exact sphere
sampled into GridSDF and passed through the Candidate C composite body. Keep
the existing W2a limits unchanged and compare against the native analytic
control; the upstream same-GridSDF/normal-floor arm should remain a diagnostic
control. This needs a new immutable operator-identity round before it is run.
W3-C retains the v17 W3 limits; W4-C retains the v17 four-case matrix and
numeric limits with the operator identity changed. All qualification flags
remain false.
