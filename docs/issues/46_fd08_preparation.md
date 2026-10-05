# FD-08 preparation (2026-10-02)

## Scope and dependency

This is solver-free preparation only. Issue #44 has not frozen the production
operator yet. FD-08 must use the composite Candidate C moment blend plus
`normal_floor=0.25` body, on the same backend, flow_24, time window and v17
canonical state. No solver, calibration, epsilon selection, uncertainty fit,
formal criteria registration or qualification run was performed here. The
FD-06 upstream noise observation is intentionally not used as a Candidate C
resolution floor.

After #44 freezes the operator, calibration must determine Candidate C's own
micro-response scale. Only then can its epsilon ladder, independently measured
absolute response resolution floor and uncertainty model be frozen and
registered. Formal evidence must come from 33 new qualification runs, with
run IDs disjoint from calibration. The 5% relative plateau condition,
resolution floor and sign consistency are independent gates. A response at or
below the frozen resolution floor is `UNRESOLVED`, never `PASS`.

## Preparation change

Added `src/cfd_sdf/candidate_c_identity.py` and expanded
`src/cfd_sdf/fd08_contract.py`. The identity loader fails closed until the
append-only #44 contract and matching sidecar exist, then checks the exact
composite body identity, pinned Julia source paths and hashes, wrapper
parameters, and all six literal-false qualification flags. A verified source
identity is not physical qualification.

The preflight checks caller-supplied, disjoint calibration/formal run IDs;
exactly three baseline rows and a complete 3-direction × 5-epsilon × 2-sign
inventory; Kaggle T4 as the caller-declared formal backend; `flow_24`,
`[80,120] tU/L`, and canonical v17 state/Float32 phi bindings; and requested
versus actual in-memory Float32 perturbation values, including changed-node
and magnitude summaries. These checks do not verify Kaggle's runtime identity,
the source/runner inventory, artifact file hashes, or that named runs actually
executed as new solver runs. A renamed historical artifact cannot count as a
fresh execution. The design checker records `fresh_solver_execution_verified`
and `formal_qualification` as false. It writes no criteria and selects no
directions, epsilon ladder, uncertainty model, or resolution floor. The verdict
helper only checks a supplied summary; a strictly positive independently
measured resolution floor, the 5% relative plateau term, and sign consistency
remain separate.

## Verification

- Focused: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_fd08_contract.py` — **5 passed**.
- Full compile: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall -q src tests` — **passed**.
- Full suite: `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` — **36 failed, 1231 passed, 5 skipped**. Compared sorted failure IDs with baseline JSON SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`: **0 new IDs, 1 baseline ID resolved** (`test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`).
- `git diff --check` — passed.
- The first suite invocation without local ignored fixtures had 38 failures; one extra was `test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity`, which could not load the worktree-local v17 NPZ. I created an isolated ignored fixture directory with copies of the existing v17 NPZ/raw inputs and the referenced smoke ProblemSpec YAML, then reran. Logs: [`work/fd08_preparation/full_pytest_before_local_fixture.log`](../../work/fd08_preparation/full_pytest_before_local_fixture.log), SHA-256 `8b3b2ccae3c9175dc3ea8a365db9f04b70f6dac0a5061d43214bafbef8ec1ff1`; [`work/fd08_preparation/full_pytest_with_local_fixtures.log`](../../work/fd08_preparation/full_pytest_with_local_fixtures.log), SHA-256 `b3b958bb8e3da682736e10812875bcc5b0141e2a5bb7f8dbbc83f9f5794027c5`.
- Evidence class: contract/readiness validation only; no CFD, calibration,
  formal FD, gradient, physical-force, or qualification evidence.

## Artifacts

- `src/cfd_sdf/fd08_contract.py`: SHA-256 `ea4e5481e5f9afa9aecf4ad390bbdac313aa8e510f21cb4f21a19708489b1ebc`.
- `tests/test_fd08_contract.py`: SHA-256 `5f8d05d42af48e7fccffb4c396caa7d7bf2cf9c1a379c5a73f3d73b382f6b714`.
- Full-suite logs are under ignored `work/fd08_preparation/`; hashes are listed above. Criteria, measurement and solver artifacts were not created.
- Commit SHA is reported after push.

## Parent review checkpoint, 2026-10-02

The hashes above describe the worker's initial preparation snapshot. Parent
commit `c69c6fe` added the repository-local `src` import bootstrap to the test,
so the shared editable environment cannot accidentally test another worktree.
The current test SHA-256 is
`dfd94dcf431dbad571d2bbb468e78dd64eb7acfa9e845221970c3c14cdd8dc14`.
The contract module hash is unchanged. The literal focused pytest command
passed all five tests; compileall passed. Integration used `merge --no-ff`.

The one formerly failing baseline test became runnable because its ignored
ProblemSpec fixture was copied into this worker's local `work/` directory.
That failure-ID removal is fixture availability, not a source bug repair.
No calibration, immutable formal criteria, or fresh 33-run qualification set
has been created. This remains preparation evidence only.

## Registration and evidence bindings audited after integration

The existing v17 FD-05 record is a protected historical reference, not the
future FD-08 criteria. Its criteria file SHA-256 is
`9cd5e3e35ac779ed937f4516421d82fbd40820dec2ae556817a4ff3ab007918e`
(criteria identity `f9ee9cb265f928aade278b3027f90212292a8c01ac0719a7fd8e7799d387f12f`). It identifies the canonical state file
`sdf_design_state.npz` (SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`),
canonical Fortran-order float32 phi bytes (SHA-256
`e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`),
and v17 state identity `02f48f64…`. Its historical flow is `flow_24`, with
the exact endpoint-clipped trapezoidal physical-time mean over `[80,120]`
`tU/L`; the primary outputs are drag and downforce in N, with direction
derivatives in N/m. This window and state are the required comparison
bindings for FD-08, subject to re-verification against the actual new input
inventory and operator-frozen registration.

The former 33-run registration contained three baseline repetitions
(`baseline_A/B/C`) plus `3 directions × 5 historical epsilons × 2 signs`.
Its direction IDs were `D0_interface_offset`, `D1_filtered_seed11`, and
`D2_filtered_seed2026`; its old epsilon values were 0.5, 1, 2.5, 5, and
10 mm. Those directions, values, perturbation files, hashes, and results are
protected history. The fact that they total 33 does not authorize their
reuse for Candidate C. FD-08 must create its own complete fresh qualification
inventory after calibration. It must explicitly define baseline repetition
count and a rectangular direction × epsilon × sign map whose run IDs total
exactly 33. If the frozen calibration-selected ladder and chosen directions
do not fit that total, the formal campaign must not be registered as 33 by
silently dropping cells or reusing calibration runs.

The old registered runtime reference was Kaggle T4, Julia 1.12.6,
WaterLily 1.8.0, KernelAbstractions, CUDA.jl 6.3.1 and CUDA runtime 12.8.0.
Those values describe historical W3/W4 evidence. The new run must save and
hash its own runtime identity; it cannot claim identity by copying these
reference values. The source identity must include the frozen composite
operator (Candidate C moment blend **and** `normal_floor=0.25` body), the
actual WaterLily job/runner, and criteria/host verifier hashes.

For every calibration and formal run, the future registrar/runner record
must bind the direction bytes and both the requested epsilon and the actual
float32 perturbed phi file hash. It must calculate a nonzero change from the
canonical float32 phi (including changed-node count and an explicit magnitude
summary) so a nominal epsilon that rounds away cannot be accepted. Each run
must preserve the raw force-history artifact and its hash, the source/runtime
identity and hashes, exact-window host recomputation, and primary force in N.
The existing host force pipeline uses force-on-body wrappers; these first
negate WaterLily's unmodified API reaction force, then project
`drag=+Fx_body` and `downforce=-Fz_body`. The criteria's solver-force values
are scaled by `rho*U^2*dx^2` to N (for the reference flow, `1/900 N` per
solver-force unit). Any new evidence must name raw API forces, body-force
components, projections, solver scaling, and physical N as distinct values
to prevent a second sign flip.

