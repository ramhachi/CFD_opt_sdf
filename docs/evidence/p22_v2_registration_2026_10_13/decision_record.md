# P22-v2 registration: decision record and frozen plan

Date: 2026-10-13 Asia/Tokyo. Issue: [#55](https://github.com/ramhachi/CFD_opt_sdf/issues/55).
Integration parent: `e1e858772c9938de9771af90c741a741c7e47581` (the SRCMAP-03a record, #54).
Evidence class: contract registration plus solver-free arithmetic. No CFD, no Kaggle, no optimizer, no shape update.

## Authority and the condition that was met

In this session the user supplied a review recommending a conditional authorization (run Stop 1; register P22-v2 only
if it passes, then stop) and then instructed "do it" without further restriction; the plan the session had presented
contained the same structure. The condition written into that plan was: SRCMAP-03a terminal
`P22_V17_SIGN_INVARIANCE_CERTIFIED`, an independent post-run PASS, and zero new full-suite failures. It is met:
[classification](../srcmap03a_sign_invariance_2026_10_13/classification.json) (sha256 `97a6ff83…b63c`), independent
post-run review PASS (`independent_review_postrun.md`), full pytest 48 failed / 2197 passed / 30 skipped with the same 48
known failure IDs (new 0). The instruction does not authorize anything beyond this registration: LOWDIM-04A is not
restarted and no preregistration for it is frozen here.

## Decision

1. Register **`sdf_native_volume_semantics_v2_2026_10`** as a separate contract. P22-v1 (registration sha256
   `0142ace4…`, limit `0.12612500000000004` m³, 1009 centers on the 61×33×25 v16 lattice) is unchanged, immutable and
   remains the historical authority for that lattice. The v1 verdict on the v17 baseline (it exceeds the v1 limit by
   `0.003125` m³ before any optimization) is preserved as a historical fact, not revised.
2. The primary constraint is the **integer** `N_phi <= N_max = 8272` on the registered v17 lattice (origin
   `(-1,-0.8,-0.6)` m, h = `0.025` m, nodes `121×65×49`). `V_max = N_max·h³ = 0.12925000000000003` m³ is derived only and is
   never the acceptance quantity (this also avoids float-literal equality defects).
3. The reference is the hash-pinned pre-LOWDIM v17 baseline artifact (state `02f48f64…`, NPZ `7a972b33…`, phi
   Float32 C-bytes `f6419547…`). The physical provenance is the original STL (`5e6d2107…`); its polyhedral volume
   (`0.1292499985` m³) is a corroborating observation, not the limit. The **selected LOWDIM-03 parent is not the reference.**
4. **Scope statement (part of the contract):** this is a representation-specific discrete constraint on the registered
   v17 design lattice. It is not a physical or continuum volume constraint, and `N <= 8272` is not equivalent to
   `V <= 0.12925` m³ physical. The evaluator refuses every other lattice.
5. The smooth contract `sdf_native_smoothed_volume_v2` reuses the v1 primitive unchanged (one-sided cosine step,
   epsilon = h, gradient ownership); only the constraint denominator is bound to the derived v2 limit. It never
   substitutes for the hard count. Implemented as a thin module (`volume_semantics_v2.py`) that wraps the unchanged v1
   function; v1 source and constants are untouched.
6. **Supersession of one precondition.** The P22-v2 migration proposal required source-mapping reproducibility to be
   resolved before registration. Reproducibility remains **UNRESOLVED** (#52 nondeterministic, #53 open). For this
   contract only it is reclassified as **non-blocking**, because the reference is an immutable hash-pinned artifact and
   the SRCMAP-03a certificate shows that no sign assignment to its boundary-ambiguous nodes can change the contracted
   hard-volume mask. The reclassification is valid only for that artifact; regenerating the SDF from the STL, other
   STLs, lattices or states are outside this contract.

## What the registration records

The registrar re-measures the retained baseline and LOWDIM-03 parent with the unchanged v1 evaluator
(`sampled_solid_centers_count`) and records the eight LOWDIM-04A perturbation volumes from the retained, hash-pinned
blocker record. Those eight states are **not re-derived**: the generating call was ad hoc and no builder script exists, so
their counts are arithmetic on the recorded volumes (each volume divided by h³ must be an integer, checked). The expected
values are 8272 centers (residual 0) for every one of the ten states.

## Zero slack (consequence for later work, not authorized here)

The baseline and the parent sit exactly at `N_max`: the hard count constraint is active and integer-quantized, so a
candidate with one more solid center is infeasible. A later LOWDIM-04A preregistration will need a two-layer rule (smooth
gradient may propose, the integer count decides acceptance) and a rule for proposals that the hard count rejects. That is
a separate decision.

## Frozen method and stop rules

The registrar `scripts/sdf_native_volume_semantics_v2_2026_10.py` runs once. It requires every pinned artifact hash
(SRCMAP-03a evidence and its `SHA256SUMS`, the proposal, v1 registration, genesis v17 evidence, retained states, LOWDIM-04A
blocker), a CERTIFIED SRCMAP-03a classification and the unchanged v1 contract hash; any mismatch is an integrity failure
and no registration is written. It refuses to overwrite an existing registration. It writes
`docs/evidence/sdf_native_volume_semantics_v2_2026_10.json` and a `.sha256` sidecar.
Process: this record, the module, the registrar and their tests are frozen by hash before the run; an independent pre-run
review precedes it and an independent post-run review follows; the full suite is compared with the known 48 failures. One
test of the *generated* artifact (`tests/test_sdf_native_volume_semantics_v2_registration.py`) is added after the run; it
reads the artifact and cannot change it, and this is disclosed rather than frozen. P22 v1 files, production mapping,
dependencies and every qualification flag are unchanged. **The stage stops at the registration.**

## Claims not made

Mapping reproducibility or signer qualification; physical or continuum volume or grid convergence; feasibility or
optimality of any candidate; any state on another lattice; that LOWDIM-04A may restart; differentiability of the hard
count. `selected_delta=null`, `shape_update_allowed=false`; CFD runs 0; Kaggle submissions 0.
