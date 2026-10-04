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