The preparation helpers validate supplied contracts and inventories; they do
not create criteria, runner inputs, calibration measurements, or saved
runtime/force records. Reuse the existing FD runner, dataset manifest and host
recomputation path for execution artifacts. Calibration must use Candidate C
measurements, not the upstream FD-06
3–4.5e-4 N diagnostic. Its own response-resolution floor must be recorded as
an independent absolute N term, alongside the unchanged 5% relative plateau
term and sign consistency. A response at/below that independently frozen
floor is `UNRESOLVED`, not `PASS`. Calibration and formal run namespaces and
all artifact paths must be disjoint; calibration evidence is never reused in
the formal verdict.

No immutable FD-08 criteria, numeric epsilon ladder, resolution floor,
uncertainty model, measurement artifact, or qualification result was created
by this audit. The #44 composite operator contract remains unfrozen.

## Decision-rule implementation checkpoint (2026-10-04)

The #44 Candidate C identity is now frozen on the integration branch, and the
FD-08 calibration/formal tooling implements the reviewed decision-rule changes.
This is source and contract implementation evidence only. Calibration criteria
have not been registered, no GPU or CPU CFD rehearsal has been executed, and no
measurement, formal verdict, or qualification flag has changed.

The implementation keeps three state hashes separate: the canonical NPZ file
SHA-256, the canonical `SDFDesignState` identity SHA-256, and the raw
Fortran-order Float32 `phi` SHA-256. The calibration registrar binds each one,
the regenerated D0/D1/D2 direction hashes, every state NPZ/raw-phi hash, and a
full rectangular direction × epsilon × sign inventory. It rejects signed
Float32 perturbations that round away and pairs whose realized centered
direction differs from the requested direction by more than 5% relative L2.

Calibration criteria require exactly five same-state baseline repeats and at
least seven strictly increasing positive epsilon values spanning at least
100×. The host recomputes exact endpoint-clipped trapezoidal means over
`[80,120] tU/L` from raw histories and converts each primary response to N.
Per response, the frozen floor formula is
`max(max(baseline)-min(baseline), 1e-8*max(1,abs(median(baseline))))` N. The
host examines every contiguous five-point window in ascending epsilon order;
all six direction/response cells must be above their own floor, sign-stable,
and within the 5% median-slope plateau rule. It selects the first passing
window; no common window stops before formal registration.

Formal registration accepts only that immutable, hash-bound host analysis. It
independently recomputes the five-repeat floors and common-window selection,
then builds three new baselines plus the complete `3 × 5 × 2` perturbation
grid. Formal classification gives a resolved sign or plateau failure `FAIL`
precedence over any sub-floor epsilon; otherwise any sub-floor point or fewer
than three resolved points is `UNRESOLVED`. Global precedence is `FAIL`, then
`UNRESOLVED`, then `PASS`. All six qualification flags remain literal `false`.

The CPU rehearsal procedure verifies the staged dataset hashes and runs one
baseline plus the smallest-epsilon D0 positive state for one CPU solver step
through the same flow_24 Candidate C composite body. It records this strictly
as setup/operator rehearsal evidence, outside the registered force window and
outside calibration/formal analysis. Both host analyzers independently check
the complete staged dataset and every file in the saved runner SHA manifest;
the formal verifier also rechecks the six-cell inventory and calibration
selection from saved analysis data.

A dry-run of the calibration input builder generated the expected 47-state
inventory (five baselines plus 21 signed pairs) using the candidate ladder
`[0.00005, 0.00015, 0.0005, 0.0015, 0.005, 0.015, 0.05]` m. The ratio is
1000× and all Float32 direction and SDF-margin gates passed. Those numbers are
only a solver-free builder dry-run; no immutable criteria or epsilon ladder
has been registered, and they are not measurement evidence.

Verification at this checkpoint:

- focused FD-08 contract/calibration tests: **22 passed**;
- Python compileall for the changed Python modules, scripts and Kaggle
  wrappers: **passed**;
- Julia parser check for `scripts/waterlily_fd08_cpu_rehearsal.jl`: **passed**;
- calibration builder dry-run: **47 inventory rows**, no criteria/dataset
  write;
- `git diff --check`: **passed**.

The full repository suite was run as
`PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q --tb=no`
from the issue worktree. The suite reported **37 failed, 1421 passed, 9
skipped**; comparison against
`docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256
`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`) found
**0 new and 0 resolved failure IDs**. The initial run had one extra failure
because a worktree does not receive the ignored v17 NPZ; after copying that
input into the worktree and confirming its SHA-256 matched the canonical
`7a972b33…feb31`, the extra failure disappeared. Full log:
[`work/fd08_preparation/full_pytest_2026_10_04_with_ignored_state.log`](../../work/fd08_preparation/full_pytest_2026_10_04_with_ignored_state.log),
SHA-256 `970fd76e77ebcc63d81f70145e0b5daaf6311b91d845fe914caa82663f890d82`
(local ignored worktree artifact).

Kaggle registration, the CPU solver rehearsal, calibration execution, formal
registration, formal execution, and issue posting remain outstanding steps.

The preceding paragraph preserves the state at the original preparation
checkpoint. The following addendum supersedes it only for the operator identity
freeze and registrar/preflight implementation status.

## Registrar/preflight preparation addendum (2026-10-02)

The shared #44 identity record is now present on the integration branch. The
loader passed against that record and its Julia source files: identity
`candidate_c_moment_blend+normal_floor_0.25`, contract SHA-256
`516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`, six
qualification flags literal `false`, and `physical_qualification=false`. The
new preflight reuses the immutable sidecar/JSON loader from
`criteria_supersession.py`; it does not change or register criteria.

Verification on the issue worktree:

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_candidate_c_identity.py tests/test_fd08_contract.py` — **13 passed**.
- `.venv/bin/python -m compileall src tests` — **passed**.
- `.venv/bin/python -m pytest -q` — **36 failed, 1294 passed, 5 skipped**. The failure-ID set was compared with `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`): **0 new IDs; 1 baseline ID resolved**, `tests/test_canonical_objective.py::test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign`.
- `git diff --check` — **passed**.

Evidence class is immutable contract identity and local preflight validation.
No solver, calibration, immutable FD-08 criteria, formal run inventory
registration, or qualification measurement was started. The 33-row design
checker accepts measured, caller-supplied epsilon values and remains a
validator; the resolution floor remains unset until independent Candidate C
calibration. Its run IDs and caller-declared T4 metadata do not establish fresh
solver executions or actual device/runtime identity; those remain requirements
for the future Kaggle runner and host verifier.

## Final implementation verification addendum (2026-10-04)

The legacy summary verdict helper now follows the same fail-closed precedence as
the formal host evaluator: a resolved sign disagreement or a plateau failure
supported by at least three resolved points remains `FAIL` even when another
epsilon is unresolved. With too few resolved points and no established failure,
the response remains `UNRESOLVED`. A regression test covers both mixed-evidence
cases.

Final source checks on the issue-specific worktree:

- FD-08 focused tests: **23 passed**; Python compileall, Julia parser, CLI
  import checks, calibration builder dry-run, and `git diff --check` passed.
