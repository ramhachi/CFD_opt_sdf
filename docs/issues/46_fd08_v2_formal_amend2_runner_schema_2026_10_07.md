# #46 Formal Infrastructure AMEND2 — Runner Schema Repair

The user authorized AMEND2 on 2026-10-07. R6 remains immutable PASS, 8/8;
no R6 solver or analyzer is rerun. AMEND1 registered criteria and payload remain
historical evidence; their files are never edited, regenerated or overwritten.
AMEND2 supersedes the unrun infrastructure registration, not its scientific
contract. Main and unrelated worktrees are untouched.

## Parent and exact blocker

AMEND1 criteria `FD08-V2-FORMAL-AMEND1-2026-10-07` has SHA-256
`857c21231eb48708daba784318445c43d115dca48567dfd3378c3ba177bd57fe` and execution
source `30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5`. Its dedicated dataset was
not uploaded, no kernel was submitted, no solver started, and zero formal
observations/comparisons exist. Its raw registered payload/archive, source,
runner hash, host traceback and campaign stop record stay immutable.

The registrar saves formal geometry rules in `criteria["geometry"]`; the old
shared runner required `criteria["geometry_reject_gates"]` at state validation,
raising exactly `KeyError: 'geometry_reject_gates'`. Criteria loading and the
54-file mounted dataset / 40-source-input checks passed before this exception.
Cause: missing dispatch for the distinct formal schema. Geometry values and
scientific thresholds are identical to R6; the repair changes interpretation of
the field name only, with explicit kind dispatch and no fallback alias.

## Allowed changes and unchanged science

The shared runner normalizes formal kind to `geometry`, and R6/setup to their
existing `geometry_reject_gates` schema. Existing setup main behavior remains;
scientific state validation, masks, margins and rejection thresholds remain.
A guarded rehearsal hook prepares every measured-state command/environment
and stops immediately before any measurement process launch. Absent its
explicit environment flag, the production measurement path is unchanged.
The default source fetch ref remains integration; candidate rehearsals may
explicitly fetch the dedicated feature ref, using the exact committed source
and source-input SHA checks.

The new registrar `scripts/register_fd08_v2_formal_amend2.py` verifies and
reads AMEND1's lossless archive, copies its state raw/NPZ bytes and entire
scientific criteria content, and updates only execution/identity/lineage and
packaging. It does not regenerate a direction, refit R6, or compute a formal
prediction/verdict. A whitelist of identity/lineage/package fields defines the
comparison; every other field must equal AMEND1 exactly. State definitions,
calibration binding (including frozen coefficients/covariance), T2, Model A,
COV-A, four directions/hashes, epsilon, geometry, runtime, no-refit,
measurement contract/caps, numeric prediction rule, aggregation, claims and
six false flags must all be unchanged.

Exact interior epsilons remain 0.6294627058970836, 1.5811388300841898,
3.971641173621408 mm, intervals {0,2,4}; inventory remains baseline 1 plus
four directions × three epsilons × two signs = 25 states. Caps remain
3300 s aggregate solver / 5600 s overall allowance. Scientific contract impact:
none. No response-dependent behavior is added.

New identities are criteria `FD08-V2-FORMAL-AMEND2-2026-10-07`, round
`fd08_v2_formal_2026_10_07_amend2`, dedicated private dataset/kernel
`ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend2`. AMEND1 is recorded separately
as `REGISTERED_NOT_RUN_SUPERSEDED_INFRASTRUCTURE`, with exact criteria/source/
blocker SHA, zero observations and solver_started=false. R6 source remains
`f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9` in calibration provenance; formal
execution binds the clean pushed AMEND2 integration merge, not this old source.

## Actual pre-solver execution gate

Tests inventory all runner criteria paths, exercise formal/R6/setup dispatch
and actual payload compatibility, and compare scientific content/state bytes
exactly. Independent schema and scientific reviewers inspect the proposed
diff and candidate without a primary safety conclusion. Full pytest must
introduce zero failures relative to the frozen 37-ID baseline.

The actual registered runner executable, not a replacement verifier, must load
the candidate payload, validate immutable flags/criteria SHA, exact inventory/
manifest and files, all 25 NPZ/raw/mask/margin/uniqueness inputs, fetch/checkout
and verify the complete committed source, verify uploaded runner bytes, build
runtime configuration and every state command/environment. The rehearsal
retains GPU inventory, Julia install/instantiate and runtime smoke. It stops
only at each measured solver invocation, before process launch. All 25 prepared
plans must be collected; the terminal is `PASS_PRE_SOLVER_EXECUTION_PATH` with
solver_started=false, never scientific COMPLETE/DONE/result or force history.

The host is macOS without the registered T4 runtime. The complete upstream
runtime path is therefore exercised through Kaggle CLI in a separate private
setup-only rehearsal notebook/kernel and input identity. Its notebook sets the
explicit stop flag and executes the exact hash-bound runner source. Temporary
rehearsal input versions contain prospective candidate or registered bytes;
they are neither an AMEND2 scientific dataset publication nor a solver run.
No full WaterLily state job, force CSV, S_obs, fit or verdict is allowed.
The normal formal kernel runs the same runner with the hook absent.

A candidate rehearsal passes before integration; after merge, the exact final
source and candidate must pass before immutable registration. The registered
criteria/payload then pass the same executable again before publishing the
formal dataset. Candidate bytes and registration status are distinguished in
evidence; prospective immutable flags exercise the consumer but do not assert
that the candidate has been registered. Rehearsal outputs/source/criteria/input
SHA, runtime, 25/25 state/config count and terminal marker are retained. Any
solver launch or rehearsal failure is fail-closed, with no formal registration
(or no publication after registration) and no threshold/source adjustment of
an already registered instance.

## Execution and final interpretation

Only after all gates, reviews, tests, actual rehearsals and fresh CLI budget
capability pass is AMEND2 registered. The formal dataset has a distinct identity
and its exact remote version is downloaded/hash-checked before submit. Complete
25/25 terminal integrity precedes one registered formal analyzer invocation.
All 24 comparisons PASS -> formal PASS; any FAIL -> formal FAIL; no FAIL and any
UNRESOLVED -> formal UNRESOLVED. Scientific FAIL/UNRESOLVED is terminal, with no
retry, refit, model switch or tuning. Source bugs require a new amendment and
registration identity; transient provider failures may retry unchanged inputs.

Even PASS qualifies only the frozen Candidate C/v17/flow_24 four-direction
local diagnostic/interior interpolation contract. It does not establish
physical truth, high-Re validity, grid independence, arbitrary direction/full-
field gradient correctness, exact epsilon-to-zero derivatives, reverse AD,
optimizer or topology. Flags remain false before formal PASS; fd_oracle can
change separately only if governing authority explicitly permits it.
