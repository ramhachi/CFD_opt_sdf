# P22-v2 registration: decision record and frozen plan

Date: 2026-10-13 Asia/Tokyo. Issue: [#55](https://github.com/ramhachi/CFD_opt_sdf/issues/55).
Integration parent: `e1e858772c9938de9771af90c741a741c7e47581` (the SRCMAP-03a record, #54).
Evidence class: contract registration plus solver-free arithmetic. No CFD, no Kaggle, no optimizer, no shape update.

## Authority and the condition that was met

In this session the user supplied a review recommending a conditional authorization (run Stop 1; register P22-v2 only
if it passes, then stop) and then instructed: "好きにしていい。do it". The plan the session had presented contained the same
structure and its condition was: SRCMAP-03a terminal `P22_V17_SIGN_INVARIANCE_CERTIFIED`, an independent post-run PASS, and
zero new full-suite failures. All three hold ([classification](../srcmap03a_sign_invariance_2026_10_13/classification.json),
sha256 `97a6ff83…b63c`; full pytest 48 failed / 2197 passed / 30 skipped with the same 48 known failure IDs, new 0).

Two limits on that statement. (1) The SRCMAP-03a post-run review approved **only the recording** of that result and
explicitly did not approve downstream use; all reviews in #54 and in this stage are Claude subagents orchestrated by the
authoring session, not human reviewers. The decision to register therefore rests on the user's instruction plus the
certificate and its evidence, not on a review of the registration idea. (2) The instruction does not authorize anything
beyond this registration: LOWDIM-04A is not restarted and no preregistration for it is frozen here.

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
   (`0.1292499984670429` m³, from the P22 audit) is a corroborating observation, not the limit; its agreement with
   `N_max·h³` to about 1e-8 relative reflects the alignment of the lattice with the STL faces and says nothing about
   continuum volume. The **selected LOWDIM-03 parent is not the reference.**
4. **Scope statement (part of the contract):** this is a representation-specific discrete constraint on the registered
   v17 design lattice. It is not a physical or continuum volume constraint, and `N <= 8272` is not equivalent to
   `V <= 0.12925` m³ physical. The evaluator refuses every other lattice.
5. The smooth contract `sdf_native_smoothed_volume_v2` reuses the v1 primitive unchanged (one-sided cosine step,
   epsilon = h, gradient ownership); only the constraint denominator is bound to the derived v2 limit. It never
   substitutes for the hard count. Implemented as a thin module (`volume_semantics_v2.py`, whose `report_v2` carries the scope with every v2 report) that wraps the unchanged v1
   function; v1 source and constants are untouched.
6. **Supersession of a precondition and of the reference definition.** The P22-v2 migration proposal required source-mapping reproducibility to be
   resolved before registration. Reproducibility remains **UNRESOLVED** (#52 nondeterministic, #53 open). For this
   contract only it is reclassified as **non-blocking**, because the reference is an immutable hash-pinned artifact and
   the SRCMAP-03a certificate shows, numerically (Float64 winding-number certification outside the band, exhaustive
   per-cell enumeration inside it, ambiguity magnitudes up to 1e-6 m), that no sign assignment to its 5370
   boundary-ambiguous nodes can change the contracted hard-volume mask of this STL and lattice. The reclassification is
   valid only for that artifact and only for the hard count. The smooth volumes, the parent and the eight perturbation
   states are recorded as facts about retained artifacts and are **not** covered by the certificate; regenerating the SDF
   from the STL, other STLs, lattices or states are outside this contract.

### Disposition of the migration proposal's items

| Proposal item | Disposition |
| --- | --- |
| reference := hard volume of the original geometry mapped to the v17 lattice | replaced by the hash-pinned retained v17 baseline artifact; provenance stays the original STL |
| precondition: source-mapping discrepancy resolved without tolerance relaxation | **not resolved**; reclassified non-blocking for the hard count of this artifact (decision 6) |
| acceptance check 1: independently replay each reference lattice | **not performed and not required** by this contract: the Oct12 replay failed with 3 sign differences, all inside the certified band; deferred to any future regeneration |
| acceptance check 1: v16 original contract still reproduces exactly | met earlier (P22 audit Q1, retained); v1 untouched |
| freeze of the mapping lineage and runtime versions | not applicable: the artifact, not the mapping, is the reference; regeneration is outside this contract |
| acceptance check 2: register under a separate version | this registration |
| acceptance check 3: re-evaluate the parent and perturbations under the new contract, smooth gV never grants feasibility | done for ten states (eight from recorded volumes); the hard count decides, g_V is inactive at the boundary |
| acceptance check 4: separately authorized LOWDIM-04A preregistration before any CFD or solve | **not done and not authorized here** |
| physical continuum cap needs a separate study | stated: this contract is not that |

## What the registration records

The registrar re-measures the retained baseline and LOWDIM-03 parent with the unchanged v1 evaluator
(`sampled_solid_centers_count`) and records the eight LOWDIM-04A perturbation volumes from the retained, hash-pinned
blocker record. Those eight states are **not re-derived**: the generating call was ad hoc and no builder script exists, so
their counts are arithmetic on the recorded volumes (each volume divided by h³ must be an integer, checked). The run
requires all ten states (baseline, parent, eight perturbations) to be exactly at 8272 centers; any other value is an
integrity failure and nothing is written.

## Zero slack (consequence for later work, not authorized here)

The baseline and the parent sit exactly at `N_max`: the hard count constraint is active and integer-quantized, so a
candidate with one more solid center is infeasible. Equal `N_phi` does not mean equal volume: the recorded ±1.25 mm D0
states keep `N_phi` while the smoothed volume changes by about ±2.8%. The smooth constraint `g_V` is about −0.31 at
`N_max` and so is inactive at the hard boundary; it cannot signal the active hard constraint. A later LOWDIM-04A preregistration will need a two-layer rule (smooth
gradient may propose, the integer count decides acceptance) and a rule for proposals that the hard count rejects. That is
a separate decision.

## Frozen method and stop rules

The registrar `scripts/sdf_native_volume_semantics_v2_2026_10.py` runs once. It requires every pinned artifact hash
(SRCMAP-03a evidence and its `SHA256SUMS`, the proposal, v1 registration, genesis v17 evidence, retained states, the
LOWDIM-04A blocker by its literal hash), a CERTIFIED SRCMAP-03a classification and the unchanged v1 contract hash; any mismatch is an integrity failure
and no registration is written. It refuses to overwrite a different registration or to accept a sidecar that differs
from the registration (a rerun with identical content is idempotent; a crash between the registration and sidecar writes leaves a state that the next run refuses, so recovery is manual, fail-closed). The payload carries no environment fields. It writes
`docs/evidence/sdf_native_volume_semantics_v2_2026_10.json` and a `.sha256` sidecar.
Process: this record, the module, the registrar and their tests are frozen by hash before the run; an independent pre-run
review precedes it and an independent post-run review follows; the full suite is compared with the known 48 failures. One
test of the *generated* artifact (`tests/test_sdf_native_volume_semantics_v2_registration.py`) is added after the run; it
reads the artifact and cannot change it, and this is disclosed rather than frozen. P22 v1 files, production mapping,
dependencies and every qualification flag are unchanged. After the run, `docs/phase_plan.md` and
`docs/problem_register_2026_09.md` get a section linking the registration and stating that #51 stays blocked pending a
separate decision. **The stage stops at the registration.**

## Claims not made

Mapping reproducibility or signer qualification; physical or continuum volume or grid convergence; feasibility or
optimality of any candidate; any state on another lattice; that LOWDIM-04A may restart; differentiability of the hard
count. `selected_delta=null`, `shape_update_allowed=false`; CFD runs 0; Kaggle submissions 0.