- The full repository suite reported **37 failed, 1422 passed, 9 skipped**.
  Its 37 failure IDs exactly match
  `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256
  `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`):
  **0 new and 0 resolved IDs**. The one additional passing test is the new
  verdict-precedence regression test. Local full-suite log SHA-256:
  `d9c1706c9d55302a25a69f5695f18bbf5046c80ba6a237958f9db5513bf84c4f`
  (ignored worktree artifact at
  `work/fd08_preparation/full_pytest_2026_10_04_final.log`).
- The source-only calibration builder preview produced the registered 47-row
  inventory and did not write criteria or dataset files.

No solver or CPU rehearsal ran. Calibration criteria remain unregistered;
formal fresh-33 criteria and verdict do not exist; all six qualification flags
remain literal `false`.

## Source-integrity review addendum (2026-10-05)

The final review added checks that uploaded calibration/formal kernel wrappers
and core runners match their criteria-bound hashes, the host analyzers compare
the executed core-runner hash with the terminal artifact, and the formal
verifier checks its own registered source hash, all formal source inputs, the
frozen Candidate C identity, canonical v17 hashes, and both calibration/formal
runner hashes. Formal registration also rejects calibration analyses whose
immutable status, kind, or literal-false flags do not match the registered
contract.

After these changes, FD-08 focused tests passed (**24 passed**), Python
compileall, Julia parsing, CLI import checks, the 47-row solver-free builder
preview, runner-reuse checks, and `git diff --check` all passed. The full suite
reported **37 failed, 1423 passed, 9 skipped**; comparison with the same pinned
37-ID baseline found **0 new and 0 resolved IDs**. Final full-suite log SHA-256:
`9bf484797761703175f87eb53e77fc72af0f5fc072f512bad775bd48a8447d19`
(ignored worktree artifact at
`work/fd08_preparation/full_pytest_2026_10_04_final_verified.log`).

No CPU or Kaggle solver ran. Calibration criteria remain unregistered, there is
no fresh-33 formal verdict, and all six qualification flags remain literal
`false`.

## Exact-final-tree revalidation (2026-10-05)

The full suite was rerun after the last source-integrity guard landed. It again
reported **37 failed, 1423 passed, 9 skipped**; all failure IDs exactly match
the pinned baseline, with **0 new and 0 resolved IDs**. Final log SHA-256:
`00fb00231edff7670c0d8c254c9ab6c412cbb0cf74186d5ad8e8a428621eb09f`
(ignored worktree artifact at
`work/fd08_preparation/full_pytest_2026_10_05_final.log`). The final-tree
focused suite passed **24 tests**; compileall, Julia parsing, CLI imports,
solver-free builder preview, and `git diff --check` passed. No solver,
calibration registration, or formal registration was performed.


## CPU rehearsal attempt 1 terminal (2026-10-05)

The exact integration source `81c19623bc3d24d64c36691a38cbec0affbdb364`
generated an unregistered 47-state builder preview (preview contract SHA-256
`2912e1c0600291f8e19aee10db3c008e6de36b0e3f6a992f57872cd280e5583e`). The
bounded CPU rehearsal stopped on `cal_baseline_01` before the first solver
step. Julia reported a `MethodError` constructing `GridSDF`: the job supplied
Float64 origin, spacing, and outside-value arguments but passed the registered
margin as Float32, while `GridSDF` requires those constructor values to share
one scalar type. This is a CPU harness type mismatch, not a scientific FAIL,
calibration observation, or formal result. No force history was generated.

The failure is preserved append-only under
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05/`: the preview and its
sidecar, selected baseline Float32 input and hash, exact Julia log, and
`rehearsal_failure.json` with its SHA-256 sidecar. The failure JSON SHA-256 is
`714bd411215e7a86e27cc30f6cb6be2a2f0f779545a47b7e25f0290a6f1f0299`; the
log SHA-256 is
`245d43e388651056f254e9b858372eda98f766f0388e65542ed7681ad1c51375`.
The append-only file inventory is `attempt_manifest.json` (SHA-256
`29b3be09bed137710187dbb311a9028cc35b35a209e66d784e77789f5c6611a9`).
Criteria were not registered, and no Kaggle/T4 solver execution started.

The fix is limited to constructor type consistency: pass the parsed Float64
margin value through unchanged. It does not alter the margin, its tolerance,
the state, direction, epsilon, operator, force convention, or measurement
window. A fresh source SHA and CPU-rehearsal retry evidence are required; the
original failure record remains unchanged. Qualification flags remain false.


## CPU rehearsal retry 1 terminal (2026-10-05)

Source `3fabdcac99d67f34a1704d8bc7bbc77efd75b809` regenerated the same
unregistered 47-state preview (SHA-256
`a2b84fb59160ddc5d096956bcf6da5f8e58bf104afccce5fc3fd49ea183acb61`).
The CPU baseline and smallest-epsilon D0+ each completed exactly one Array
solver step. The host parsed both two-row force histories and verified the
registered component semantics. The runner terminal is 2/2 `COMPLETED`; its
SHA manifest and DONE marker verify, with manifest SHA-256
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108` and
inventory digest `04ca27c1785976b079c68746bfcb95b0756c75e0bcd6a7e06e35ba2ced63a2ac`.

The outer rehearsal then stopped while serializing its result: a repository-
relative output path was passed to `Path.relative_to(ROOT)` before resolving
it. This is a reporting-path harness failure after the bounded setup steps;
the CPU force values are not calibration data and were not analyzed as an FD
response. All attempt outputs are preserved under
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/`, including
raw input states, raw histories, summaries, logs, CPU terminal, DONE marker,
and the complete runner manifest. The host exception record SHA-256 is
`91fc9ad135889db6a4faa4463c32170632387677f568878faebf85a215f4704b`, its
traceback text SHA-256 is
`e49fe053a83650caee443f051697364430a0ea0622d17f03da26d78bbea832f8`, and the
append-only attempt manifest SHA-256 is
`46eda1584781be7443ea1bf7ee96576b6c857446168120b2aa279b53f79baa2f`.

The criteria-neutral repair is to resolve and validate the output directory
inside the repository at the start of preflight, before invoking Julia. A new
source SHA and new output directory are required for the next attempt. No
calibration criteria or Kaggle run has been registered or started; all six
qualification flags remain false.


## CPU rehearsal retry 2 PASS (2026-10-05)

After the criteria-neutral GridSDF scalar-type and output-path repairs, the
full bounded CPU rehearsal passed under integration source
`b47769662dc78981b5c3b3f09aaa7056a2b276d3`. The builder-derived preview
SHA-256 is `897ffbea3f1a4a5f56169f5a7dce5cb77d8337a0f558802c90a9fce9685fc4f0`.
The prescribed first baseline and smallest-epsilon D0+ state each completed
one CPU Array step; Julia 1.12.6 and WaterLily 1.8.0 were recorded, both
Float32 phi margins were about 0.35 m against the registered 0.15 m margin
requirement, and both two-row raw force histories passed host parsing and the
registered force-component/sign audit. The terminal is 2/2 `COMPLETED`. The
runner manifest SHA-256 is
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108`; its
verified inventory digest is
`04ca27c1785976b079c68746bfcb95b0756c75e0bcd6a7e06e35ba2ced63a2ac`.

The full evidence, including input phi files, raw histories, per-state logs and
summaries, DONE marker, and host rehearsal result/sidecar, is under
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry2/`. Rehearsal
result SHA-256 is
`27ec4db23c68a3fd6568796b3bc15d5187f5e34f718dab20666e56057155edf1`; the
append-only attempt inventory SHA-256 is
`b02ec6cb75612f57c23440af74fcbca7cfa13275f5a563551c675b1fb52e2522`. These
one-step CPU forces are setup diagnostics only; they are outside `[80,120]
tU/L`, are not calibration responses, and are not used to set any threshold.
The two earlier harness failures remain preserved under their separate paths.

This completes the bounded setup rehearsal only. Calibration criteria remain
unregistered, Kaggle T4 calibration and fresh33 have not run, no FD-08 verdict
exists, and all six qualification flags remain literal `false`.


