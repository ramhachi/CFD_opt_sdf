# SRCMAP-03a preregistered P22-v17 boundary-sign invariance certificate

Date: 2026-10-13 Asia/Tokyo. Issue: [#54](https://github.com/ramhachi/CFD_opt_sdf/issues/54).
Integration parent: `f82a5e037409f7e17e8542dfe05043d3bade03f8` (descends from the SRCMAP-02 record `910ead1e205c4df0b47e2f594d60fcd044604244`; the only difference is a documentation-only change to `docs/git_branching_strategy.md`).
Evidence class: solver-free arithmetic certificate over retained evidence. No CFD, no Kaggle, no new geometry query.

## Authority and question

SRCMAP-01 (#52) established `SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC`; SRCMAP-02 (#53) stopped
`SRCMAP02_INCONCLUSIVE` at its exact-zero guard. Neither result is revised. The P22-v2 proposal
(`p22_v17_volume_semantics_bridge_2026_10_11/p22_v2_migration_proposal.md`) was gated on source-mapping
reproducibility. This stage asks a weaker question, namely what P22 actually observes:

> For the retained v17 baseline lattice and source STL, does any sign assignment to boundary-ambiguous
> nodes change the P22 hard mask (`_corner_mean(phi) < 0`), and do the registered LOWDIM gates keep their
> pass/fail classification?

Signer qualification, mapping determinism, and correctness of any sign inside the ambiguity band are
**not** addressed and **not** claimed.

## Disclosure of exploratory prototype (before registration)

Before this registration the author ran an exploratory, unrecorded prototype on the retained SRCMAP-01 fields
and the retained v17 baseline (counts of near-surface nodes, a two-endpoint interval check, an independent
winding-number check, a 256-pattern enumeration, and gate bounds). The parameters below (band representative,
plateau ratio, tolerances) were fixed after seeing that the plateau spans six orders of magnitude, so they are
not blind. **The prototype passed every predicate it exercised**, so this stage is a confirmatory replication
with frozen code, not a blind preregistration; its scratch code is not retained, and the frozen script is a
rewrite that must reproduce its figures on its own. The protection is structural: the predicates and their
numeric thresholds are checked by an independent reviewer on the frozen source, the script refuses to run if
any frozen file or parameter differs from `prerun_freeze.json`, and the outcome is recorded whether or not it is
favourable. No threshold may be changed after the run; a failed predicate is a terminal NOT_CERTIFIED.

## Frozen inputs

- Source STL `docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/reference_surface.stl`,
  SHA-256 `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`; loaded with
  `trimesh.load(force="mesh")`; vertex/face C-byte hashes must equal the SRCMAP-01 values
  (`b2e014fc…`, `7b4be845…`).
- Retained v17 baseline `inputs/v17_baseline.npz` (NPZ `7a972b33…`, state `02f48f64…`), the reference artifact.
- Retained LOWDIM-03 parent `inputs/lowdim03_parent.npz` (NPZ `0ce3256b…`), used only for one smoothed-volume
  relative-change figure.
- The 18 SRCMAP-01 diagnostic fields (verified against its 130-entry `SHA256SUMS`) and the Oct12 replay
  `v17_source_replay_2026_10_12.npz`, used only as controls.
- Production evaluators reused unchanged: `_corner_mean`, `cell_occupancy`, `smoothed_volume_and_gradient`,
  `zero_level_margin_m`, `_gradient_diagnostics`; registered gate constants imported, not copied.

## Frozen parameters

| Name | Value |
| --- | --- |
| `TAU_REP` | `1e-6` m (Float32): representative of the plateau, not the claim |
| `PLATEAU_MIN_RATIO` | `1e3` (smallest outside magnitude / largest inside magnitude) |
| `GWN_TOL` | `1e-9` (distance of an outside-band winding number from 0 or 1) |
| `SMOOTH_BOUND_MAX_REL` | `1e-3` |
| `REFERENCE_SOLID_CENTERS` | `8272` (retained, pre-existing audit value) |

## Method

1. **Band and gap.** `B = {|phi| < TAU_REP}`. The substantive requirement is the gap: smallest outside magnitude
   over largest inside magnitude at least `PLATEAU_MIN_RATIO`, so every `tau` in the gap defines the same `B`.
   (Identical membership at the gap ends is recorded as a sanity check; it is true by construction once the
   gap exists.) The occupancy certificate below is evaluated for ambiguity amplitude up to `TAU_REP`
   (uniform and actual magnitudes; the Float32 chain is monotone, so smaller magnitudes are covered) and
   the descriptive amplitude sweep reports the margin beyond `TAU_REP`. The certificate is therefore bound to
   `B` and to amplitude at most `TAU_REP`, not to the whole gap.
2. **Outside-band signs, independent numerical certification.** Generalized winding number
   (Van Oosterom–Strackee, numpy float64, independent of trimesh signing and libigl) at every node outside `B`.
   Required: distance from {0,1} at most `GWN_TOL` and `(w>0.5) == (phi<0)` at every such node, on a mesh that
   is watertight and consistently wound. This is a numerical certification, not a formal proof.
3. **Occupancy interval certificate.** For every h-cube touching `B`, evaluate the production `_corner_mean`
   over all 2^8 sign patterns of its ambiguous corners, at amplitude `TAU_REP` (uniform) and at the actual
   magnitudes. Required: no cell with `cmin < 0 <= cmax`, no cell whose sign differs from the reference
   in any pattern, both endpoint fields (all `-a`, all `+a`) through the production occupancy equal the
   reference mask, and the endpoint values equal the enumerated extrema. Descriptive: the largest uniform
   amplitude for which the endpoint fields still give the reference mask.
4. **Gate classification robustness (bounds, not observable invariance).**
   - Clearance: production `zero_level_margin_m` on the worst case (every band node solid at `-TAU_REP`), must be
     at least `MARGIN_GATE_M`.
   - Eikonal median: baseline median plus `sqrt(3)*2*TAU_REP/h` must stay below `EIKONAL_MEDIAN_MAX`; narrow-band
     width must exceed `TAU_REP` so band membership is sign independent.
   - Smoothed volume: `pi/(2h) * sum(c_max-c_min) * h^3` relative to baseline V_eps must be below
     `SMOOTH_BOUND_MAX_REL` (= 1% of the registered `VOLUME_BAND`, a conservative factor of 100). The retained
     parent's relative change is bounded two-sidedly, `(V_p +/- b_p)/(V_b -/+ b_b) - 1`, using the parent's own
     ambiguity band, and both ends must stay inside `VOLUME_BAND`. Only the baseline and this one retained
     parent are covered; no candidate or perturbed state is evaluated.
   - Cell components: label count of both endpoint masks must equal `CELL_COMPONENTS`.
   - Masks/support preservation: not applicable (separate arrays).
5. **Controls (never proof inputs).** The population is exactly 19 retained v17 fields: the 18 SRCMAP-01 sign
   variants (excluding the two v16 controls, the unsigned field and the difference maps) plus the Oct12 replay;
   any other count or skip set is an integrity failure. Each must have the reference occupancy mask and no sign
   difference outside `B`.

## Predicates and terminal classification

P1 plateau; P2 outside-sign numerical certification; P3 occupancy interval certificate (both amplitudes,
count 8272 at both ends, reference count 8272); P4 gate classification robustness; P5 controls consistent.
Terminal: `P22_V17_SIGN_INVARIANCE_CERTIFIED` (all true), `P22_V17_SIGN_INVARIANCE_NOT_CERTIFIED` (any false),
`INCOMPLETE` (any not evaluated or an integrity assertion fails). Any contradiction between a control and the
certificate is NOT_CERTIFIED. No threshold change, no tau retuning, no rerun to obtain a pass.

## Claims not made

Mapping reproducibility; qualification of any signer; correctness of any sign inside `B` (no ground truth exists
on the surface); other STLs, lattices or states; any candidate or perturbed state (gate statements cover the
baseline and one retained parent only); invariance under a signer that errs outside `B` (outside-`B` signs are
certified for the retained field and observed controls only, so the claim reads "any signer that agrees with the
winding number outside `B`", not "nondeterminism cannot matter"); CFD response; physical or continuum volume; grid convergence;
invariance of the gate observables themselves (only their pass/fail classification).

## Failure handling

Every identity check is an explicit error, not an assertion. Any exception before a verdict writes
`classification.json` with `INCOMPLETE` and the exception. A crash is **not** a verdict and is not a pass.
Re-execution is allowed only for a demonstrable infrastructure fault (I/O, interpreter or memory), with the
frozen source and parameters unchanged and both attempts recorded; it is never a means of changing a result.

## Process requirements and the successor stage

Independent pre-run review on the frozen source, independent post-run review, one run, full-pytest baseline
comparison (48 known failures, zero new), `compileall`, SHA256SUMS over all evidence. Stop 2 (P22-v2 registration)
is a separate stage with its own freeze and commit, authorized by the user only conditionally on
CERTIFIED plus independent post-run PASS plus zero new test failures; otherwise this stage stops. Stop 2 ends
with a stop: LOWDIM-04A (#51) is not resumed by either stage.