## Full validation after harness repairs (2026-10-05)

On pushed integration source `41d84ab1a6f6c8f5f339f89354d411297cec1f30`,
the final bounded-rehearsal code tree passed 38 focused FD-08/identity tests,
Python `compileall src tests`, the Julia GridSDF constructor regression (2/2),
Julia parsing, CLI imports, and `git diff --check`. The full suite reported
**37 failed, 1435 passed, 9 skipped**. Sorted failure IDs exactly match the
pinned 37-ID baseline at
`docs/evidence/four_track_baseline_2026_10_02/failure_ids.json` (SHA-256
`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`): **0 new
and 0 resolved IDs**. Full log SHA-256 is
`c17933f90bb98db8356e04891eef8668769a18e6c732835b715a2e7fdc727976` at
`work/fd08_preparation/full_pytest_after_harness_repairs_2026_10_05.log`
(local ignored artifact); the machine-readable comparison record SHA-256 is
`0a6ca9d0af306302c3ff2e8d64ef1c2820352465d823d8c5f3ca9910acf60f7d` at
`work/fd08_preparation/full_pytest_after_harness_repairs_2026_10_05.json`.

The 37 failures are known repository baseline failures, not FD-08 regressions.
The rehearsal result remains setup-only; calibration criteria are still not
registered, no Kaggle run has started, and all qualification flags remain
literal `false`.


## Calibration criteria preregistered (2026-10-05)

After the source and bounded CPU rehearsal checkpoints above, immutable
calibration round `fd08_candidate_c_calibration_2026_10_04_r1` was registered
on integration source `b559c56a123fc62f73da1bea3429f18ec22b3f8f`. Criteria are
at `docs/evidence/fd08_candidate_c_calibration_2026_10_04/xfidc_criteria.json`
(SHA-256 `23e5eef9f1b7c6a878ea5267c26738089d0cffd3a88b6144a89418ddf9b7ad75`);
the append-only host registration and inventory audit is
`docs/evidence/fd08_candidate_c_calibration_2026_10_04/registration_audit.json`
(SHA-256 `44ff025d541865ec8c4a0f68af205f69923a2c746f33335539063237526c6685`).

The registered inventory is 47 states: five identical-input baseline repeats
and 42 signed perturbations from D0/D1/D2 over the exact calibration-only
epsilon ladder `0.00005, 0.00015, 0.0005, 0.0015, 0.005, 0.015, 0.05 m` (1000x
span). The 89 input files in the ignored local staging directory passed the
registered filename/hash inventory and criteria-sidecar checks; inventory
SHA-256 is `593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.
All 27 source inputs also matched their registered SHA-256 values (sorted
source inventory digest `b22b4d25b73f156a5eb18b38500c36b2a32b05244bfae341aef9347fa27ac29e`).

The criteria bind Candidate C identity, canonical v17 state and phi hashes,
`flow_24`, physical-force conversion, exact `[80,120] tU/L` window, perturbation
directions, actual Float32 changed-node audits, runner/verifier and expected
artifact schemas. Per response, the resolution floor is derived from exactly
five baseline repeats. The deterministic selector examines every contiguous
five-epsilon window in all six direction/response series and chooses the
smallest common passing window, with the registered 5% deviation and sign
rules; no epsilon has yet been selected. These seven epsilons are calibration
candidates only; no formal epsilon ladder is registered. All six qualification
flags remain literal `false`.


Stationarity is recorded and reported only under the explicit
`waterlily_side_rules.stationarity` and the runner's gate set; it does not stop
a state. The inherited XFID-C JSON also carries `measurement.stationarity_gate
= true`, but that field is not consumed by the FD-08 runner or host analyzer.
The registered calibration runner records stationarity separately from its
completion gates. No stationarity threshold or other scientific criterion was
changed.

At this checkpoint the criteria and local staged inventory are registered and
host-verified, but the remote Kaggle dataset has not yet been created, no
calibration kernel has been submitted, and no calibration measurement or
verdict exists.


## Private Kaggle calibration dataset verified (2026-10-05)

The registered dataset `ramhachi888/cfd-opt-sdf-fd08-calibration` was created
privately and reached Kaggle status `ready`. The downloaded archive SHA-256 is
`76edd195c74b5590fdc649dfade14a124d8d72c9154a471fdbbe26ced90e20e4`; Kaggle's
91-file catalog SHA-256 is
`a66e4ad3dcbcccd60f205cfc7c0d0fa6140c04e381cd17b908d684e1834bb665`. All
catalog names and byte sizes matched the downloaded archive. The extracted
dataset passed the registered verifier: its 89 input hashes, criteria JSON,
and criteria SHA sidecar all match; input inventory SHA-256 remains
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.

The append-only per-file host verification record is
`docs/evidence/fd08_candidate_c_calibration_2026_10_04/remote_dataset_verification.json`
(SHA-256 `3af66a93b1487ab4c195e7e543b694cf11f1ba0a2245cc8d084c0ac2e8899148`).
The T4 calibration kernel has not yet been submitted, so no calibration solver
measurements or verdict exist.


## Calibration kernel v1 infrastructure terminal (2026-10-05)

Kaggle kernel version 1 reached terminal status `KernelWorkerStatus.ERROR`
before entering the solver or T4 smoke path. The exact error was
`FileNotFoundError: /kaggle/src/runner_base.py`. The wrapper checks its own
registered SHA successfully, then assumes `runner_base.py` was uploaded beside
the Kaggle `code_file`. Inspection of the installed Kaggle CLI confirms that
`kernels_push` sends the metadata `code_file` as the script body; it does not
upload adjacent helper files. This is a kernel packaging/path defect, not a
solver or scientific failure. No Julia install, GPU smoke test, baseline, or
perturbation ran, and no calibration evidence or verdict was produced.

Kaggle's returned page slug is
`ramhachi888/cfd-opt-sdf-fd-08-candidate-c-calibration`, while the preregistered
metadata ID is `ramhachi888/cfd-opt-sdf-fd08-calibration`; the CLI warned of
that title/ID mismatch. Both exact identities and the error artifacts are
retained at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04/r1_kernel_v1_terminal/`
(terminal audit SHA-256
`887e167a9f5346f8e23ce62d4f3db698c62f8cf6a3adc740317d5c1ce3d19f05`). The
raw Kaggle log is SHA-256
`cb23d12c9392952e4d4293bd6621b8c319d53d4d4a5fbff6c461b037348b6f6b`;
the separate `kernels logs` response is SHA-256
`b3c535559576a83c786ebf5149674ca0410d194878f13d386a6b761c45fd29e8`.

Round 1 criteria and its private input dataset are unchanged. The retry will
package the hash-bound core runner in the one submitted script, correct the
Kaggle title/ID slug alignment, rerun the bounded setup rehearsal against the
new source inventory, and preregister a distinct immutable retry round before
submitting another T4 job. All six qualification flags remain literal
`false`.


## Criteria-neutral kernel packaging repair (2026-10-05)

The retry implementation now builds
`infra/kaggle/kernel_fd08_calibration/runner.py` as a deterministic single-file
Kaggle script from a tracked template and the unchanged `runner_base.py`. The
script decodes the embedded core and checks both wrapper and core SHA-256
values against the attached immutable criteria before entering the core
runner. `scripts/build_fd08_calibration_kernel.py` is included in the retry
source inventory. The kernel title now slugifies to its registered metadata ID
(`cfd-opt-sdf-fd08-calibration`), avoiding the v1 URL/ID mismatch. Round 1
criteria and dataset version 1 remain untouched.

The registrar accepts a separately named retry round and derives a distinct
criteria/result namespace; a dry-run produced the expected 47-state r2
inventory without writing criteria. Kaggle CLI confirms dataset versions can
be added without deleting old versions. No r2 criteria or solver run has yet
been registered or started.

Validation: final focused FD-08/contract/identity tests passed **40/40**;
Python `compileall src tests` and `git diff --check` passed. The full suite
reported **37 failed, 1436 passed, 9 skipped**; sorted IDs equal the pinned
37-ID baseline exactly (**0 new, 0 resolved**). Full log SHA-256 is
`617546368f12ae5fc2d7e2ac4e6dda468f91c4751fdbd95a9cd3aeb25d9268c4` at
`work/fd08_preparation/full_pytest_after_kernel_bundle_fix_2026_10_05.log`
(local ignored artifact); the comparison record SHA-256 is
`2603bbea89578811042eb49a3e7d5091bbd78bd0fb52761c0b6a94173391910d` at
`work/fd08_preparation/runner_bundle_full_pytest_comparison_2026_10_05.json`.
The last focused rerun additionally exercised the r2 path regression. The
calibration retry remains pending and all six qualification flags remain
literal `false`.


## CPU rehearsal under the bundled-kernel source (2026-10-05)

Under pushed integration source `f0ffb82839836516fdc786f36e0530b2361d7b22`,
the builder regenerated the full 47-state setup preview and the bounded CPU
rehearsal completed the prescribed baseline and smallest-epsilon D0+ state,
one Array step each. Julia 1.12.6 and WaterLily 1.8.0 were recorded; both
Float32 phi margins were about 0.35 m against the registered 0.15 m limit, and
both raw histories passed the host force-component/sign audit. The terminal is
2/2 `COMPLETED`. This remains setup-only evidence: its force window is
`[0, 0.0104167] tU/L`, not `[80,120]`, and its forces were not analyzed as FD
responses or used to select criteria.

The builder preview SHA-256 is
`40bc84ff9d5713cc8d9fc95375ae052f4146e8a91c17da0f44e684e99dfbe734`; its 89
staged input files pass inventory digest
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`. All 29
bound source inputs verify, with sorted inventory digest
`a7847b0c3742691fa2f3270fa09fedbe07eac94fae7a6741031d7224a0878b9e`. The
rehearsal result SHA-256 is
`c74c903d2d1f1714bf16ce5a8daaaf357a90e01e03dd7b40d7b4e7cbbaaf6e89`; the
runner output manifest SHA-256 is
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108`, with
verified inventory digest
`04ca27c1785976b079c68746bfcb95b0756c75e0bcd6a7e06e35ba2ced63a2ac`.
Evidence is preserved in
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry3/`. R2 criteria
have not yet been registered, no calibration T4 measurement has started, and
all six qualification flags remain literal `false`.


## Calibration retry round 2 preregistered (2026-10-05)

After the kernel bundling repair and passing bounded CPU rehearsal, immutable
calibration round `fd08_candidate_c_calibration_2026_10_04_r2` was registered
against clean, pushed integration source
`d69a6ed94cd6fd8cc4b4be676f971f3620daa5e5`. The criteria are at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r2/xfidc_criteria.json`
(SHA-256
`27e4e159960576afcd297f116ca6545c640ea783dcc5fbdc9b78d1aecc0bb64d`); the
append-only host registration audit is in the same directory (SHA-256
`201fd5f892dc23a95bd90e3f542cb6f42506b834526a8cccfbd35b8e84f6ef19`).

R2 preserves the same 47 states, five baseline repeats, and calibration-only
epsilon candidates `0.00005, 0.00015, 0.0005, 0.0015, 0.005, 0.015, 0.05 m`.
All 89 input files verify against the registered inventory (SHA-256
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`); all 29
bound source inputs verify against both the worktree and the registered source
commit (sorted inventory digest
`a7847b0c3742691fa2f3270fa09fedbe07eac94fae7a6741031d7224a0878b9e`). The
criteria bind the exact CPU rehearsal result and preview, corrected single-file
kernel bundle, response-floor/selector/verdict contracts, and frozen Candidate
C and canonical v17 identities. No formal epsilon ladder is registered. The
remote Kaggle dataset still needs a new version containing the R2 criteria
before kernel submission. No T4 calibration has run, no epsilon has been
selected, no calibration verdict exists, and all six qualification flags
remain literal `false`.

Post-registration validation: focused FD-08/contract/identity tests passed
**40/40**, Python `compileall src tests` passed, and `git diff --check` passed.
The full suite reported **37 failed, 1437 passed, 9 skipped**. Its sorted
failure-ID set exactly matches the pinned 37-ID baseline: **0 new, 0
resolved**. The full log SHA-256 is
`dd83b20224a29a3f45a675ff077bd9116a79bea8e11e9a29389a4e533922315a` at
`work/fd08_preparation/full_pytest_after_r2_registration_2026_10_05.log`
(local ignored artifact); the exact-set comparison record SHA-256 is
`5c8855cad85c2644de79b269a9ca204593f2f5f9a5743d829824e1545fb05305` at
`work/fd08_preparation/r2_registration_full_pytest_comparison_2026_10_05.json`.


## Private Kaggle calibration dataset version 2 verified (2026-10-05)

The registered private dataset
`ramhachi888/cfd-opt-sdf-fd08-calibration` reached status `ready` after adding
version 2 with R2 criteria SHA-256
`27e4e159960576afcd297f116ca6545c640ea783dcc5fbdc9b78d1aecc0bb64d`. The
downloaded archive SHA-256 is
`3baaa9a22d1b696935684d1a8d6f05c51c748cbbf31e6ed8abad36be48852eb0` (21,834,718
bytes). All 91 remote catalog entries matched the archive's extracted names
and byte sizes; the 89 registered input hashes, criteria JSON, and criteria
sidecar then passed the host verifier. Input inventory SHA-256 remains
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.

The raw 91-file catalog is preserved at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r2/remote_dataset_catalog_v2.json`
(SHA-256 `a7d9015283bb47d71aac64cf5eb59ca7cce696154cc4b4de0467505da55f355a`).
The host verification record is in the same directory (SHA-256
`1ca9925eeaff67621502e0034c4b0a81d5b75fa7bdb2d7dfac1ebadb93503126`). The
dataset's existing private visibility was unchanged. The corrected calibration
kernel has not yet been submitted; no T4 measurement or calibration verdict
exists, and all six qualification flags remain literal `false`.


## Calibration round 2 kernel submission identity terminal (2026-10-05)

Kaggle rejected the R2 kernel before creating a kernel or starting computation.
HTTP 409 returned `ALREADY_EXISTS`: the requested title
`CFD Opt SDF FD08 Calibration` is already in use by a dataset. The immutable
R2 criteria currently bind the same slug for `kernel_id` and
`input_dataset_id`: `ramhachi888/cfd-opt-sdf-fd08-calibration`. Kaggle rejects
that cross-resource slug collision. The new kernel ID is absent from the
owned-kernel listing; the older R1 kernel remains separately preserved at its
old slug and is still an infrastructure ERROR.

The exact criteria/source, metadata and runner identities and API response are
preserved at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r2/kernel_submission_terminal.json`
(SHA-256
`9ff9cf57d007ee3a100edb1df9ef569f83a03f93434805363f547f1e25648360`). No
Julia, T4, solver or calibration measurement ran. R2 criteria, dataset
version 2 and their hashes remain unchanged. A separate R3 source round must
bind a distinct kernel ID and be followed by its own CPU rehearsal and
immutable criteria registration; no calibration epsilon was selected, no
formal evidence exists, and all six qualification flags remain literal
`false`.


## Kernel/dataset identity repair and CPU rehearsal retry 4 (2026-10-05)

The R2 Kaggle 409 showed that the registered dataset and kernel IDs cannot
share a slug. R2 criteria and dataset version 2 remain immutable. Source
`483067ddf926c1df2d23ee47124422099dc0ab93` changes only the registrar's kernel
ID, the matching private-kernel metadata title/ID, and a regression assertion;
the dataset remains
`ramhachi888/cfd-opt-sdf-fd08-calibration`, while the corrected kernel is
`ramhachi888/cfd-opt-sdf-fd08-calibration-kernel`. Its title-derived slug
matches the new ID, and Kaggle's owned-kernel search showed that the new slug
was unused before submission.

Focused FD-08/contract/identity tests passed **40/40**, Python
`compileall src tests` and `git diff --check` passed. Full pytest reported
**37 failed, 1437 passed, 9 skipped**; exact failure IDs match the pinned
baseline (**0 new, 0 resolved**). The full log SHA-256 is
`20c66f171be96a30c0cc59d9a69e6b3247c0567be530ab677b159d839d11ac53` at
`work/fd08_preparation/full_pytest_after_r2_kernel_slug_fix_2026_10_05.log`
(local ignored artifact); the comparison record SHA-256 is
`607fc798958ef1867df53630d2832ba29507ff5b3637afd73e0a42ce59de876a` at
`work/fd08_preparation/r2_kernel_slug_fix_full_pytest_comparison_2026_10_05.json`.

The setup-only CPU rehearsal passed under the new source: baseline and
smallest-epsilon D0+ each completed one `Array` step. Julia 1.12.6 and
WaterLily 1.8.0 were recorded; both raw histories passed host force-component
and sign checks. Both phi margins were about 0.35 m. The sampled force interval
was `[0, 0.0104167] tU/L`, not the registered `[80,120]` measurement window;
the forces are not FD responses. The 47-state preview SHA-256 is
`5dc0e7fa7170d3796c7dfbaf2c023cb45da92850110a172cec913eba39d3a1a7`; the
rehearsal result SHA-256 is
`bff2b597dda142ef133c66e2ff4cc895836be7f0f8ec58d7d3fda3d678060d99`; the
runner manifest SHA-256 is
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108`. All 29
source inputs verify with sorted inventory digest
`c8d1399b2a82646d474911031cb6063cd87f647d0c0de40f14caf4bdbf71ba9f`.
Evidence is under
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry4/`.

R3 criteria are not yet registered; registration follows after these rehearsal
artifacts are committed and pushed. No T4 calibration or epsilon selection has
occurred, the formal ladder remains unregistered, and all six qualification
flags remain literal `false`.

The first R3 registration attempt stopped before writing criteria because the
two valid rehearsal `.log` files matched `.gitignore` rule `*.log` and were not
present in the pushed rehearsal commit. The fail-closed registrar reported the
missing committed D0+ log; it did not write criteria or a staged dataset. The
attempt record is
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry4/r3_registration_attempt1.json`
(SHA-256
`6a48a72b3a9c5dc91c8f84ed6dabedcd4958fa452501321a3cc12a976a0fd9b7`). The
two existing logs' hashes are preserved there and will be force-added to the
evidence commit; no solver rerun or criteria change is needed.


## Calibration retry round 3 preregistered (2026-10-05)

After the distinct kernel identity and complete CPU rehearsal evidence were
pushed, immutable calibration round
`fd08_candidate_c_calibration_2026_10_04_r3` was registered against source
`05c9c59c475f24e3da41e582b49dec3e1e844604`. Criteria SHA-256 is
`a7a8437394f7b34afc591b45db150b0c5d899e86765acdcb49db783272cd31c5`; the host
registration audit SHA-256 is
`f8a5f19d195dc0d3dcc1ac8a51d8533a05bcc5d9c9b4c9625da35934175624cc`.

R3 has the same 47-state inventory, five repeated baselines, seven
calibration-only epsilon candidates, Candidate C identity, force semantics,
response-floor rule, deterministic common-five-point selector, and [80,120]
`tU/L` window. It binds the committed CPU rehearsal and 29-source inventory.
All 89 local staged inputs passed verification (inventory SHA-256
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`). The
kernel ID `ramhachi888/cfd-opt-sdf-fd08-calibration-kernel` is now distinct
from dataset ID `ramhachi888/cfd-opt-sdf-fd08-calibration`. R2 criteria and
dataset version 2 remain unchanged.

The private dataset still needs a new version carrying R3 criteria and a fresh
download/hash audit before T4 submission. No calibration measurement or
epsilon selection has occurred; no formal ladder is registered, no verdict
exists, and all six qualification flags remain literal `false`.


## Private Kaggle calibration dataset version 3 verified (2026-10-05)

The existing private dataset reached a version-3 listing size of 21,834,724
bytes. The downloaded archive SHA-256 is
`2f164a7f921085d2fb039d7be7c385a47031e1f2310a0ae8b771deec039c6941`. All 91
remote catalog entries matched the downloaded archive's extracted names and
byte sizes. The R3 criteria JSON and sidecar match SHA-256
`a7a8437394f7b34afc591b45db150b0c5d899e86765acdcb49db783272cd31c5`; all 89
registered input hashes pass the host verifier with inventory SHA-256
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.

The raw catalog is preserved at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r3/remote_dataset_catalog_v3.json`
(SHA-256 `e509c957ddbb7a6e7676e5e6e11efd99e13e364888eb4a19a1ac18c7854c7bb6`).
The host download/hash verification record is in the same directory (SHA-256
`84d66a022e0eb5ccc8762207a6a7c5ddd3e68b30bcea514ac6a59da5ab0382f9`). The
corrected private kernel has not yet been submitted. No T4 calibration
measurement or verdict exists; no formal epsilon ladder is registered and all
six qualification flags remain literal `false`.


## Calibration round 3 kernel v1 submitted (2026-10-05)

Kaggle accepted private kernel version 1 at
`https://www.kaggle.com/code/ramhachi888/cfd-opt-sdf-fd08-calibration-kernel`
with the registered `NvidiaTeslaT4` request and dataset version 3. The first
status check reported `KernelWorkerStatus.RUNNING`; the initial stdout snapshot
was empty, so actual GPU/runtime identity and solver progress are not yet
verified. The append-only submission identity record is
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r3/kernel_submission.json`
(SHA-256
`9bced35dd374b493eaeca29f49bf4edd1f826c98f93018ed28e203f9193d41ae`). No
terminal artifacts or host analysis exist yet. No epsilon has been selected,
no FD-08 verdict exists, and all six qualification flags remain literal
`false`.


## Calibration round 3 kernel v1 terminal (2026-10-05)

Kaggle kernel v1 ended with `KernelWorkerStatus.ERROR` in the
`criteria_discovery` stage. Its log reports `RuntimeError: criteria SHA
mismatch` at `runner_base.py:255`, 1.76 seconds into startup. The output only
contains the `execution_state.json` stage marker and the Kaggle log; no Julia,
T4 smoke test, or solver step started. No runtime criteria digest or backend
identity was emitted.

The harness cause is a Python namespace-binding bug. The single-file wrapper
computes the attached criteria digest and validates its sidecar, then executes
the embedded core with `runpy.run_path`. Mutating the returned mapping does
not mutate the `__globals__` used by the returned `main` function. The core
therefore still compared the attached digest with its stale embedded value
`39974802c43a55bde53da2afc6e04149ef7fec148d8b678e1f8b92a4523d775b` instead of
R3's registered criteria SHA-256
`a7a8437394f7b34afc591b45db150b0c5d899e86765acdcb49db783272cd31c5`. A local
Python reproduction confirmed the mapping and function globals are distinct.
The host had independently verified the version-3 dataset archive before
submission, but the failed kernel did not emit its mounted criteria hash, so
the runtime artifact does not independently bind that mounted file to R3.

The immutable R3 criteria, dataset v3 and original terminal evidence are
preserved. This is a pre-solver harness failure, not a scientific FAIL or
calibration verdict. The terminal audit SHA-256 is
`27e408bf578c1dbe5c355800a0e635a84e30aa72fbbe0eb8aea20bf94254363b`; its raw
logs and output inventory are under
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r3/kernel_v1_terminal/`.
The repair will be registered as a new source-bound round after a regression
test and bounded CPU rehearsal. No epsilon was selected, no formal criteria
were registered, and all six qualification flags remain literal `false`.


## R3 kernel harness repair and R4 CPU rehearsal (2026-10-05)

Source commit `91bb6f4175435cc0259f3ff7d83c7dd260352ec2` fixes R3's
pre-solver namespace-binding defect. The wrapper now updates the `__globals__`
used by the embedded core's `main` function, binding criteria SHA, mounted
input root, and output root before calling it. The added integration regression
test renders and runs the wrapper with a synthetic core whose initial globals
contain stale values, then checks that the criteria digest and both paths
reach the function.

Validation on that source passed: focused FD-08/contract tests **39 passed**;
Python compileall, Julia parse of `scripts/waterlily_fd08_cpu_rehearsal.jl`,
FD-08 module imports, and `git diff --check`. Full pytest reported **37 failed,
1438 passed, 9 skipped**. The observed failure-ID set exactly matches the
pinned baseline file (`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`):
**0 new, 0 resolved**. Log SHA-256 is
`1884d55fa49fdb7ea54af5efdedfd6fb476026a67ba7ad867058951f4d1d7456`; the
machine-readable validation and set comparison are in
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry5/source_validation.json`.

The bounded rehearsal passed for `cal_baseline_01` and the smallest registered
epsilon's D0+ state, each with one CPU `Array` step. Julia 1.12.6 and WaterLily
1.8.0 were observed. Both raw histories passed host force-component/sign
checks over their initial and post-step rows; this short interval was
`[0, 0.010416666977107525] tU/L`, not the calibration window. Margins were
`0.3499999939931499 m` and `0.34999999925494196 m`. Preview SHA-256 is
`5ac384c3d034f79acb3c5f2e724eaa0dc9f5c74206899ea16c9f7ee0cc8a521b`, result
SHA-256 is
`b7265211f71206ec7f377f556d758ae097e6bb7e477cc3076507d9dbf9c11cfd`, and
runner output manifest SHA-256 is
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108`. All 29
source inputs passed verification with inventory digest
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`. Full
artifacts are under
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry5/`.

One initial host rehearsal invocation stopped before Julia because the command
pointed at an empty dataset root, while the builder had staged the 89 inputs
and preview contract together elsewhere. This input-validation attempt and
its sidecar are preserved at
`docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry5_attempt1/`;
the corrected command used the existing full inventory and passed. Neither
CPU attempt registered criteria or entered calibration evidence. R4's
immutable calibration criteria have not yet been registered; no T4
measurement, formal epsilon, or verdict exists, and all six qualification
flags remain literal `false`.


## Calibration retry round 4 preregistered (2026-10-05)

After fixing the R3 wrapper's Python global binding and passing the bounded
CPU rehearsal, immutable calibration round
`fd08_candidate_c_calibration_2026_10_04_r4` was registered against clean,
pushed integration source `b098d1a60992e217fd131e0b02c383bb39b0a8f5`.
Criteria SHA-256 is
`81434dc9f5b4424b9d1057053bbbfd6465487de0e05035fad81f01db9245b6c5`; the
host registration audit SHA-256 is
`5c9ec766f0eeac5679ae28db7ccfd0af598615fe5b0224a55cbbaab789c25042`.

R4 preserves the same Candidate C identity, canonical v17 state, `flow_24`,
`[80,120] tU/L` measurement window, force semantics, 47-state inventory,
five repeated baselines, and seven broad calibration-only epsilon candidates.
It has no formal epsilon ladder. All 29 source-input hashes match the
registered commit (inventory SHA-256
`e2ea45bb8eb509b36e2b0b06827645dde1aeab0f9fd39b5e5d2c9a9f98a3bedf`); all
89 staged data-file hashes pass (inventory SHA-256
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`). The
preregistration audit verifies the exact criteria sidecar and dataset file
inventory and binds the passing setup-only CPU rehearsal from source
`91bb6f4175435cc0259f3ff7d83c7dd260352ec2`.

The R4 criteria and audit are at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/`. The remote
private dataset is not yet versioned with R4; version 4 download/hash
verification is required before submitting the corrected T4 kernel. No
calibration measurement, epsilon selection, formal registration, or FD-08
verdict exists. All six qualification flags remain literal `false`.


## Private Kaggle calibration dataset version 4 verified (2026-10-05)

The private calibration dataset now downloads with R4's immutable criteria,
SHA-256
`81434dc9f5b4424b9d1057053bbbfd6465487de0e05035fad81f01db9245b6c5`. The
91-file catalog matches every archive filename and byte size; all 89
registered input hashes, criteria hash, and sidecar pass host verification
with input inventory digest
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.

The downloaded archive is 21,834,722 bytes, SHA-256
`d6f95b717b8e65039728a74ce2e3f1d70ec66c525b088f8a70a9453216f03741`. The
remote file catalog is
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/remote_dataset_catalog_v4.json`
(SHA-256
`43f5cb16ebf3af8f67d91a70ef145b1796fa133ee30695f5272cc8d5c54f88e9`); the
download and hash audit is in the same directory (SHA-256
`521f8c6e4311c27bd9e147ce21655b3624c62827221be1fb852cd49b223e6ec7`). The
corrected T4 kernel has not yet been submitted. No calibration solver
measurement or verdict exists; all six qualification flags remain literal
`false`.


## Calibration round 4 kernel v2 submitted (2026-10-05)

Kaggle accepted private kernel version 2 at
`https://www.kaggle.com/code/ramhachi888/cfd-opt-sdf-fd08-calibration-kernel`
using dataset version 4 and the registered `NvidiaTeslaT4` request. Before
submission, all 29 source inputs were reverified against R4's source commit;
the kernel wrapper and embedded core hashes match R4 criteria. The initial
status was `KernelWorkerStatus.RUNNING`, with empty logs and no output files
yet available. The submission record is
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/kernel_submission.json`
(SHA-256
`a4cabc1559383445b090dfd3cf65c8b7ed9b37400ed200d849cd01c13ddb22cb`).

Runtime identity, completed artifacts, and calibration analysis remain
pending. No solver terminal or calibration verdict exists; no formal epsilon
has been selected, and all six qualification flags remain literal `false`.


## Calibration round 4 kernel v2 terminal record (2026-10-05)

Kaggle kernel version 2 terminated with
`KernelWorkerStatus.CANCEL_ACKNOWLEDGED` at its requested 7,200-second runtime
limit. The final execution marker names
`state_D2_filtered_seed2026__eps_5_0000000000e_04__minus`, and the last log
event at 7,189.427 seconds starts that run. `result.json` contains 38 completed
state records out of the 47-state inventory; nine D2 records are missing. The
result is `partial: true`. This is a runtime/infrastructure terminal, not a
scientific FAIL.

The returned result criteria hash matches R4 (`81434dc9f5b4424b9d1057053bbbfd6465487de0e05035fad81f01db9245b6c5`),
and all 29 registered source inputs match source commit
`b098d1a60992e217fd131e0b02c383bb39b0a8f5`. Each of the 38 available force CSV
hashes matches the result record and corresponding saved state-result record.
The runtime smoke recorded two Tesla T4 devices, compute capability 7.5.0,
Julia 1.12.6, CUDA driver API 13.3.0/runtime 12.8.0, CUDA.jl 6.3.1, WaterLily
1.8.0, and driver 580.178.04. R4 marks driver version as recorded, not gated.

The downloaded kernel outputs, raw Kaggle logs/status, and host inventory are
preserved in
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/kernel_v2_terminal/`.
The 200-file output inventory SHA-256 is
`c2fa76d425669da1d97f1e03d370c84209937ee27061cdb3551681d83691ee10`; the
terminal audit SHA-256 is
`accc34a667d40ebe73e29e041bdf3e63575518b2e240281c4353c69a7a15dddf`.
The registered calibration analyzer was not run because the expected state
inventory and final output manifest are incomplete. No calibration verdict,
response floor, or epsilon selection is issued, and all six qualification
flags remain literal `false`.

An infrastructure retry will use the same immutable R4 criteria, source, and
dataset with a 10,800-second Kaggle run limit. The execution allowance does
not change the registered 5,400-second aggregate solver budget or any
scientific criterion. The v2 partial data remain isolated and will not be
mixed with retry outputs.


## Calibration round 4 retry kernel v3 submitted (2026-10-05)

Retry attempt 2 was submitted as private Kaggle kernel version 3 against the
unchanged dataset version 4, with the same immutable R4 criteria SHA-256
`81434dc9f5b4424b9d1057053bbbfd6465487de0e05035fad81f01db9245b6c5`, source
commit `b098d1a60992e217fd131e0b02c383bb39b0a8f5`, runner hashes, and 47-state
inventory. Kaggle's requested execution timeout is 10,800 seconds so the
solver and per-state process startup overhead can finish. This changes no
registered 5,400-second aggregate solver budget or scientific rule. The v2
partial output remains isolated.

Initial status is `KernelWorkerStatus.RUNNING`, with empty initial logs. The
submission and status captures are at
`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/kernel_v3_retry/`
(submission record SHA-256
`9d5381339fbd5deba922d1a96e881f996d406ca71765619acb3e6f41457cb2db`). The
checkpoint comment is
[issue comment](https://github.com/ramhachi/CFD_opt_sdf/issues/46#issuecomment-5984879282).
No calibration analyzer, formal registrar, or verdict has run; all six
qualification flags remain literal `false`.

## R4 v3 terminal and analyzer schema defect, 2026-10-05

Kaggle kernel v3 completed all **47/47** registered states in 9,297.601 s.
Its criteria, integration source, and runner hashes match R4. All 244 files in
the runner SHA manifest pass host verification, as do the complete state
inventory, every per-state force-history hash, all 29 source inputs, all 89
registered dataset inputs, and the registered T4/Julia/WaterLily runtime
checks. Output inventory SHA-256 is
`a6ecfc7c658a96242a9cd37b37370612ce5f80ef838ab32fe917e6926f9939bb`; terminal
audit SHA-256 is
`6ca8e72dfb7bf8dac5c0f1f357a77dc6f7938ec0959007d9eca4c18d21f79aa4`. Full
outputs are saved under
[`docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/result/`](../../docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/result/).
The byte-exact `instantiate.log` is stored as a gzip archive in the adjacent
R4 v3 evidence directory because its trailing space fails `git diff --check`;
the archive metadata records its raw SHA-256 and restore command.

The registered analyzer failed at its schema gate before recomputation. R4
stores `flow_24` in `case.case_id` and `[80,120]` in
`measurement.force_window_t_u_l`; the analyzer instead requires top-level
`flow_id` and `window_tu_l`. The preserved attempt record is
[`calibration_analysis_attempt.json`](../../docs/evidence/fd08_candidate_c_calibration_2026_10_04_r4/kernel_v3_retry/calibration_analysis_attempt.json),
SHA-256 `72153f39c22ec1a90a8d7ef97e5ef762da89808aed4e17cb9d9747d48f1d92e0`.
No raw histories were scientifically analyzed, so no response floor, epsilon
selection, calibration verdict, or formal criteria exist. R4 criteria and
measurements remain immutable; all six qualification flags remain literal
`false`.

R4 binds the analyzer hash, so the schema defect must be fixed in a new source
and criteria lineage. Repeat the bounded setup-only CPU rehearsal and
calibration under that lineage. Do not relabel the R4 analyzer failure as a
scientific result.

## Analyzer schema fix checkpoint, 2026-10-05

Integration commit `f6eaac3eb11eb26d1b9bcc5e13ab20f1cb942ce1` updates the
analyzer to validate `case.case_id` and
`measurement.force_window_t_u_l`, matching the registered criteria schema.
A regression test covers the exact accepted flow/window and rejects altered
values. This changes no solver, force, response-floor, epsilon, threshold,
plateau, sign, time-window, or verdict semantics.

Focused FD-08 tests: **40 passed**. Required Python compileall and
`git diff --check`: **passed**. Full repository suite: **37 failed, 1,439
passed, 9 skipped**; the 37 failure IDs exactly match the pinned baseline
(new 0, resolved 0). The validation record is
[`source_validation.json`](../evidence/fd08_analyzer_schema_fix/source_validation.json),
SHA-256 `965a029cf3f8cbdce63a262b358a494acbee3f4f7b60162a72cc781b3c223942`.

R4 remains complete as a solver run but has no analyzer result: its immutable
source inventory binds the defective analyzer. The corrected source will be
used only with a new CPU rehearsal and a separately registered calibration
round. All six qualification flags remain literal `false`.

## Corrected-source CPU rehearsal checkpoint, 2026-10-05

The builder regenerated the 47-state preview against integration HEAD
`529f8d13a8d99d927ca4036afed85c4fe7853f03`, with the previously registered
seven calibration-only epsilon candidates unchanged. Preview SHA-256 is
`394dad9ee63c9a914256cbb2a51e76fe47f62f13a414e88e085c2b644df707b6`; all 89
staged input hashes match inventory SHA-256
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`.

The bounded CPU setup rehearsal passed the first baseline and smallest-epsilon
D0+ state, one `Array` step each. Julia 1.12.6 and WaterLily 1.8.0 were
observed. Both raw histories pass host force/sign checks over
`[0, 0.010416666977107525] tU/L`; that is only the one-step diagnostic
interval. Runner manifest SHA-256 is
`04f2534b5b0307ba2d42ceeb372e29bc8fdb2d469d4f5cc4ad82d65546dd1108`, result
SHA-256 is
`919c24bd96ef52a106fa2c1de57e4e19fa4f42ae1252f63a019862d45699b2ee`, and
terminal audit SHA-256 is
`d1a668d05967490bf4f9d55dc17966d2718e5cd1c16b9ef333a4f06e3ad1fc66`. This
rehearsal is setup-only and contributes no calibration or formal measurements.

One stale-source preview failed before Julia was invoked; its preserved audit
is `preview_attempt1.json` (SHA-256
`d8ce534607b2d99caa78bcba961b5a354a4c8269cd4e15cfc469817928cb5f7a`). The
current-source rehearsal passed.

## Calibration round 5 preregistered, 2026-10-05

Immutable R5 criteria are registered against clean pushed integration source
`95bd9cbf8e67f0c718e346f7edca3f343ed1091f`. Criteria SHA-256 is
`928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c`; the
registration audit SHA-256 is
`6c45ba460daf53bceb28af371217d45924e9445babf13254bb790fa78e7c9f3e`.

All 29 source inputs, the bound setup-only CPU rehearsal, and 89 staged dataset
files passed registration verification. Dataset inventory SHA-256 is
`593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`. R5
preserves the existing 47-state builder inventory, the same seven broad
calibration-only epsilon candidates, and the 5,400 s aggregate solver budget.
No measurement has started and no formal epsilon exists. Next is private
dataset versioning and T4 kernel submission. All six qualification flags
remain literal `false`.
